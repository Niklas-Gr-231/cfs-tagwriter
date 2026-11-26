# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit registration of a new cloud profile through checked printer SSH."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shlex


REMOTE_CONFIG = "/mnt/UDISK/printer_data/config/cfs_cloud_profiles"
REMOTE_SERVICE = REMOTE_CONFIG + "/cloud_service.py"


def validate_registration(catalog: dict, setting_id: str, material_id: str):
    if not re.fullmatch(r"[0-9a-f]{24}", setting_id):
        raise ValueError("Bitte ein verfügbares Cloud-Profil auswählen.")
    if not re.fullmatch(r"99[0-9]{3}", material_id):
        raise ValueError("Der neue Materialcode muss fünf Ziffern haben und mit 99 beginnen, zum Beispiel 99021.")
    if catalog.get("printer_registration_status") != "installed":
        raise ValueError("Die Druckereinrichtung ist noch nicht abgeschlossen. Bitte später erneut laden.")
    if material_id in catalog.get("used_material_ids", []):
        raise ValueError("Dieser Materialcode ist bereits belegt oder reserviert. Bitte einen freien Code wählen.")
    matching = [p for p in catalog.get("available_profiles", []) if p.get("profile_setting_id") == setting_id and p.get("status", "unassigned") == "unassigned"]
    if len(matching) != 1:
        raise ValueError("Dieses Cloud-Profil ist nicht mehr zur Vergabe verfügbar. Bitte die Übersicht neu laden.")


def register_cloud_profile(registry, setting_id: str, material_id: str | None, password: str | None = None, *, ssh_factory=None) -> dict:
    """Run only the registration CLI; never upload or alter slicer profiles.

    Passwords are passed in memory to PrinterSSH, which uses a private pipe.
    A successful CLI reply alone is insufficient: the committed HTTP snapshot
    must independently confirm the exact new code/setting-ID pair.
    """
    catalog = registry.cloud_catalog(fresh=True)
    automatic=material_id is None
    candidate=catalog.get('next_material_id') if automatic else material_id
    if candidate is None:raise ValueError('Kein freier NFC-Materialcode verfügbar.')
    validate_registration(catalog, setting_id, candidate)
    if password is not None and (len(password) > 1024 or "\n" in password or "\r" in password):
        raise ValueError("Das SSH-Passwort enthält ungültige Zeichen oder ist zu lang.")
    if ssh_factory is None:
        from cfs_profile_sync import PrinterSSH
        ssh_factory = PrinterSSH
    known_hosts = Path(registry.path).parent / "state" / "known_hosts"
    remote = ssh_factory(registry.printer["ip"], known_hosts, password or None)
    parts=["python3",REMOTE_SERVICE,"--config",REMOTE_CONFIG,"--register",setting_id]
    if not automatic:parts.extend(('--material-id',material_id))
    command=' '.join(shlex.quote(part) for part in parts)
    try:
        from cfs_profile_sync import run_json_command
        reply = run_json_command(remote,command,timeout=45)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("Der Drucker hat die Profilregistrierung nicht eindeutig bestätigt. Bitte Cloud-Profile neu laden.") from exc
    if not isinstance(reply, dict) or reply.get("success") is not True:
        message = reply.get("message") if isinstance(reply, dict) else None
        raise ValueError(str(message or "Die Profil-ID konnte am Drucker nicht registriert werden."))
    if automatic:
        chosen=reply.get('material_id')
        if not isinstance(chosen,str) or not re.fullmatch(r'99[0-9]{3}',chosen):
            raise ValueError('Drucker bestätigt keinen gültigen automatischen Materialcode.')
        material_id=chosen
    if reply.get("material_id") != material_id or reply.get("profile_setting_id") != setting_id or reply.get("status") not in ("registered", "already_registered"):
        raise ValueError("Die Druckerantwort bestätigt eine andere Profilzuordnung. Es wird kein Tag geschrieben; bitte neu laden.")
    materials = registry.materials()
    registered = next((item for item in materials if item["id"] == material_id and item.get("profile_setting_id") == setting_id), None)
    if registered is None or registered.get("registry_registration_status") != "installed":
        raise ValueError("Die neue Profil-ID ist noch nicht im aktuellen Drucker-Snapshot bestätigt. Bitte Cloud-Profile neu laden.")
    backup = reply.get("configuration_backup")
    backup_warning = None
    if isinstance(backup, dict) and backup.get("schema_version") == 1:
        bindings = backup.get("manifest", {}).get("profiles", [])
        if not any(p.get("material_id") == material_id and p.get("profile_setting_id") == setting_id for p in bindings):
            raise ValueError("Die Sicherung bestätigt eine andere Profilzuordnung. Bitte Druckerstatus prüfen.")
        try:
            from cfs_profile_transfer import save_backup
            save_backup(registry, backup)
        except OSError:
            backup_warning = "Die ID ist eingerichtet; die lokale Sicherung konnte nicht geschrieben werden."
    return {"material_id":material_id, "profile_setting_id":setting_id,
            "name":registered["name"], "status":reply["status"], "materials":materials,
            "backup_warning":backup_warning}
