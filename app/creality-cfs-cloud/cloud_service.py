#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Printer-local CFS aliases from Creality's native cloud cache (Python 3.9)."""
import argparse
import base64
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import tempfile
import threading
import time
import urllib.request

from cloud_alias_core import build_aliases, SyncError, DeferredSyncError
from cfs_transfer_core import plan_import, plan_delete, digest as transfer_digest
from cfs_versions import SERVICE_VERSION

DEFAULT_CONFIG = "/mnt/UDISK/printer_data/config/cfs_cloud_profiles"
DEFAULT_DATABASE = "/mnt/UDISK/creality/userdata/box/material_database.json"
DEFAULT_CLOUD_ROOT = "/mnt/UDISK/creality/userdata/box/usrMaterial"
NATIVE_ROOT = DEFAULT_CLOUD_ROOT + "/"
SID_RE = re.compile(r"[0-9a-f]{24}$")
CODE_RE = re.compile(r"99[0-9]{3}$")
PATH_RE = re.compile(re.escape(NATIVE_ROOT) + r"([0-9]+)/([0-9a-f]{24})-(0|[1-9][0-9]*)$")


class ServiceError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def utc(timestamp):
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def read_raw(path, optional=False, limit=16_000_000):
    path = Path(path)
    try:
        descriptor = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        if optional:
            return None
        raise ServiceError("SOURCE_MISSING", "Datei noch nicht vorhanden: " + str(path))
    except OSError as exc:
        raise ServiceError("SOURCE_UNAVAILABLE", "Datei nicht sicher lesbar: " + str(path)) from exc
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ServiceError("SOURCE_INVALID", "Keine reguläre Datei: " + str(path))
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ServiceError("SOURCE_INVALID", "Datei überschreitet das Größenlimit: " + str(path))
    return raw


def decoded(raw, context):
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeError, AttributeError) as exc:
        raise ServiceError("SOURCE_INVALID", "JSON noch nicht vollständig lesbar: " + str(context)) from exc


def fsync_directory(path):
    descriptor = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path, raw, before_replace=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.stat() if path.exists() else None
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fchmod(stream.fileno(), stat.S_IMODE(existing.st_mode) if existing else 0o600)
            if existing and os.geteuid() == 0:
                os.fchown(stream.fileno(), existing.st_uid, existing.st_gid)
            os.fsync(stream.fileno())
        if before_replace:
            before_replace()
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class CloudService:
    def __init__(self, config=DEFAULT_CONFIG, database=DEFAULT_DATABASE,
                 index=None, cloud_root=DEFAULT_CLOUD_ROOT, ready_check=None,
                 clock=time.time, interval=15, ttl=60, before_commit=None, hardware_check=None):
        self.config = Path(config).resolve()
        self.database = Path(database).resolve()
        self.cloud_root = Path(cloud_root).resolve()
        self.index = Path(index or self.cloud_root / "userMaterial.json").resolve()
        self.manifest = self.config / "manifest.json"
        self.receipt = self.config / "receipt.json"
        self.export = self.config / "tag-materials.json"
        self.journal = self.config / "transaction.json"
        self.ready_check = ready_check or self.printer_ready
        self.clock, self.interval, self.ttl = clock, interval, ttl
        self.before_commit = before_commit
        self.busy_check = self.printer_busy
        self.hardware_check=hardware_check or self.verify_nozzle

    @staticmethod
    def verify_nozzle(manifest):
        try:
            with urllib.request.urlopen('http://127.0.0.1:4408/printer/objects/query?configfile',timeout=3) as response:
                status=json.loads(response.read(1_000_001).decode())['result']['status']
            nozzle=str(status['configfile']['settings']['extruder']['nozzle_diameter'])
        except (OSError,ValueError,KeyError,TypeError) as error:
            raise ServiceError('HARDWARE_UNAVAILABLE','Aktuelle Düse ist nicht sicher prüfbar; keine Profiländerung ausgeführt.') from error
        if nozzle!=manifest['nozzle_diameter']:
            raise ServiceError('NOZZLE_CHANGED','Aktuelle Düse '+nozzle+' mm passt nicht zum eingerichteten Profilbestand ('+manifest['nozzle_diameter']+' mm).')

    @staticmethod
    def printer_ready():
        request = urllib.request.Request(
            "http://127.0.0.1:4408/printer/objects/query?webhooks&print_stats",
            headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                result = json.loads(response.read(1_000_001).decode("utf-8"))
            status = result["result"]["status"]
            return (status["webhooks"]["state"] == "ready" and
                    status["print_stats"]["state"] in ("standby", "complete", "cancelled"))
        except (OSError, ValueError, KeyError, TypeError):
            return False

    @staticmethod
    def printer_busy():
        try:
            with urllib.request.urlopen('http://127.0.0.1:4408/printer/objects/query?webhooks&print_stats', timeout=3) as response:
                status = json.load(response)['result']['status']
            return status['webhooks']['state'] == 'ready' and status['print_stats']['state'] in ('printing','paused')
        except Exception:
            return False

    def refresh_committed_snapshot(self):
        """Serve verified committed material values while catalog writes wait."""
        if not self.busy_check():
            raise ServiceError('PRINTER_BUSY','Drucker ist nicht bereit; keine Aktualisierung ausgeführt')
        watched = {path: read_raw(path) for path in (self.database,self.manifest,self.receipt,self.export)}
        database, manifest, receipt, export = [decoded(watched[path],path) for path in (self.database,self.manifest,self.receipt,self.export)]
        self.hardware_check(manifest)
        expected = {p['material_id']:p['profile_setting_id'] for p in manifest['profiles'] if p.get('enabled',True)}
        expected.update({p['material_id']:p['profile_setting_id'] for p in manifest.get('imported_profiles',[])})
        profiles = export.get('profiles',[])
        published={p['material_id']:p['profile_setting_id'] for p in profiles}
        published.update({p['material_id']:p['profile_setting_id'] for p in export.get('unavailable_profiles',[])})
        if published != expected:
            raise ServiceError('SOURCE_CHANGED','Bestätigte Profilübersicht passt nicht zur Zuordnung')
        for profile in profiles:
            code = profile['material_id']
            rows = [r for r in database['result']['list'] if r.get('base',{}).get('id') == code]
            owned = receipt.get('owned_entries',{}).get(code)
            if len(rows) != 1 or owned is None or transfer_digest(rows[0]) != transfer_digest(owned) or transfer_digest(rows[0]) != transfer_digest(profile.get('record')):
                raise ServiceError('SOURCE_CHANGED','Bestätigter Materialeintrag wurde geändert; keine veralteten Werte anzeigen')
        now = self.clock()
        export.update(generated_at=utc(now), valid_until=utc(now+self.ttl), service_version=SERVICE_VERSION,
            database_sha256=sha(watched[self.database]), receipt_sha256=sha(watched[self.receipt]), updates_deferred=True)
        atomic_write(self.export,encoded(export),lambda:self.compare(watched))
        self.export.chmod(0o644)
        return {'success':True,'status':'deferred_printing','database_changed':False,'registered_profiles':len(profiles),'updates_deferred':True}

    @contextlib.contextmanager
    def locked(self):
        self.config.mkdir(parents=True, exist_ok=True)
        locks = []
        try:
            # The DB lock is shared with the previous host-side synchronizer.
            for path in (self.config / "service.lock", Path(str(self.database) + ".cfs-sync.lock")):
                descriptor = os.open(str(path), os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
                locks.append(descriptor)
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise ServiceError("BUSY", "Die Profilsynchronisierung arbeitet gerade; bitte erneut versuchen.") from exc
            yield
        finally:
            for descriptor in reversed(locks):
                os.close(descriptor)

    def check_ready(self):
        if not self.ready_check():
            raise ServiceError("PRINTER_BUSY", "Der Drucker muss bereit sein; während eines Druckauftrags wird gewartet.")

    @staticmethod
    def compare(expected):
        for path, raw in expected.items():
            if sha(read_raw(path, optional=raw is None)) != sha(raw):
                raise ServiceError("SOURCE_CHANGED", "Quelldaten wurden gleichzeitig verändert; keine veralteten Werte übernehmen.")

    def guard(self, expected):
        self.check_ready()
        self.compare(expected)

    def load(self):
        from cfs_mixed_core import migrate_manifest
        watched={path:read_raw(path,optional=path==self.receipt)
                 for path in (self.database,self.manifest,self.receipt)}
        index_error=''
        try:watched[self.index]=read_raw(self.index,optional=True)
        except ServiceError:index_error='Nativer Cloudindex ist nicht sicher lesbar.' 
        old_manifest=decoded(watched[self.manifest],self.manifest)
        receipt=decoded(watched[self.receipt],self.receipt) if watched[self.receipt] else None
        manifest=migrate_manifest(old_manifest,receipt)
        self.cloud_issue=index_error
        try:
            index=decoded(watched[self.index],self.index) if watched.get(self.index) else []
            if not isinstance(index,list):raise ValueError('Cloudindex ist unvollständig.')
        except (ServiceError,ValueError):
            index=[];self.cloud_issue='Nativer Cloudindex fehlt oder ist noch unvollständig.'
        cloud_files={}
        accounts=set()
        for item in index:
            path=item.get('path') if isinstance(item,dict) else None
            match=PATH_RE.fullmatch(path) if isinstance(path,str) else None
            version=item.get('version') if isinstance(item,dict) else None
            if not match or isinstance(version,bool) or not re.fullmatch(r'[0-9]+',str(version)):
                self.cloud_issue='Cloudindex enthält vorübergehend unvollständige Angaben.'
                continue
            accounts.add(match.group(1))
            local_path=self.cloud_root/match.group(1)/(match.group(2)+'-'+match.group(3))
            if local_path.parent.is_symlink() or local_path.is_symlink():
                self.cloud_issue='Unsicherer Cloudpfad wurde nicht gelesen.';continue
            try:
                raw=read_raw(local_path,optional=True,limit=4_000_000);watched[local_path]=raw
                if raw is not None:cloud_files[path]=decoded(raw,local_path)
            except ServiceError:
                self.cloud_issue='Eine native Clouddatei ist noch unvollständig.'
        if len(accounts)>1:self.cloud_issue='Cloudkonto im nativen Index ist noch nicht eindeutig.'
        return decoded(watched[self.database],self.database),index,cloud_files,manifest,receipt,watched

    def build(self,database,index,files,manifest,receipt):
        from cfs_mixed_core import build_mixed
        return build_mixed(database,index,files,manifest,receipt,getattr(self,'cloud_issue',''))

    @staticmethod
    def allocation(database, manifest, receipt):
        used = {str(item.get("base", {}).get("id", ""))
                for item in database.get("result", {}).get("list", []) if isinstance(item, dict)}
        used.update(profile["material_id"] for profile in manifest.get("profiles", []))
        used.update(profile["material_id"] for profile in manifest.get("imported_profiles", []))
        receipt = receipt or {}
        used.update(receipt.get("owned_entries", {}))
        used.update(receipt.get("profile_bindings", {}))
        used.update(receipt.get("reserved_material_ids", []))
        used.discard("")
        next_code = next((str(code) for code in range(99021, 100000) if str(code) not in used), None)
        return sorted(used), next_code

    def backup(self, raw):
        folder = self.config / "backups"
        folder.mkdir(exist_ok=True)
        original = folder / "original-material_database.json"
        if not original.exists():
            atomic_write(original, raw)
        stamp = datetime.datetime.fromtimestamp(self.clock(), datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        atomic_write(folder / (stamp + "-" + sha(raw)[:12] + ".json"), raw)
        backups = sorted(path for path in folder.glob("*.json") if path != original)
        for path in backups[:-20]:
            path.unlink()

    def recover(self):
        raw = read_raw(self.journal, optional=True)
        if raw is None:
            return
        journal = decoded(raw, self.journal)
        self.hardware_check(decoded(read_raw(self.manifest),self.manifest))
        allowed = {str(self.database), str(self.receipt), str(self.manifest)}
        if journal.get("schema_version") != 1 or not isinstance(journal.get("targets"), list):
            raise ServiceError("TRANSACTION_CONFLICT", "Unbekanntes Wiederherstellungsformat.")
        targets, expected = [], {}
        for record in journal["targets"]:
            if record.get("path") not in allowed:
                raise ServiceError("TRANSACTION_CONFLICT", "Unerwarteter Wiederherstellungspfad.")
            path = Path(record["path"])
            before = base64.b64decode(record["before"], validate=True) if record["before"] is not None else None
            after = base64.b64decode(record["after"], validate=True)
            current = read_raw(path, optional=before is None)
            if sha(current) not in (sha(before), sha(after)):
                raise ServiceError("TRANSACTION_CONFLICT", "Eine unvollständige Transaktion wurde extern verändert; sicher angehalten.")
            expected[path] = current
            targets.append((path, before, after))
        # Finish only the exact recorded transaction; never overwrite an
        # independently changed database. A fresh derivation follows immediately.
        self.check_ready()
        for path, before, after in targets:
            if expected[path] == after:
                continue
            atomic_write(path, after, lambda: self.guard(expected))
            expected[path] = after
        self.journal.unlink()
        fsync_directory(self.config)

    def commit(self, merged, receipt, report, export, manifest, watched):
        if len(encoded(merged)) > 16_000_000 or len(encoded(export)) > 16_000_000:
            raise ServiceError("CATALOG_TOO_LARGE", "Der Materialbestand überschreitet das unterstützte Größenlimit; kein Import ausgeführt.")
        old_database = decoded(watched[self.database], self.database)
        old_receipt = decoded(watched[self.receipt], self.receipt) if watched[self.receipt] else None
        old_manifest = decoded(watched[self.manifest], self.manifest)
        self.hardware_check(manifest)
        self.guard(watched)
        if old_manifest.get('schema_version')==1:
            backup=self.config/'backups'/'migration-schema-1.json'
            if not backup.exists():
                atomic_write(backup,encoded({'schema_version':1,'manifest':old_manifest,'receipt':old_receipt}),lambda:self.guard(watched))
        targets = []
        for path, old, new in ((self.database, old_database, merged),
                               (self.receipt, old_receipt, receipt),
                               (self.manifest, old_manifest, manifest)):
            if old != new:
                targets.append((path, watched[path], encoded(new)))
        self.guard(watched)
        if self.before_commit:
            self.before_commit()
        if targets:
            journal = {"schema_version": 1, "targets": [
                {"path": str(path), "before": base64.b64encode(before).decode("ascii") if before is not None else None,
                 "after": base64.b64encode(after).decode("ascii")}
                for path, before, after in targets]}
            atomic_write(self.journal, encoded(journal), lambda: self.guard(watched))
            if any(path == self.database for path, _, _ in targets):
                self.backup(watched[self.database])
            for path, before, after in targets:
                atomic_write(path, after, lambda: self.guard(watched))
                watched[path] = after
        # This is the only publisher. Installed means DB and receipt have both
        # committed and still match the current cache at the final CAS check.
        now = self.clock()
        export.update({"printer_registration_status": "installed", "generated_at": utc(now),
                       'service_version': SERVICE_VERSION,
                       "valid_until": utc(now + self.ttl), "poll_interval_seconds": self.interval,
                       "printer_int_name": manifest["printer_int_name"],
                       "nozzle_diameter": manifest["nozzle_diameter"],
                       "database_sha256": sha(watched[self.database]),
                       "receipt_sha256": sha(watched[self.receipt])})
        atomic_write(self.export, encoded(export), lambda: self.guard(watched))
        # This export contains material data only. The existing Moonraker file
        # endpoint must be able to serve it even if it runs without root.
        self.export.chmod(0o644)
        if self.journal.exists():
            self.journal.unlink()
            fsync_directory(self.config)
        report.update({"success": True, "status": "installed", "database_changed": old_database != merged})
        return report

    def run_once(self, register=None, material_id=None, import_bundle=None,
                 preview=False, expected_plan=None, delete_codes=None):
        if register is not None and not SID_RE.fullmatch(register):
            raise ServiceError("BAD_PROFILE_ID", "Die Cloud-Profil-ID muss aus 24 kleinen Hexadezimalzeichen bestehen.")
        if material_id is not None and not CODE_RE.fullmatch(material_id):
            raise ServiceError("BAD_MATERIAL_ID", "Eigene Materialcodes müssen genau fünfstellig im Bereich 99000–99999 liegen.")
        with self.locked():
            self.recover()
            if register is None and import_bundle is None and delete_codes is None and not self.ready_check():
                return self.refresh_committed_snapshot()
            database, index, files, manifest, receipt, watched = self.load()
            self.hardware_check(manifest)
            chosen, registration_status = None, None
            initial = self.build(database, index, files, manifest, receipt)
            transfer_rows, plan_token = None, None
            if delete_codes is not None:
                try:
                    manifest, database, transfer_rows = plan_delete(delete_codes, database, manifest, receipt)
                except (ValueError, TypeError, KeyError) as exc:
                    raise ServiceError('BAD_DELETE', str(exc)) from exc
                plan_token = transfer_digest({'inputs': {str(path): sha(raw) for path, raw in watched.items()},
                                              'delete_codes': delete_codes, 'plan': transfer_rows})
                if not preview and (not expected_plan or expected_plan != plan_token):
                    raise ServiceError('PLAN_CHANGED', 'Der Zielbestand hat sich geändert. Entfernung erneut prüfen.')
            if import_bundle is not None:
                try:
                    manifest, transfer_rows = plan_import(import_bundle, database, manifest, receipt, initial[3])
                except (ValueError, TypeError, KeyError) as exc:
                    raise ServiceError("BAD_IMPORT", str(exc)) from exc
                plan_token = transfer_digest({"inputs": {str(path): sha(raw) for path, raw in watched.items()},
                    "bundle": import_bundle, "plan": transfer_rows})
                if not preview and (not expected_plan or expected_plan != plan_token):
                    raise ServiceError("PLAN_CHANGED", "Der Importplan oder der Zielbestand hat sich geändert. Bitte Vorschau erneut laden.")
            if register is not None:
                existing = next((profile for profile in manifest["profiles"]
                                 if profile["profile_setting_id"] == register), None)
                if existing:
                    if material_id is not None and material_id != existing["material_id"]:
                        raise ServiceError("PERMANENT_BINDING", "Dieses Cloudprofil besitzt bereits einen anderen festen Materialcode.")
                    if not existing.get("enabled", True):
                        raise ServiceError("DISABLED_BINDING", "Dieses Profil bleibt unter seinem bisherigen Materialcode reserviert.")
                    chosen, registration_status = existing["material_id"], "already_registered"
                else:
                    available = next((item for item in initial[3].get("available_profiles", [])
                                      if item["profile_setting_id"] == register), None)
                    if not available or available.get("status") != "unassigned":
                        raise ServiceError("CLOUD_PENDING", "Das Cloudprofil ist noch nicht vollständig im nativen Druckerbestand verfügbar.")
                    used, next_code = self.allocation(database, manifest, receipt)
                    chosen = material_id or next_code
                    if chosen is None:
                        raise ServiceError("NO_FREE_CODE", "Der Materialcode-Bereich ist vollständig reserviert.")
                    if chosen in used:
                        raise ServiceError("CODE_IN_USE", "Dieser Materialcode ist bereits belegt oder dauerhaft reserviert.")
                    manifest["profiles"].append({"material_id": chosen, "profile_setting_id": register, "enabled": True,
                        'cloud_setting_id':available['cloud_setting_id'],'account_id':available['account_id']})
                    registration_status = "registered"
            merged, next_receipt, report, export = self.build(database, index, files, manifest, receipt)
            if import_bundle is not None and transfer_rows:
                unavailable={p['material_id']:p['reason'] for p in export.get('unavailable_profiles',[])}
                failed=[row for row in transfer_rows if row['material_id'] in unavailable]
                if failed:raise ServiceError('PROFILE_CONFLICT','Importprofil nicht sicher übertragbar: '+unavailable[failed[0]['material_id']])
            used, next_code = self.allocation(merged, manifest, next_receipt)
            previous_reserved = set((receipt or {}).get("reserved_material_ids", []))
            next_receipt["reserved_material_ids"] = sorted(previous_reserved | {
                code for code in used if CODE_RE.fullmatch(code)})
            export.update({"used_material_ids": used, "next_material_id": next_code})
            if (import_bundle is not None or delete_codes is not None) and preview:
                return {"success": True, "status": "preview", "plan_token": plan_token,
                        "plan": transfer_rows, "registered_profiles": len(export["profiles"])}
            result = self.commit(merged, next_receipt, report, export, manifest, watched)
            if import_bundle is not None or delete_codes is not None:
                result.update({"status": "imported" if import_bundle is not None else 'deleted', "plan": transfer_rows,
                    "plan_token": plan_token, "configuration_backup": {"schema_version": 1,
                        "manifest": manifest, "receipt": next_receipt}})
            if register is not None:
                result.update({"status": registration_status, "material_id": chosen,
                               "profile_setting_id": register,
                               "configuration_backup": {"schema_version": 1,
                                   "manifest": manifest, "receipt": next_receipt},
                               "message": "Cloudprofil ist unter dem festen Materialcode eingerichtet."})
            return result

    def uninstall(self):
        with self.locked():
            self.recover()
            watched = {path: read_raw(path) for path in (self.database, self.manifest, self.receipt)}
            database, manifest, receipt = [decoded(watched[path], path) for path in (self.database, self.manifest, self.receipt)]
            records = database.get('result', {}).get('list')
            owned = receipt.get('owned_entries')
            if not isinstance(records, list) or database['result'].get('count') != len(records) or not isinstance(owned, dict):
                raise ServiceError('BAD_UNINSTALL', 'Eigene Materialeinträge sind nicht eindeutig nachgewiesen')
            for code, expected in owned.items():
                if not isinstance(code,str) or not CODE_RE.fullmatch(code) or not isinstance(expected,dict) or expected.get('base',{}).get('id') != code:
                    raise ServiceError('BAD_UNINSTALL','Ungültiger Besitznachweis; keine ursprünglichen Materialeinträge entfernen')
                found = [row for row in records if row.get('base', {}).get('id') == code]
                if len(found) > 1 or (found and transfer_digest(found[0]) != transfer_digest(expected)):
                    raise ServiceError('OWNERSHIP_CONFLICT', 'Eigener Eintrag wurde extern geändert; keine Entfernung: '+code)
            self.guard(watched)
            database['result']['list'] = [row for row in database['result']['list'] if row['base']['id'] not in owned]
            database['result']['count'] = len(database['result']['list'])
            self.backup(watched[self.database])
            atomic_write(self.database, encoded(database), lambda: self.guard(watched))
            return {'success': True, 'status': 'uninstalled', 'service_version': SERVICE_VERSION,
                'configuration_backup': {'schema_version': 1, 'manifest': manifest, 'receipt': receipt},
                'remaining_records': database['result']['count']}


def error_result(exc):
    if isinstance(exc, ServiceError):
        code = exc.code
    elif isinstance(exc, DeferredSyncError):
        code = "CLOUD_PENDING"
    elif isinstance(exc, SyncError):
        code = "OWNERSHIP_CONFLICT"
    else:
        code = "SERVICE_ERROR"
    return {"success": False, "code": code, "message": str(exc)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Native Cloudprofile als feste CFS-Codes übernehmen")
    parser.add_argument('--version', action='version', version=SERVICE_VERSION)
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Verzeichnis mit manifest.json und receipt.json")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--run", action="store_true")
    action.add_argument("--once", action="store_true")
    action.add_argument("--register")
    action.add_argument("--import-profiles", action="store_true")
    action.add_argument('--delete-profiles', action='store_true')
    action.add_argument('--uninstall', action='store_true')
    parser.add_argument("--material-id")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--expected-plan")
    args = parser.parse_args(argv)
    if args.material_id and not args.register:
        parser.error("--material-id benötigt --register")
    if (args.preview or args.expected_plan) and not (args.import_profiles or args.delete_profiles):
        parser.error("--preview/--expected-plan benötigt --import-profiles oder --delete-profiles")
    service = CloudService(config=args.config)
    if not args.run:
        try:
            if args.uninstall:
                result = service.uninstall()
                print(json.dumps(result, ensure_ascii=False), flush=True)
                return 0
            payload = decoded(sys.stdin.buffer.read(8_000_001), "Transferdatei") if args.import_profiles or args.delete_profiles else None
            if args.delete_profiles and (not isinstance(payload, dict) or not isinstance(payload.get('material_ids'), list)):
                raise ServiceError('BAD_DELETE', 'Liste der zu entfernenden Profile fehlt')
            result = service.run_once(args.register, args.material_id, payload if args.import_profiles else None,
                args.preview, args.expected_plan, payload.get('material_ids') if args.delete_profiles else None)
        except Exception as exc:
            result = error_result(exc)
            print(result["message"], file=sys.stderr, flush=True)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0 if result["success"] else 1
    stop = threading.Event()
    for name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(name, lambda signum, frame: stop.set())
    last = None
    while not stop.is_set():
        try:
            result = service.run_once()
        except Exception as exc:
            result = error_result(exc)
        summary = {key: result[key] for key in ("success", "status", "code", "message", "changes", "new_count") if key in result}
        if summary != last:
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            last = summary
        stop.wait(service.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
