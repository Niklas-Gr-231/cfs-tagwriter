# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Merge registered, current slicer profiles into the actual printer catalog.

The default CLI only prepares files. Installing is explicit, uses a checked SSH
host key, backs up both locally and remotely, and compares the original bytes
immediately before an atomic replacement. It never runs G-code or restarts.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager,nullcontext
from copy import deepcopy
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import urllib.request
import uuid


HERE = Path(__file__).resolve().parent
REMOTE_DATABASE = "/mnt/UDISK/creality/userdata/box/material_database.json"


class SyncError(RuntimeError):
    def __init__(self,message,code=""):
        self.code=code
        super().__init__(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def scalar(value):
    if isinstance(value, list):
        if len(value) != 1:
            raise SyncError("Mehrere Extruderwerte sind für diese Zuordnung nicht unterstützt.")
        return scalar(value[0])
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    raise SyncError("Nicht unterstützter Profilwert: " + repr(value))


def make_record(template, profile, material_id):
    """Use only fields supported by this printer's matching stock template."""
    item = deepcopy(template)
    color = scalar(profile["default_filament_colour"]).upper()
    if not re.fullmatch(r"#[0-9A-F]{6}", color):
        raise SyncError("Ungültige Profilfarbe: " + color)
    for key in item["kvParam"]:
        if key in profile:
            item["kvParam"][key] = scalar(profile[key])
    item["base"].update({
        "id": material_id,
        "name": scalar(profile["name"]),
        "brand": scalar(profile["filament_vendor"]),
        "meterialType": scalar(profile["filament_type"]),
        "colors": [color],
        "density": float(scalar(profile["filament_density"])),
        "diameter": scalar(profile["filament_diameter"]),
        "minTemp": int(scalar(profile["nozzle_temperature_range_low"])),
        "maxTemp": int(scalar(profile["nozzle_temperature_range_high"])),
        "isSoluble": scalar(profile["filament_soluble"]) == "1",
        "isSupport": scalar(profile["filament_is_support"]) == "1",
    })
    low, high = item["base"]["minTemp"], item["base"]["maxTemp"]
    if low > high:
        raise SyncError("Ungültiger Temperaturbereich.")
    for key in ("nozzle_temperature", "nozzle_temperature_initial_layer"):
        if not low <= float(item["kvParam"][key]) <= high:
            raise SyncError(f"{item['base']['name']}: {key} außerhalb des Temperaturbereichs.")
    if item["base"]["density"] <= 0:
        raise SyncError("Ungültige Filamentdichte.")
    if "userMaterial" in item:
        raise SyncError("Eine Cloud-Benutzerprofilvorlage darf nicht als RFID-Vorlage dienen.")
    return item


def merge_database(database, resolved_profiles, printer, receipt=None):
    """Keep every unowned object, its ordering, and the catalog version."""
    old = database["result"]["list"]
    if database["result"]["count"] != len(old):
        raise SyncError("Der Materialkatalog hat eine inkonsistente Eintragszahl.")
    owned = (receipt or {}).get("owned_entries", {})
    result = deepcopy(database)
    entries = result["result"]["list"]
    all_codes = set()
    new_owned = {}
    changes = []
    unowned_before = []
    for item in old:
        code = item.get("base", {}).get("id", "")
        if code not in owned:
            unowned_before.append(item)
    for record in resolved_profiles:
        entry, profile = record["entry"], record["resolved"]
        code = entry["material_id"]
        if not re.fullmatch(r"[A-Za-z0-9]{5}", code) or code in all_codes:
            raise SyncError("Doppelte oder ungültige Registry-Kennung: " + code)
        all_codes.add(code)
        material_type = scalar(profile["filament_type"])
        base_id = entry["original_filament_id"]
        templates = [x for x in old
                     if x.get("base", {}).get("id") == base_id
                     and x["base"].get("name", "").startswith("Generic ")
                     and x["base"].get("meterialType") == material_type
                     and x.get("printerIntName") == printer["printer_int_name"]
                     and x.get("nozzleDiameter") == [printer["nozzle_diameter"]]
                     and "userMaterial" not in x]
        if len(templates) != 1:
            raise SyncError(f"{entry['name']}: keine eindeutige passende Druckervorlage.")
        wanted = make_record(templates[0], profile, code)
        found = [i for i, x in enumerate(entries) if x.get("base", {}).get("id") == code]
        if len(found) > 1:
            raise SyncError("Materialcode ist mehrfach vorhanden: " + code)
        if found:
            current = entries[found[0]]
            if code not in owned:
                raise SyncError("Materialcode ist bereits fremd belegt: " + code)
            if digest(current) != digest(owned[code]):
                raise SyncError("Registrierter Druckereintrag wurde außerhalb der Synchronisierung verändert: " + code)
            if current != wanted:
                entries[found[0]] = wanted
                changes.append({"material_id": code, "name": wanted["base"]["name"], "action": "updated"})
        else:
            entries.append(wanted)
            changes.append({"material_id": code, "name": wanted["base"]["name"], "action": "added"})
        new_owned[code] = wanted
    # Disabled/deleted registry entries are not deleted from the printer. Keep
    # their ownership receipts too, so the next enable cannot hijack a new code.
    for code, item in owned.items():
        if code not in new_owned:
            new_owned[code] = item
    result["result"]["count"] = len(entries)
    if result["result"]["version"] != database["result"]["version"]:
        raise AssertionError("The original version must remain unchanged")
    unowned_after = [x for x in entries if x.get("base", {}).get("id", "") not in new_owned]
    if canonical(unowned_before) != canonical(unowned_after):
        raise AssertionError("An unrelated material record changed")
    report = {
        "status": "prepared_not_installed", "old_count": len(old),
        "new_count": len(entries), "version": result["result"]["version"],
        "registered_profiles": len(resolved_profiles), "changes": changes,
        "unrelated_records_unchanged": True, "restart_performed": False,
        "active_firmware_reload_verified": False,
    }
    return result, {"schema_version": 1, "owned_entries": new_owned}, report


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def run_json_command(remote, command, data=None, timeout=60):
    for attempt in range(4):
        try:
            raw = remote.run(command, timeout=timeout) if data is None else remote.run(command, data, timeout=timeout)
            return json.loads(raw)
        except SyncError as error:
            if 'arbeitet gerade' not in str(error) or attempt == 3:
                raise
            time.sleep(0.25*(attempt+1))


class PrinterSSH:
    def __init__(self, ip, known_hosts, password=None):
        import ipaddress
        ipaddress.ip_address(ip)
        self.ip = ip
        self.known_hosts = Path(known_hosts).resolve()
        if not self.known_hosts.is_file():
            raise SyncError("SSH-Hostschlüssel fehlt. Zuerst die Identität des Druckers prüfen.")
        self.password=password
        self._client=None
        self._reuse_client=False

    def close(self):
        if self._client is not None:
            self._client.close();self._client=None

    @contextmanager
    def session(self):
        previous=self._reuse_client;self._reuse_client=True
        try:yield self
        finally:
            self._reuse_client=previous
            if not previous:self.close()

    def run(self, command, data=None, timeout=30):
        try:
            import paramiko
        except ImportError:
            if os.name == 'nt':
                raise SyncError('Für SSH unter Windows wird Paramiko benötigt. Anwendungseinrichtung ausführen.')
        else:
            client=self._client if self._reuse_client else None
            if client is not None and not client.get_transport().is_active():
                self.close();client=None
            fresh=client is None
            if fresh:client=paramiko.SSHClient()
            try:
                if fresh:
                    client.load_host_keys(str(self.known_hosts))
                    client.set_missing_host_key_policy(paramiko.RejectPolicy())
                    client.connect(self.ip,username='root',password=self.password,
                        timeout=8,banner_timeout=8,auth_timeout=8,
                        look_for_keys=self.password is None,allow_agent=self.password is None)
                    if self._reuse_client:self._client=client
                stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
                if data:
                    stdin.write(data); stdin.flush()
                stdin.channel.shutdown_write()
                output, error = stdout.read(16_000_001), stderr.read(1_000_001)
                if stdout.channel.recv_exit_status():
                    raise SyncError('SSH: ' + error.decode(errors='replace').strip())
                return output
            except SyncError:
                raise
            except Exception as exc:
                from cfs_connection_errors import ssh_issue
                issue=ssh_issue(exc,self.ip,self.password is not None)
                raise SyncError(str(issue),issue.code) from exc
            finally:
                if not self._reuse_client or self._client is not client:client.close()
        cmd = ["ssh", "-o", "StrictHostKeyChecking=yes", "-o",
               "UserKnownHostsFile=" + str(self.known_hosts), "-o", "ConnectTimeout=8",
               "-o", "ServerAliveInterval=10", "root@" + self.ip, command]
        read_fd = None
        try:
            if self.password is not None:
                read_fd, write_fd = os.pipe()
                os.write(write_fd, self.password.encode() + b"\n")
                os.close(write_fd)
                cmd = ["sshpass", "-d", str(read_fd)] + cmd
            else:
                cmd[1:1] = ["-o", "BatchMode=yes"]
            r = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout,
                               pass_fds=(() if read_fd is None else (read_fd,)))
        except (OSError, subprocess.TimeoutExpired) as exc:
            from cfs_connection_errors import network_issue
            issue=network_issue(exc,self.ip,ssh=True)
            raise SyncError(str(issue),issue.code) from exc
        finally:
            if read_fd is not None:
                os.close(read_fd)
        if r.returncode:
            if r.returncode in (5,255):
                from cfs_connection_errors import ssh_cli_issue
                issue=ssh_cli_issue(r.returncode,r.stderr.decode(errors='replace'),self.password is not None)
                raise SyncError(str(issue),issue.code)
            raise SyncError("SSH: "+r.stderr.decode(errors="replace").strip())
        return r.stdout

    def read_database(self):
        raw = self.run("cat -- " + shlex.quote(REMOTE_DATABASE))
        return raw, json.loads(raw)

    def read_status(self):
        url = "http://" + self.ip + ":4408/printer/objects/query?print_stats&webhooks&configfile"
        try:
            with urllib.request.urlopen(url, timeout=8) as response:
                status = json.load(response)["result"]["status"]
        except Exception as exc:
            from cfs_connection_errors import network_issue
            issue=network_issue(exc,self.ip)
            raise SyncError(str(issue),issue.code) from exc
        return status

    def check_idle(self):
        status = self.read_status()
        if status.get("webhooks", {}).get("state") != "ready":
            raise SyncError("Drucker ist nicht bereit; die Synchronisierung wartet.")
        if status.get("print_stats", {}).get("state") not in ("standby", "complete", "cancelled"):
            raise SyncError("Druckauftrag aktiv; die Synchronisierung wartet.")
        return status

    def install(self, before, merged, backup_dir):
        self.check_idle()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / (stamp + ".material_database.json")).write_bytes(before)
        staging = REMOTE_DATABASE + ".cfs-" + uuid.uuid4().hex + ".tmp"
        wanted = canonical(merged) + b"\n"
        self.run("umask 077; cat > " + shlex.quote(staging), wanted)
        # Validate JSON and hashes on the printer before entering the short
        # commit section. Never trust a partially uploaded file.
        script = "\n".join([
            "import hashlib,json,os,shutil,fcntl",
            "path=" + repr(REMOTE_DATABASE), "stage=" + repr(staging),
            "expected=" + repr(digest(before)), "wanted=" + repr(digest(wanted)),
            "backup=os.path.dirname(path)+'/.cfs-profile-backups/" + stamp + ".json'",
            "with open(path+'.cfs-sync.lock','a') as lock:",
            " fcntl.flock(lock,fcntl.LOCK_EX)",
            " assert hashlib.sha256(open(path,'rb').read()).hexdigest()==expected, 'CATALOG_CHANGED'",
            " assert hashlib.sha256(open(stage,'rb').read()).hexdigest()==wanted, 'UPLOAD_CHANGED'",
            " doc=json.load(open(stage)); assert doc['result']['count']==len(doc['result']['list'])",
            " os.makedirs(os.path.dirname(backup),exist_ok=True)",
            " shutil.copy2(path,backup)",
            " os.chmod(stage,os.stat(path).st_mode & 0o777)",
            " os.chown(stage,os.stat(path).st_uid,os.stat(path).st_gid)",
            " with open(stage,'rb') as stream: os.fsync(stream.fileno())",
            " os.replace(stage,path)",
            " fd=os.open(os.path.dirname(path),os.O_DIRECTORY); os.fsync(fd); os.close(fd)",
            " print(backup)",
        ])
        try:
            self.check_idle()
            remote_backup = self.run("python3 -", script.encode()).decode().strip()
            after, _ = self.read_database()
            if after != wanted:
                raise SyncError("Der Drucker hat den Katalog nach der Übertragung geändert. Sicherungen aufbewahren.")
        finally:
            self.run("rm -f -- " + shlex.quote(staging))
        return {"remote_backup": remote_backup, "catalog_sha256": digest(wanted),
                "installed_at": datetime.now(timezone.utc).isoformat(),
                "restart_performed": False, "active_firmware_reload_verified": False}


def synchronize(registry_path, input_database=None, install=False, password=None, state_dir=None):
    from cfs_registry import ProfileRegistry
    registry = ProfileRegistry(registry_path)
    state = Path(state_dir or HERE / "state")
    state.mkdir(parents=True, exist_ok=True)
    registry_doc = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    if install and registry_doc.get("sync_source") == "printer_cloud":
        raise SyncError("Der Drucker gleicht seine Cloud-Profile selbst ab. Ein lokaler PC-Abgleich würde diesen Stand überschreiben und ist deshalb deaktiviert.")
    printer = registry_doc["printer"]
    records = [registry.resolve(e["material_id"]) for e in registry.entries if e.get("enabled", True)]
    receipt_path = state / ("receipt-" + printer["ip"] + ".json")
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    remote = None
    if input_database:
        if install:
            raise SyncError("Eine Offline-Vorlage kann nicht direkt installiert werden; der aktuelle Katalog muss neu gelesen werden.")
        raw = Path(input_database).read_bytes()
        current = json.loads(raw)
    else:
        remote = PrinterSSH(printer["ip"], state / "known_hosts", password)
        raw, current = remote.read_database()
    merged, next_receipt, report = merge_database(current, records, printer, receipt)
    report["input_sha256"] = digest(raw)
    report["profile_setting_ids"] = [r["entry"]["profile_setting_id"] for r in records]
    write_json(state / "material_database.proposed.json", merged)
    write_json(state / "sync-report.json", report)
    if install:
        if remote is None:
            raise SyncError("Keine geprüfte Druckerverbindung.")
        if report["changes"]:
            details = remote.install(raw, merged, state / "backups")
            report.update(details)
        else:
            details = {"catalog_sha256": digest(raw), "no_changes": True}
        next_receipt["printer_ip"] = printer["ip"]
        write_json(receipt_path, next_receipt)
        report["status"] = "file_installed_reload_unverified"
        write_json(state / "sync-report.json", report)
        # The native controller watches this file. Rewriting an unchanged
        # registry on every poll would unnecessarily discard slot history.
        if report["changes"] or registry.registration_status != "installed":
            registry.set_registration_status("installed", details=details)
    return report


def main():
    parser = argparse.ArgumentParser(description="Benutzerprofile für den K2-Pro-Materialkatalog vorbereiten oder synchronisieren.")
    parser.add_argument("--registry", type=Path, default=HERE / "profil-zuordnung.json")
    parser.add_argument("--input-database", type=Path, help="Nur offline vorbereiten, ohne Druckerverbindung")
    parser.add_argument("--state-dir", type=Path, default=HERE / "state")
    parser.add_argument("--install", action="store_true", help="Aktuellen Katalog sichern und atomar ersetzen; kein Neustart")
    parser.add_argument("--watch", action="store_true", help="Gespeicherte Profiländerungen mit --install wiederholt übernehmen")
    parser.add_argument("--ask-password", action="store_true", help="SSH-Passwort einmal abfragen; nicht speichern")
    args = parser.parse_args()
    if args.watch and (not args.install or args.input_database):
        parser.error("--watch benötigt --install und eine echte Druckerverbindung")
    password = getpass.getpass("SSH-Passwort des K2 Pro: ") if args.ask_password else None
    try:
        while True:
            try:
                report = synchronize(args.registry, args.input_database, args.install, password, args.state_dir)
                print(json.dumps({k: report.get(k) for k in ("status", "registered_profiles", "old_count", "new_count", "changes")}, ensure_ascii=False), flush=True)
            except (SyncError, ValueError, OSError, KeyError) as exc:
                if not args.watch:
                    raise
                print("Synchronisierung wartet: " + str(exc), file=sys.stderr, flush=True)
            if not args.watch:
                return
            time.sleep(30)
    except KeyboardInterrupt:
        return
    except (SyncError, ValueError, OSError, KeyError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()


def connection_session(remote):
    return remote.session() if isinstance(remote,PrinterSSH) else nullcontext(remote)
