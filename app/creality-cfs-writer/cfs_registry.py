# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Persistent CFS codes bound to existing Creality profile setting IDs.

Only this registry may be updated during local discovery. Original JSON/.info
files are always read-only; neither names nor inherited filament IDs allocate
new CFS codes. In printer-cloud mode a validated public printer snapshot is
authoritative and local profile files are never consulted.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from cfs_locking import locked_file
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from cfs_codec import DEFAULT_MATERIALS, _is_slicer_profile, _slicer_material, _resolve_slicer


DEFAULT_REGISTRY_PATH = Path(os.environ.get("CFS_PROFILE_REGISTRY", Path(__file__).with_name("profil-zuordnung.json")))


class RegistryError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def read_profile_info(path: Path) -> dict[str, str]:
    result = {}
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise RegistryError("MISSING_PROFILE", f"Profilinformationen fehlen oder sind nicht lesbar: {path}") from exc
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def _version_key(directory: Path):
    return tuple(int(number) for number in re.findall(r"\d+", directory.parents[2].name))


def _active_source_directory(entry: dict) -> Path:
    directory = Path(entry["source_file"]).parent
    # <Creality Print>/<version>/user/<account>/filament
    if directory.name == "filament" and directory.parent.parent.name == "user" and len(directory.parents) >= 4:
        account = directory.parent.name
        base = directory.parents[3]
        candidates = [path for path in base.glob(f"*/user/{account}/filament") if path.is_dir()]
        if candidates:
            return max(candidates, key=_version_key)
    if not directory.is_dir():
        raise RegistryError("MISSING_PROFILE", f"Der registrierte Profilordner fehlt: {directory}")
    return directory


class ProfileRegistry:
    def __init__(self, path: str | Path = DEFAULT_REGISTRY_PATH):
        self.path = Path(path).expanduser().resolve()
        self._cloud_cache = None
        self._cloud_cache_at = 0.0
        self._cloud_cache_key = None
        self._cloud_lock = threading.RLock()
        self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise RegistryError("BAD_REGISTRY", f"Profilzuordnung kann nicht gelesen werden: {self.path}") from exc
        if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("profiles"), list):
            raise RegistryError("BAD_REGISTRY", "Unbekanntes Format der Profilzuordnung.")
        if data.get("sync_source", "local_profiles") not in ("local_profiles", "printer_cloud"):
            raise RegistryError("BAD_REGISTRY", "Unbekannte Quelle für die Profilzuordnung.")
        codes, setting_ids = set(), set()
        reserved = {item["id"].casefold() for item in DEFAULT_MATERIALS}
        for entry in data["profiles"]:
            if not isinstance(entry, dict):
                raise RegistryError("BAD_REGISTRY", "Ungültiger Eintrag in der Profilzuordnung.")
            code = entry.get("material_id")
            setting_id = entry.get("profile_setting_id")
            if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9]{5}", code):
                raise RegistryError("BAD_REGISTRY", "Jeder registrierte Materialcode muss genau fünf Buchstaben/Ziffern enthalten.")
            if not isinstance(setting_id, str) or not setting_id.strip():
                raise RegistryError("BAD_REGISTRY", f"Dem Code {code} fehlt die eindeutige Profil-setting_id.")
            if code.casefold() in codes or code.casefold() in reserved or setting_id in setting_ids:
                raise RegistryError("COLLISION", f"Doppelter oder reservierter Materialcode bzw. doppelte Profil-ID bei {code}.")
            required_fields = ("name", "source_file") if data.get("sync_source") == "printer_cloud" else ("name", "source_file", "info_file")
            for key in required_fields:
                if not isinstance(entry.get(key), str) or not entry[key].strip():
                    raise RegistryError("BAD_REGISTRY", f"Dem Code {code} fehlt {key}.")
            if data.get("sync_source") != "printer_cloud" and Path(entry["info_file"]) != Path(entry["source_file"]).with_suffix(".info"):
                raise RegistryError("BAD_REGISTRY", f"JSON- und Info-Datei gehören bei {code} nicht zusammen.")
            if not isinstance(entry.get("enabled", True), bool):
                raise RegistryError("BAD_REGISTRY", f"Ungültiger Aktivierungsstatus für {code}.")
            codes.add(code.casefold())
            setting_ids.add(setting_id)
        return data

    @property
    def entries(self) -> list[dict]:
        return deepcopy(self._load()["profiles"])

    @property
    def registration_status(self) -> str:
        data = self._load()
        if data.get("sync_source") == "printer_cloud":
            return self._cloud_snapshot(data)["printer_registration_status"]
        return str(data.get("printer_registration_status", "pending"))

    @property
    def sync_source(self) -> str:
        return str(self._load().get("sync_source", "local_profiles"))

    @property
    def printer(self) -> dict:
        return deepcopy(self._load().get("printer", {}))

    def printer_choices(self) -> list[dict]:
        """Remember endpoints for printers using this account's fixed mappings."""
        data = self._load()
        choices = deepcopy(data.get("printer_connections", []))
        current = data.get("printer", {})
        if current.get("ip") and not any(item.get("ip") == current["ip"] for item in choices):
            choices.insert(0, {"name": current.get("name", "K2 Pro"), "ip": current["ip"]})
        return choices

    def select_printer(self, name: str, address: str, *, save: bool = False) -> dict:
        """Probe a candidate without changing settings; commit only on success.

        A second printer must already provide the service and compatible stable
        mappings. This is an endpoint selection, never a remote installation.
        No password or Cloud token is involved in reading this public export.
        """
        name, address = str(name).strip(), str(address).strip()
        if not name or len(name) > 80 or any(ord(char) < 32 for char in name):
            raise RegistryError("BAD_CONNECTION", "Bitte eine Druckerbezeichnung mit höchstens 80 Zeichen eingeben.")
        try:
            ip = ipaddress.IPv4Address(address)
            if ip.is_unspecified or ip.is_multicast or ip.is_loopback or int(ip) == 0xFFFFFFFF:
                raise ValueError("Keine Druckeradresse")
        except ValueError as exc:
            raise RegistryError("BAD_CONNECTION", "Bitte die IPv4-Adresse des Druckers eingeben, zum Beispiel 192.0.2.10; ohne http:// oder Port.") from exc
        before = self._load()
        if before.get("sync_source") != "printer_cloud":
            raise RegistryError("BAD_CONNECTION", "Die Druckerauswahl benötigt eine eingerichtete Drucker-Profilzuordnung.")
        candidate = deepcopy(before)
        candidate["printer"].update(name=name, ip=str(ip))
        candidate["cloud_materials_url"] = f"http://{ip}:4408/server/files/config/cfs_cloud_profiles/tag-materials.json"
        # Material-code bindings belong to one printer, not to the whole UI.
        # A previously paired endpoint retains its own immutable bindings.
        other_printer = str(ip) != before["printer"]["ip"]
        saved_choice = next((item for item in self.printer_choices() if item["ip"] == str(ip)), {})
        scope = saved_choice.get("profile_scope", {}) if other_printer else before
        if other_printer:
            candidate["profiles"] = deepcopy(scope.get("profiles", []))
            candidate["cloud_account_id"] = scope.get("cloud_account_id")
            candidate["printer"].pop("mac", None)
        snapshot = self._cloud_snapshot(candidate, fresh=True, adopt=False, remember=False)
        account = candidate.get("cloud_account_id")
        incoming_account = str(snapshot.get("account_id", ""))
        if snapshot.get('schema_version',1)==1 and (not re.fullmatch(r"[0-9]+", incoming_account) or (account and incoming_account != str(account))):
            raise RegistryError("WRONG_ACCOUNT", "Dieser Drucker liefert Profile eines anderen oder unbekannten Cloud-Kontos. Die bestehende Verbindung wurde nicht geändert.")
        account = snapshot.get('account_id') if snapshot.get('schema_version')==2 else incoming_account
        candidate["cloud_account_id"] = account
        if snapshot.get('schema_version')==2:candidate['profile_backend_version']=2
        if snapshot.get("printer_int_name"):
            candidate["printer"]["printer_int_name"] = snapshot["printer_int_name"]
            candidate["printer"]["nozzle_diameter"] = snapshot["nozzle_diameter"]
        if snapshot["printer_registration_status"] != "installed":
            raise RegistryError("PRINTER_NOT_READY", "Der Profildienst dieses Druckers ist noch nicht fertig eingerichtet. Die bestehende Verbindung wurde nicht geändert.")
        known = {entry["material_id"] for entry in candidate["profiles"]}
        for code, profile in snapshot["profiles"].items():
            if code not in known:
                candidate["profiles"].append({"material_id": code,
                    "profile_setting_id": profile["profile_setting_id"], "name": profile["name"],
                    "source_file": profile["source_file"], "enabled": True, "source": "printer_cloud",
                    **({'source_identity':profile['identity']} if 'identity' in profile else {})})
        result = {"name": name, "ip": str(ip), "account_id": account,
                  "profile_count": len(snapshot["profiles"]), "saved": False,
                  "model": snapshot.get("printer_int_name", "")}
        result["materials"] = [self._resolve_cloud(entry, snapshot)["material"]
                               for entry in candidate["profiles"] if entry.get("enabled", True) and entry['material_id'] in snapshot['profiles']]
        if save:
            with self._cloud_lock, self._locked():
                if self._load() != before:
                    raise RegistryError("SOURCE_CHANGED", "Die Zuordnung wurde während des Verbindungstests geändert. Bitte erneut verknüpfen.")
                choices = [item for item in self.printer_choices() if item["ip"] not in (str(ip), before["printer"]["ip"])]
                if other_printer:
                    choices.append({"name": before["printer"].get("name", "K2 Pro"), "ip": before["printer"]["ip"],
                        "printer_int_name": before["printer"].get("printer_int_name", ""), "nozzle_diameter": before["printer"].get("nozzle_diameter", ""),
                        "profile_scope": {"profiles": deepcopy(before["profiles"]), "cloud_account_id": before.get("cloud_account_id")}})
                choices.append({"name": name, "ip": str(ip),
                    "printer_int_name": candidate["printer"].get("printer_int_name", ""), "nozzle_diameter": candidate["printer"].get("nozzle_diameter", ""), "profile_scope": {
                    "profiles": deepcopy(candidate["profiles"]), "cloud_account_id": account}})
                candidate["printer_connections"] = choices
                self._save(candidate)
                self._cloud_cache, self._cloud_cache_key, self._cloud_cache_at = None, None, 0.0
            result["saved"] = True
        return result

    @contextmanager
    def _locked(self):
        lock_path = self.path.with_name(self.path.name + ".lock")
        try:
            with lock_path.open("a+", encoding="utf-8") as stream:
                with locked_file(stream):
                    yield
        except OSError as exc:
            raise RegistryError("REGISTRY_WRITE", f"Profilzuordnung kann nicht aktualisiert werden: {self.path}") from exc

    def _save(self, data: dict):
        temporary = None
        try:
            mode = self.path.stat().st_mode & 0o777
            old_raw=self.path.read_bytes()
            if data.get('profile_backend_version')==2 and json.loads(old_raw).get('profile_backend_version')!=2:
                backup=self.path.with_name(self.path.stem+'.pre-v2.json')
                try:
                    with backup.open('xb') as preserved:
                        preserved.write(old_raw);preserved.flush();os.fsync(preserved.fileno())
                    backup.chmod(0o600)
                except FileExistsError:pass
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".profil-zuordnung-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(mode)
            temporary.replace(self.path)
        except OSError as exc:
            raise RegistryError("REGISTRY_WRITE", f"Profilzuordnung konnte nicht sicher gespeichert werden: {self.path}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def set_registration_status(self, status: str, *, details: dict | None = None):
        if status not in ("pending", "installed"):
            raise RegistryError("BAD_REGISTRY", "Druckerstatus muss pending oder installed sein.")
        with self._locked():
            data = self._load()
            data["printer_registration_status"] = status
            data["printer_registration_updated_at"] = datetime.now(timezone.utc).isoformat()
            if details is not None:
                data["printer_registration_details"] = details
            self._save(data)

    def set_profile_activity(self, bindings, enabled):
        with self._cloud_lock, self._locked():
            data = self._load()
            by_code = {entry['material_id']: entry for entry in data['profiles']}
            for row in bindings:
                entry = by_code.get(row['material_id'])
                if entry is not None:
                    if entry['profile_setting_id'] != row['profile_setting_id']:
                        raise RegistryError('COLLISION', 'Die bestätigte Profilzuordnung passt nicht zur lokalen Zuordnung')
                    entry['enabled'] = bool(enabled)
            self._save(data)
            self._cloud_cache = None

    def _remember_source(self, entry: dict, name: str, source: Path, info: Path):
        updates = {"name": name, "source_file": str(source), "info_file": str(info)}
        if all(entry.get(key) == value for key, value in updates.items()):
            return
        with self._locked():
            data = self._load()
            current = next((item for item in data["profiles"] if item["profile_setting_id"] == entry["profile_setting_id"]), None)
            if current is None or current["material_id"] != entry["material_id"]:
                raise RegistryError("COLLISION", "Die feste Profilzuordnung wurde während des Lesens geändert.")
            current.setdefault("original_name", entry["name"])
            current.setdefault("original_source_file", entry["source_file"])
            current.update(updates)
            self._save(data)

    def _cloud_snapshot(self, data: dict | None = None, *, fresh: bool = False,
                        adopt: bool = True, remember: bool = True) -> dict:
        """Fetch one bounded public export; never fall back to local profiles.

        The two-second in-memory cache only avoids repeated requests while a
        batch is resolved. Selection/write preparation calls fresh=True.
        """
        data = self._load() if data is None else data
        url = data.get("cloud_materials_url", "")
        try:
            parsed = urllib.parse.urlsplit(url)
            printer_ip = str(data.get("printer", {}).get("ip", ""))
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.hostname != printer_ip:
                raise ValueError("Die Snapshot-Adresse muss zum registrierten Drucker gehören.")
            if parsed.username or parsed.password or parsed.fragment:
                raise ValueError("Die Snapshot-Adresse darf keine Zugangsdaten oder URL-Fragmente enthalten.")
        except (TypeError, ValueError) as exc:
            raise RegistryError("BAD_REGISTRY", "Ungültige Cloud-Snapshot-Adresse in der Profilzuordnung.") from exc
        known = {entry["material_id"]: entry for entry in data["profiles"]}
        known_setting_ids = {entry["profile_setting_id"]: entry["material_id"] for entry in data["profiles"]}
        expected = {code: entry for code, entry in known.items() if entry.get("enabled", True)}
        key = (url, tuple(sorted((code, entry["profile_setting_id"]) for code, entry in expected.items())))
        with self._cloud_lock:
            if remember and not fresh and self._cloud_cache is not None and self._cloud_cache_key == key and time.monotonic() - self._cloud_cache_at < 2.0 and self._cloud_cache.get("valid_until_epoch", float("inf")) > time.time():
                return deepcopy(self._cloud_cache)
            try:
                request = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(request, timeout=3.0) as response:
                    raw = response.read(16_000_001)
                if len(raw) > 16_000_000:
                    raise ValueError("Der Cloud-Snapshot ist unerwartet groß.")
                snapshot = json.loads(raw.decode("utf-8-sig"))
            except Exception as exc:
                # A prior cache may remain available for a displayed batch,
                # but a fresh request always raises instead of reusing it.
                from cfs_connection_errors import network_issue
                if isinstance(exc,urllib.error.HTTPError) and exc.code==404:
                    message='Der Profildienst wurde unter dieser IP nicht gefunden. Drucker-IP prüfen und den Zusatzdienst in der Einrichtung prüfen bzw. installieren.'
                else:message=str(network_issue(exc,printer_ip))
                raise RegistryError("CLOUD_UNAVAILABLE",message+" Es wurde kein Tag geschrieben.") from exc
            if not isinstance(snapshot, dict) or (snapshot.get("schema_version"),snapshot.get("source")) not in ((1,"printer_cloud"),(2,"printer_profiles")) or not isinstance(snapshot.get("profiles"), list):
                raise RegistryError("BAD_CLOUD_SNAPSHOT", "Der Drucker liefert keinen unterstützten Cloud-Profil-Snapshot.")
            mixed=snapshot.get('schema_version')==2
            status = snapshot.get("printer_registration_status")
            if status not in ("pending", "installed"):
                raise RegistryError("BAD_CLOUD_SNAPSHOT", "Im Cloud-Snapshot fehlt ein eindeutiger Status der Druckereinrichtung.")
            expires = None
            if mixed and not {'generated_at','valid_until'}.issubset(snapshot):
                raise RegistryError('STALE_CLOUD_SNAPSHOT','Dem Profilkatalog fehlt ein bestätigter Gültigkeitszeitraum.')
            if "generated_at" in snapshot or "valid_until" in snapshot:
                try:
                    generated = datetime.fromisoformat(snapshot["generated_at"].replace("Z", "+00:00"))
                    valid_until = datetime.fromisoformat(snapshot["valid_until"].replace("Z", "+00:00"))
                    if generated.tzinfo is None or valid_until.tzinfo is None or generated >= valid_until:
                        raise ValueError("Ungültiger Gültigkeitszeitraum")
                    expires = valid_until.timestamp()
                    if expires <= time.time() or generated.timestamp() > time.time() + 60:
                        raise ValueError("Der Snapshot ist abgelaufen oder liegt in der Zukunft")
                except (KeyError, AttributeError, TypeError, ValueError) as exc:
                    raise RegistryError("STALE_CLOUD_SNAPSHOT", "Die Cloud-Profilübersicht des Druckers ist nicht mehr aktuell. Bitte die Druckersynchronisierung prüfen und erneut laden.") from exc
            validated, setting_ids, names = {}, set(), set()
            for profile in snapshot["profiles"]:
                if not isinstance(profile, dict):
                    raise RegistryError("BAD_CLOUD_SNAPSHOT", "Ungültiger Eintrag im Cloud-Snapshot.")
                code = profile.get("material_id")
                if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9]{5}", code) or code in validated:
                    raise RegistryError("COLLISION", "Der Cloud-Snapshot enthält unbekannte oder doppelte Materialcodes.")
                setting_id = profile.get("profile_setting_id")
                if not isinstance(setting_id, str) or not setting_id.strip() or setting_id in setting_ids:
                    raise RegistryError("COLLISION", f"Der Cloud-Code {code} gehört nicht zur fest zugeordneten Profil-ID.")
                if code in known and setting_id != known[code]["profile_setting_id"]:
                    raise RegistryError("COLLISION", f"Der Cloud-Code {code} gehört nicht zur fest zugeordneten Profil-ID.")
                if setting_id in known_setting_ids and known_setting_ids[setting_id] != code:
                    raise RegistryError("COLLISION", "Eine bestehende Cloud-Profil-ID darf keinen anderen Materialcode erhalten.")
                if code not in known and (not re.fullmatch(r"99\d{3}", code) or not re.fullmatch(r"[0-9a-f]{24}", setting_id)
                                          or code.casefold() in {item["id"].casefold() for item in DEFAULT_MATERIALS}):
                    raise RegistryError("COLLISION", "Ein neuer Cloud-Materialcode oder seine Profil-ID ist ungültig bzw. reserviert.")
                for field in ("name", "brand", "type", "source_file"):
                    if not isinstance(profile.get(field), str) or not profile[field].strip():
                        raise RegistryError("BAD_CLOUD_SNAPSHOT", f"Dem Cloud-Profil {code} fehlt {field}.")
                if not mixed and profile["name"].casefold() in names:
                    raise RegistryError("COLLISION", "Mehrere Cloud-Profile haben denselben Namen.")
                color = profile.get("color")
                if not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
                    raise RegistryError("BAD_CLOUD_SNAPSHOT", f"Das Cloud-Profil {code} enthält keine gültige RGB-Farbe.")
                if not isinstance(profile.get("resolved"), dict) or profile["resolved"].get("name") != profile["name"]:
                    raise RegistryError("BAD_CLOUD_SNAPSHOT", f"Die aufgelösten Cloud-Werte von {code} passen nicht zum Profilnamen.")
                metadata = profile.get("profile_metadata", {})
                if not isinstance(metadata, dict) or any(value is not None and not isinstance(value, (str, int, float)) for value in metadata.values()):
                    raise RegistryError("BAD_CLOUD_SNAPSHOT", f"Ungültige Druckparameter-Anzeige im Cloud-Profil {code}.")
                if mixed:
                    identity=profile.get('identity')
                    if not isinstance(identity,str) or not re.fullmatch(r'(?:local:[0-9a-f]{32}|cloud:[0-9]+:[0-9a-f]{24})',identity):
                        raise RegistryError('BAD_CLOUD_SNAPSHOT','Dauerhafte Profilherkunft fehlt.')
                    kind=profile['origin'] if 'origin' in profile else None
                    state=profile.get('update_status')
                    valid_states={'local':('local_current','slicer_current'),'cloud':('cloud_cache_current','cached_cloud','slicer_current'),'imported':('imported_snapshot','slicer_current')}
                    if state=='slicer_current':
                        from cfs_slicer_policy import validate_source,cloud_reference
                        source=validate_source(profile.get('slicer_source'))
                        if profile.get('values_source')!='slicer' or (kind=='cloud' and cloud_reference(source)!=identity):
                            raise RegistryError('BAD_CLOUD_SNAPSHOT','Slicer-Vorrang und Profilherkunft widersprechen sich.')
                    if state not in valid_states.get(kind,()):
                        raise RegistryError('BAD_CLOUD_SNAPSHOT','Aktualisierungsstatus oder Profilherkunft fehlt.')
                    expected_identity=('local:'+str(profile.get('origin_setting_id')) if kind=='local' else
                        'cloud:'+str(profile.get('origin_account_id'))+':'+str(profile.get('origin_setting_id')))
                    if identity!=expected_identity or (kind=='local' and profile.get('origin_account_id') is not None):
                        raise RegistryError('BAD_CLOUD_SNAPSHOT','Profilherkunft und dauerhafte Identität widersprechen sich.')
                    prior=known.get(code,{})
                    if prior.get('source_identity') and prior['source_identity']!=identity:
                        raise RegistryError('COLLISION','Eine bestehende Profilherkunft darf nicht geändert werden.')
                    if profile.get('origin') not in ('local','cloud','imported') or (profile['origin']=='local')!=identity.startswith('local:'):
                        raise RegistryError('BAD_CLOUD_SNAPSHOT','Widersprüchliche lokale bzw. Cloud-Herkunft.')
                item = deepcopy(profile)
                item["color"] = color.upper()
                item["profile_metadata"] = {key: "" if value is None else str(value) for key, value in metadata.items()}
                validated[code] = item
                setting_ids.add(setting_id)
                names.add(profile["name"].casefold())
            unavailable=snapshot.get('unavailable_profiles',[]) if mixed else []
            if not isinstance(unavailable,list):raise RegistryError('BAD_CLOUD_SNAPSHOT','Ungültige Liste nicht verfügbarer Profile.')
            blocked={}
            for p in unavailable:
                if not isinstance(p,dict) or not re.fullmatch(r'99[0-9]{3}',str(p.get('material_id',''))) or not re.fullmatch(r'[0-9a-f]{24}',str(p.get('profile_setting_id',''))) or p.get('material_id') in validated or p.get('material_id') in blocked or not isinstance(p.get('reason'),str):
                    raise RegistryError('BAD_CLOUD_SNAPSHOT','Unvollständiger Profilfehler.')
                if p.get('material_id') in known and p.get('profile_setting_id')!=known[p['material_id']]['profile_setting_id']:
                    raise RegistryError('COLLISION','Nicht verfügbare Profilkennung wurde verändert.')
                blocked[p.get('material_id')]=p
            if not set(expected).issubset(set(validated)|set(blocked)):
                raise RegistryError("MISSING_PROFILE", "Der Cloud-Snapshot enthält nicht alle fest zugeordneten Benutzerprofile. Schreiben bleibt gesperrt.")
            available = snapshot.get("available_profiles", [])
            if not isinstance(available, list):
                raise RegistryError("BAD_CLOUD_SNAPSHOT", "Die Liste neuer Cloud-Profile ist ungültig.")
            available_ids = set()
            for profile in available:
                if not isinstance(profile, dict) or not isinstance(profile.get("profile_setting_id"), str) or not re.fullmatch(r"[0-9a-fA-F]{24}", profile["profile_setting_id"]):
                    raise RegistryError("BAD_CLOUD_SNAPSHOT", "Ein neues Cloud-Profil hat keine gültige Profil-ID.")
                sid = profile["profile_setting_id"]
                if sid in setting_ids or sid in known_setting_ids or sid in available_ids:
                    raise RegistryError("COLLISION", "Eine Cloud-Profil-ID ist zugleich registriert oder mehrfach verfügbar.")
                if profile.get("status", "unassigned") == "unassigned":
                    if any(not isinstance(profile.get(field), str) or not profile[field].strip() for field in ("name", "brand", "type", "source_file")):
                        raise RegistryError("BAD_CLOUD_SNAPSHOT", "Ein neues Cloud-Profil ist nicht vollständig beschrieben.")
                    if not isinstance(profile.get("color"), str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", profile["color"]):
                        raise RegistryError("BAD_CLOUD_SNAPSHOT", "Ein neues Cloud-Profil enthält keine gültige Farbe.")
                elif profile.get("status") != "cloud_pending":
                    raise RegistryError("BAD_CLOUD_SNAPSHOT", "Unbekannter Status eines neuen Cloud-Profils.")
                available_ids.add(sid)
            used = snapshot.get("used_material_ids", list(validated))
            if not isinstance(used, list) or any(not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9]{5}", code) for code in used) or len(set(used)) != len(used):
                raise RegistryError("BAD_CLOUD_SNAPSHOT", "Die Liste belegter Materialcodes ist ungültig.")
            used = sorted(set(used) | set(validated) | set(known))
            next_code = snapshot.get("next_material_id") if "next_material_id" in snapshot else next((str(n) for n in range(99021, 100000) if str(n) not in used), None)
            if next_code is not None and (not isinstance(next_code, str) or not re.fullmatch(r"99\d{3}", next_code) or next_code in used):
                raise RegistryError("BAD_CLOUD_SNAPSHOT", "Der nächste freie Materialcode ist ungültig oder bereits belegt.")
            if status == "installed" and adopt:
                self._adopt_cloud_profiles(data, validated)
                current = self._load()
                key = (url, tuple(sorted((entry["material_id"], entry["profile_setting_id"]) for entry in current["profiles"] if entry.get("enabled", True))))
            result = {"profiles": validated, "printer_registration_status": status,
                      'schema_version':snapshot.get('schema_version',1),'service_version':snapshot.get('service_version'),
                      'unavailable_profiles':deepcopy(unavailable),'cloud_status':snapshot.get('cloud_status'),
                      'cloud_account_id':snapshot.get('cloud_account_id'),'cloud_warning':snapshot.get('cloud_warning'),
                      'profile_source_mode':snapshot.get('profile_source_mode'),
                      "account_id": snapshot.get("account_id"),
                      'updates_deferred': bool(snapshot.get('updates_deferred',False)),
                      "printer_int_name": snapshot.get("printer_int_name"),
                      "nozzle_diameter": snapshot.get("nozzle_diameter"),
                      "available_profiles": deepcopy(available), "used_material_ids": used, "next_material_id": next_code}
            if expires is not None:
                result["valid_until_epoch"] = expires
            if remember:
                self._cloud_cache, self._cloud_cache_at, self._cloud_cache_key = deepcopy(result), time.monotonic(), key
            return result

    def _adopt_cloud_profiles(self, fetched_data: dict, profiles: dict):
        """Cache committed printer mappings without ever reassigning an ID."""
        known = {entry["material_id"]: entry for entry in fetched_data["profiles"]}
        additions = [profile for code, profile in profiles.items() if code not in known]
        if not additions and fetched_data.get('profile_backend_version')==2:
            return
        with self._locked():
            data = self._load()
            if data.get("sync_source") != "printer_cloud" or data.get("cloud_materials_url") != fetched_data.get("cloud_materials_url"):
                raise RegistryError("SOURCE_CHANGED", "Die Druckerquelle wurde während des Abrufs geändert. Bitte erneut laden.")
            by_code = {entry["material_id"]: entry for entry in data["profiles"]}
            by_setting = {entry["profile_setting_id"]: entry["material_id"] for entry in data["profiles"]}
            for code, profile in profiles.items():
                sid = profile["profile_setting_id"]
                if (code in by_code and by_code[code]["profile_setting_id"] != sid) or (sid in by_setting and by_setting[sid] != code):
                    raise RegistryError("COLLISION", "Eine bestehende Profilzuordnung wurde parallel geändert. Keine neue Zuordnung übernommen.")
            changed = False
            if any('identity' in profile for profile in profiles.values()) and data.get('profile_backend_version')!=2:
                data['profile_backend_version']=2;changed=True
                for entry in data['profiles']:
                    profile=profiles.get(entry['material_id'])
                    if profile and profile.get('identity'):entry['source_identity']=profile['identity']
            for profile in additions:
                code, sid = profile["material_id"], profile["profile_setting_id"]
                if code not in by_code:
                    entry = {"material_id":code, "profile_setting_id":sid, "name":profile["name"],
                             "source_file":profile["source_file"], "enabled":True, "source":"printer_cloud",
                             **({'source_identity':profile['identity']} if 'identity' in profile else {})}
                    data["profiles"].append(entry)
                    changed = True
            if changed:
                self._save(data)

    @property
    def profile_status(self):
        with self._cloud_lock:
            return deepcopy(self._cloud_cache or {})

    def cloud_catalog(self, *, fresh: bool = True) -> dict:
        if self.sync_source != "printer_cloud":
            raise RegistryError("BAD_REGISTRY", "Neue Cloud-Profil-IDs sind nur im Drucker-Cloud-Modus verfügbar.")
        return deepcopy(self._cloud_snapshot(fresh=fresh))

    def _resolve_cloud(self, entry: dict, snapshot: dict) -> dict:
        code = entry["material_id"]
        if code not in snapshot['profiles']:
            reason=next((p['reason'] for p in snapshot.get('unavailable_profiles',[]) if p['material_id']==code),'Profil fehlt im Druckerbestand.')
            raise RegistryError('MISSING_PROFILE',f'Profil {code} nicht verfügbar: {reason}')
        profile = deepcopy(snapshot["profiles"][code])
        resolved = profile["resolved"]
        from cfs_nozzles import manufacturer_value
        fingerprint = hashlib.sha256(json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        material = {
            "id": code, "name": profile["name"], "brand": profile["brand"], "type": profile["type"],
            "raw_brand": manufacturer_value({'resolved':resolved,'brand':profile['brand']}),
            "color": profile["color"], "source": "printer_cloud", "source_file": profile["source_file"],
            "origin": profile.get("origin", "cloud"),
            'update_status':profile.get('update_status','cloud_cache_current'),
            'values_source':profile.get('values_source'),
            'slicer_source':deepcopy(profile.get('slicer_source')),
            'update_reason':profile.get('update_reason',''),
            'source_identity':profile.get('identity'),
            'profile_source_mode':snapshot.get('profile_source_mode'),
            'cloud_status':snapshot.get('cloud_status'),
            'updates_deferred': bool(snapshot.get('updates_deferred',False)),
            "profile_metadata": deepcopy(profile["profile_metadata"]),
            "mapping_status": "registry_assigned", "registry_managed": True,
            "registry_material_id": code, "profile_setting_id": entry["profile_setting_id"],
            "registry_registration_status": snapshot["printer_registration_status"],
            "profile_fingerprint": fingerprint,
        }
        current_entry = {**entry, "name": profile["name"], "source_file": profile["source_file"]}
        return {"entry": current_entry, "source_file": profile["source_file"], "info_file": "",
                "profile": profile, "resolved": resolved, "material": material,
                "source_sha256": fingerprint, "profile_fingerprint": fingerprint, "sync_source": "printer_cloud"}

    def resolve(self, material_id: str) -> dict:
        data = self._load()
        if data.get("sync_source") == "printer_cloud":
            snapshot = self._cloud_snapshot(data)
            data = self._load()
            entry = next((item for item in data["profiles"] if item["material_id"] == material_id and item.get("enabled", True)), None)
            if entry is None:
                raise RegistryError("MISSING_PROFILE", f"Materialcode {material_id} ist keinem aktiven Benutzerprofil zugeordnet.")
            return self._resolve_cloud(entry, snapshot)
        entry = next((item for item in data["profiles"] if item["material_id"] == material_id), None)
        if entry is None or not entry.get("enabled", True):
            raise RegistryError("MISSING_PROFILE", f"Materialcode {material_id} ist keinem aktiven Benutzerprofil zugeordnet.")
        directory = _active_source_directory(entry)
        matches = [path for path in sorted(directory.glob("*.info"))
                   if read_profile_info(path).get("setting_id") == entry["profile_setting_id"]]
        if not matches:
            raise RegistryError("MISSING_PROFILE", f"Das Profil für Code {material_id} fehlt im aktiven Profilordner {directory}.")
        if len(matches) != 1:
            raise RegistryError("COLLISION", f"Die Profil-ID für Code {material_id} kommt im aktiven Profilordner mehrfach vor.")
        info_path = matches[0].resolve()
        source_path = info_path.with_suffix(".json")
        try:
            source_bytes, info_bytes = source_path.read_bytes(), info_path.read_bytes()
            profile = json.loads(source_bytes)
        except (OSError, ValueError) as exc:
            raise RegistryError("MISSING_PROFILE", f"Benutzerprofil ist nicht vollständig lesbar: {source_path}") from exc
        if not isinstance(profile, dict) or not _is_slicer_profile(profile):
            raise RegistryError("BAD_PROFILE", f"Kein gültiges Benutzerprofil: {source_path}")
        material = _slicer_material(profile, source_path)
        if material["id"] and material["id"] != material_id:
            raise RegistryError("COLLISION", f"Code {material_id} und der Code in den Profilnotizen widersprechen sich.")
        name = material["name"]
        if not name:
            raise RegistryError("BAD_PROFILE", f"Der Profilname fehlt: {source_path}")
        if any(other["material_id"] != material_id and other.get("enabled", True)
               and other["name"].casefold() == name.casefold() for other in data["profiles"]):
            raise RegistryError("COLLISION", f"Der Profilname {name} gehört zu mehr als einer festen Zuordnung.")
        resolved = _resolve_slicer(profile, source_path)
        if source_path.read_bytes() != source_bytes or info_path.read_bytes() != info_bytes:
            raise RegistryError("SOURCE_CHANGED", "Das Profil wurde während des Lesens gespeichert. Bitte erneut versuchen.")
        self._remember_source(entry, name, source_path, info_path)
        current_entry = {**entry, "name": name, "source_file": str(source_path), "info_file": str(info_path)}
        fingerprint = hashlib.sha256(json.dumps(resolved, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        material.update({
            "id": material_id, "mapping_status": "registry_assigned", "registry_managed": True,
            "registry_material_id": material_id, "profile_setting_id": entry["profile_setting_id"],
            "registry_registration_status": str(data.get("printer_registration_status", "pending")),
            "profile_fingerprint": fingerprint,
        })
        return {"entry": current_entry, "source_file": str(source_path), "info_file": str(info_path),
                "profile": profile, "resolved": resolved, "material": material,
                "source_sha256": hashlib.sha256(source_bytes).hexdigest(), "profile_fingerprint": fingerprint}

    def resolve_all(self) -> list[dict]:
        data = self._load()
        if data.get("sync_source") == "printer_cloud":
            snapshot = self._cloud_snapshot(data, fresh=True)
            return [self._resolve_cloud(entry, snapshot) for entry in self.entries if entry.get("enabled", True) and entry['material_id'] in snapshot['profiles']]
        resolved = [self.resolve(entry["material_id"]) for entry in self.entries if entry.get("enabled", True)]
        names = [item["material"]["name"].casefold() for item in resolved]
        if len(set(names)) != len(names):
            raise RegistryError("COLLISION", "Mehrere registrierte Benutzerprofile haben denselben Namen.")
        return resolved

    def materials(self) -> list[dict]:
        return [item["material"] for item in self.resolve_all()]

    def material_for_source(self, source: str | Path) -> dict | None:
        if self.sync_source == "printer_cloud":
            # A local JSON file is never allowed to replace cloud parameters.
            return None
        info = Path(source).with_suffix(".info")
        if not info.is_file():
            return None
        setting_id = read_profile_info(info).get("setting_id")
        entries = [entry for entry in self.entries if entry.get("enabled", True) and entry["profile_setting_id"] == setting_id]
        if not entries:
            return None
        if len(entries) != 1:
            raise RegistryError("COLLISION", "Die importierte Profil-ID ist mehrfach registriert.")
        return self.resolve(entries[0]["material_id"])["material"]

    def refresh_material(self, material: dict) -> dict:
        if material.get("registry_managed"):
            code = material.get("registry_material_id", material.get("id", ""))
            data = self._load()
            if data.get("sync_source") == "printer_cloud":
                entry = next((entry for entry in data["profiles"] if entry["material_id"] == str(code) and entry.get("enabled", True)), None)
                if entry is None:
                    raise RegistryError("MISSING_PROFILE", "Dieses Cloud-Profil ist nicht mehr fest zugeordnet.")
                result = self._resolve_cloud(entry, self._cloud_snapshot(data, fresh=True))["material"]
            else:
                result = self.resolve(str(code))["material"]
            if result["profile_setting_id"] != material.get("profile_setting_id"):
                raise RegistryError("COLLISION", "Der feste Materialcode gehört inzwischen zu einer anderen Profil-ID.")
            return result
        if material.get("source") == "slicer" and material.get("source_file"):
            registered = self.material_for_source(material["source_file"])
            if registered is not None:
                return registered
        return material
