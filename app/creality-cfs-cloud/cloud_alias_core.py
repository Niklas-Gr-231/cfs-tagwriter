# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Pure Creality cloud-profile -> stable CFS material-code derivation.

Python 3.9 standard library only. No files, network, printer commands, profile
edits, clocks, or services are accessed here. All inputs are decoded JSON values.
The caller must commit database + receipt before publishing an installed export.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re
from cfs_transfer_core import imported_exports, MODEL


class SyncError(RuntimeError):
    """Configuration, ownership, or foreign-code conflict; never overwrite it."""


class DeferredSyncError(SyncError):
    """Native cloud state is missing/inconsistent; keep the current files intact."""


_CLOUD_PATH = re.compile(
    r"^/mnt/UDISK/creality/userdata/box/usrMaterial/"
    r"(?P<account>[0-9]+)/(?P<sid>[0-9a-f]{24})-(?P<revision>0|[1-9][0-9]*)$")
_CODE = re.compile(r"99[0-9]{3}$")
_SID = re.compile(r"[0-9a-f]{24}$")
_COLOR = re.compile(r"#[0-9a-fA-F]{6}$")
_REQUIRED_KV = (
    "filament_type", "filament_vendor", "filament_density", "filament_diameter",
    "nozzle_temperature", "nozzle_temperature_initial_layer",
    "nozzle_temperature_range_low", "nozzle_temperature_range_high",
    "filament_flow_ratio", "pressure_advance", "enable_pressure_advance",
)
# Native cloud conversion currently writes an unrelated template name to
# kvParam.inherits. Compatibility/notes are metadata, not proof of new settings.
_NON_PRINT_COMPARISON = {
    "inherits", "filament_notes", "compatible_printers", "compatible_prints",
    "compatible_printers_condition", "compatible_prints_condition",
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _scalar(value, context):
    if isinstance(value, list):
        if len(value) != 1:
            raise DeferredSyncError(context + ": kein eindeutiger Einzelwert")
        return _scalar(value[0], context)
    if isinstance(value, str):
        if "\x00" in value:
            raise DeferredSyncError(context + ": ungültiges Steuerzeichen")
        return value
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise DeferredSyncError(context + ": nicht endlicher Zahlenwert")
        return str(value)
    raise DeferredSyncError(context + ": fehlender/ungültiger Profilwert")


def _number(value, context):
    try:
        result = float(_scalar(value, context))
    except (ValueError, OverflowError):
        raise DeferredSyncError(context + ": kein Zahlenwert")
    if not math.isfinite(result):
        raise DeferredSyncError(context + ": nicht endlicher Zahlenwert")
    return result


def _same_value(a, b, context):
    a, b = _scalar(a, context), _scalar(b, context)
    if a == b:
        return True
    # Native JSON conversion may stringify 245 as 245.0. Other values, G-code,
    # percentages and names remain exact strings.
    numeric = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")
    if numeric.fullmatch(a) and numeric.fullmatch(b):
        try:
            return Decimal(a) == Decimal(b)
        except InvalidOperation:
            return False
    return False


def _color(value, context):
    value = _scalar(value, context)
    if not _COLOR.fullmatch(value):
        raise DeferredSyncError(context + ": Farbe muss genau #RRGGBB enthalten")
    return value.upper()


def _manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise SyncError("Unbekanntes Cloud-Alias-Manifestformat")
    account = manifest.get("account_id")
    printer = manifest.get("printer_int_name")
    nozzle = manifest.get("nozzle_diameter")
    if not isinstance(account, str) or not re.fullmatch(r"[0-9]+", account):
        raise SyncError("Manifest benötigt die exakte Cloud-Konto-ID")
    if not isinstance(printer, str) or not MODEL.fullmatch(printer):
        raise SyncError("Manifest benötigt das interne Druckermodell")
    if (not isinstance(nozzle, str) or not re.fullmatch(r"[0-9]+\.[0-9]+", nozzle)
            or not math.isfinite(float(nozzle)) or float(nozzle) <= 0):
        raise SyncError("Manifest benötigt den Düsendurchmesser als Zeichenkette")
    profiles = manifest.get("profiles")
    if not isinstance(profiles, list):
        raise SyncError("Manifest-Profilliste fehlt")
    codes, sids = set(), set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise SyncError("Ungültiger Manifest-Profileintrag")
        code, sid = profile.get("material_id"), profile.get("profile_setting_id")
        if not isinstance(code, str) or not _CODE.fullmatch(code):
            raise SyncError("Eigene Materialcodes müssen im fünfstelligen 99xxx-Bereich liegen")
        if not isinstance(sid, str) or not _SID.fullmatch(sid):
            raise SyncError("Ungültige stabile Cloud-Profil-ID bei " + code)
        if code in codes or sid in sids:
            raise SyncError("Doppelte Material- oder Cloud-Profil-ID im Manifest")
        if not isinstance(profile.get("enabled", True), bool):
            raise SyncError("Ungültiger Aktivierungsstatus bei " + code)
        codes.add(code)
        sids.add(sid)
    return account, printer, nozzle, profiles


def _index_records(index, account):
    if not isinstance(index, list):
        raise DeferredSyncError("Der native Cloudindex ist noch nicht lesbar")
    result = {}
    for item in index:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        match = _CLOUD_PATH.fullmatch(path) if isinstance(path, str) else None
        if not match or match.group("account") != account:
            continue
        version = item.get("version")
        if isinstance(version, bool) or not isinstance(version, (str, int)) or not re.fullmatch(r"[0-9]+", str(version)):
            raise DeferredSyncError("Cloudindex enthält eine unvollständige Versionsangabe")
        record = {"path": path, "version": str(version),
                  "revision": int(match.group("revision")), "profile_setting_id": match.group("sid")}
        existing = result.setdefault(record["profile_setting_id"], [])
        if record not in existing:
            existing.append(record)
    return result


def _active_index(records, sid):
    found = records.get(sid, [])
    if len(found) != 1:
        raise DeferredSyncError("Cloudprofil fehlt oder hat mehrere aktive Revisionen: " + sid)
    return found[0]


def _native_record(entries, active, cloud_files, printer, nozzle, owned_codes):
    path = active["path"]
    cloud = cloud_files.get(path)
    if not isinstance(cloud, dict):
        raise DeferredSyncError("Cloudprofildatei ist noch nicht vollständig geladen: " + path)
    name = _scalar(cloud.get("name"), path + "/name")
    if not name.strip():
        raise DeferredSyncError("Cloudprofilname fehlt: " + path)
    candidates = [entry for entry in entries
                  if isinstance(entry, dict) and entry.get("userMaterial") == path
                  and entry.get("printerIntName") == printer
                  and entry.get("nozzleDiameter") == [nozzle]
                  and isinstance(entry.get("base"), dict)
                  and entry["base"].get("id") not in owned_codes
                  and not str(entry["base"].get("id", "")).startswith("99")]
    if not candidates:
        raise DeferredSyncError("Native Druckerdatenbank hat die Cloudrevision noch nicht aufgelöst: " + path)
    for entry in candidates:
        kv, base = entry.get("kvParam"), entry["base"]
        if not isinstance(kv, dict) or any(key not in kv for key in _REQUIRED_KV):
            raise DeferredSyncError("Nativer Cloud-Datensatz ist unvollständig: " + path)
        if base.get("name") != name:
            raise DeferredSyncError("Clouddatei und nativer Datenbankname sind noch nicht konsistent: " + path)
        if not isinstance(entry.get("engineVersion"), str) or not entry["engineVersion"]:
            raise DeferredSyncError("Native Engine-Version fehlt: " + path)
        for key, value in cloud.items():
            if key in kv and key not in _NON_PRINT_COMPARISON:
                same = (_color(value, name) == _color(kv[key], name) if key == "default_filament_colour"
                        else _same_value(value, kv[key], name + "/" + key))
                if not same:
                    raise DeferredSyncError("Cloud-Druckwert ist noch nicht in der nativen Datenbank angekommen: " + name + "/" + key)
        low = _number(kv["nozzle_temperature_range_low"], name + "/temperature_low")
        high = _number(kv["nozzle_temperature_range_high"], name + "/temperature_high")
        if low <= 0 or low > high:
            raise DeferredSyncError("Ungültiger nativer Temperaturbereich: " + name)
        for key in ("nozzle_temperature", "nozzle_temperature_initial_layer"):
            if not low <= _number(kv[key], name + "/" + key) <= high:
                raise DeferredSyncError("Native Drucktemperatur liegt außerhalb des Bereichs: " + name)
        for key in ("filament_density", "filament_diameter", "filament_flow_ratio"):
            if _number(kv[key], name + "/" + key) <= 0:
                raise DeferredSyncError("Ungültiger nativer Druckwert: " + name + "/" + key)
        if _number(kv["pressure_advance"], name + "/pressure_advance") < 0:
            raise DeferredSyncError("Ungültiger nativer PA-Wert: " + name)
        if not _scalar(kv["filament_type"], name + "/type").strip():
            raise DeferredSyncError("Nativer Filamenttyp fehlt: " + name)
    if len({digest(entry["kvParam"]) for entry in candidates}) != 1:
        raise DeferredSyncError("Mehrdeutige native Druckwerte derselben Cloudrevision: " + path)
    richest = max(len(entry["base"]) for entry in candidates)
    rich = [entry for entry in candidates if len(entry["base"]) == richest]
    if len({digest(entry) for entry in rich}) != 1:
        raise DeferredSyncError("Mehrdeutige gleich vollständige native Cloud-Datensätze: " + path)
    chosen = rich[0]
    # Only explicit cloud overrides may replace native base metadata. Native KV
    # stays verbatim, including all fields not understood by this helper.
    brand = (_scalar(cloud["filament_vendor"], name + "/vendor")
             if "filament_vendor" in cloud else _scalar(chosen["base"].get("brand"), name + "/brand"))
    if not brand.strip():
        raise DeferredSyncError("Cloud-Hersteller fehlt: " + name)
    if "default_filament_colour" in cloud:
        color = _color(cloud["default_filament_colour"], name + "/color")
    else:
        color = _color(chosen["base"].get("colors"), name + "/native_color")
    return chosen, cloud, name, brand, color, len(candidates), richest


def build_aliases(database, index, cloud_files, manifest, receipt=None):
    """Return (merged_database, next_receipt, report, pending_tag_export).

    Failure raises before any result is returned. Inputs are never mutated.
    A trusted schema-1 receipt from the previous host synchronizer is accepted
    for a one-time migration, but existing owned entries must still match it.
    """
    account, printer, nozzle, profiles = _manifest(manifest)
    try:
        imported = imported_exports(manifest)
    except (ValueError, TypeError, KeyError) as exc:
        raise SyncError("Importierte Profile sind ungültig: " + str(exc)) from exc
    if not isinstance(database, dict) or not isinstance(database.get("result"), dict):
        raise DeferredSyncError("Native Materialdatenbank ist noch nicht lesbar")
    catalog = database["result"]
    old = catalog.get("list")
    if (not isinstance(old, list) or not isinstance(catalog.get("count"), int)
            or isinstance(catalog.get("count"), bool) or catalog.get("count") != len(old) or "version" not in catalog):
        raise DeferredSyncError("Native Materialdatenbank ist noch nicht vollständig")
    if any(not isinstance(entry, dict) or not isinstance(entry.get("base"), dict) for entry in old):
        raise DeferredSyncError("Native Materialdatenbank enthält unvollständige Einträge")
    if any(not isinstance(entry["base"].get("id"), str)
           or not re.fullmatch(r"[A-Za-z0-9]{5}", entry["base"]["id"]) for entry in old):
        raise DeferredSyncError("Native Materialdatenbank enthält ungültige Materialkennungen")
    if not isinstance(cloud_files, dict):
        raise DeferredSyncError("Native Clouddateien sind noch nicht geladen")
    if receipt is not None and (not isinstance(receipt, dict) or receipt.get("schema_version") != 1):
        raise SyncError("Unbekanntes Besitznachweisformat")
    receipt = receipt or {"schema_version": 1, "owned_entries": {}}
    owned = receipt.get("owned_entries", {})
    bindings = receipt.get("profile_bindings", {})
    reserved = receipt.get("reserved_material_ids", [])
    if not isinstance(owned, dict) or not isinstance(bindings, dict) or not isinstance(reserved, list):
        raise SyncError("Ungültiger Besitznachweis")
    if any(not isinstance(code, str) or not _CODE.fullmatch(code) for code in list(bindings) + reserved):
        raise SyncError("Ungültige historische Materialcode-Reservierung")
    if receipt.get("account_id", account) != account:
        raise SyncError("Besitznachweis gehört zu einem anderen Cloudkonto")
    positions = {}
    for i, entry in enumerate(old):
        positions.setdefault(entry["base"].get("id"), []).append(i)
    for code, previous in owned.items():
        if (not isinstance(code, str) or not _CODE.fullmatch(code) or not isinstance(previous, dict)
                or not isinstance(previous.get("base"), dict) or previous["base"].get("id") != code):
            raise SyncError("Ungültiger eigener Eintrag im Besitznachweis")
        found = positions.get(code, [])
        if len(found) > 1:
            raise SyncError("Eigener Materialcode ist mehrfach vorhanden: " + code)
        if found and digest(old[found[0]]) != digest(previous):
            raise SyncError("Eigener Druckereintrag wurde extern verändert: " + code)
    for profile in profiles + imported:
        code = profile["material_id"]
        if positions.get(code) and code not in owned:
            raise SyncError("Materialcode ist fremd belegt: " + code)
        binding = bindings.get(code)
        if binding is not None and (not isinstance(binding, dict) or binding.get("profile_setting_id") != profile["profile_setting_id"]):
            raise SyncError("Eine bestehende Materialcode-Bindung würde auf ein anderes Cloudprofil zeigen: " + code)
    records = _index_records(index, account)
    prepared, exported, sources = [], [], {}
    for profile in profiles:
        if not profile.get("enabled", True):
            continue
        code, sid = profile["material_id"], profile["profile_setting_id"]
        active = _active_index(records, sid)
        previous = bindings.get(code, {})
        try:
            rollback = (int(active["version"]) < int(previous.get("cloud_version", "0")) or
                        active["revision"] < int(previous.get("cloud_revision", 0)))
        except (ValueError, TypeError):
            raise SyncError("Ungültiger Versionsnachweis bei " + code)
        if rollback:
            raise DeferredSyncError("Cloudindex ist älter als der bereits übernommene Stand: " + code)
        native, cloud, name, brand, color, candidate_count, richness = _native_record(
            old, active, cloud_files, printer, nozzle, set(owned))
        wanted = deepcopy(native)
        wanted["base"]["id"] = code
        if "filament_vendor" in cloud:
            wanted["base"]["brand"] = brand
        if "default_filament_colour" in cloud:
            wanted["base"]["colors"] = [color]
        prepared.append((code, wanted))
        kv = deepcopy(native["kvParam"])
        sources[code] = {"profile_setting_id": sid, "cloud_path": active["path"],
                         "cloud_version": active["version"], "cloud_revision": active["revision"],
                         "native_entry_sha256": digest(native), "cloud_file_sha256": digest(cloud),
                         "native_candidates": candidate_count, "selected_base_fields": richness}
        exported.append({"material_id": code, "profile_setting_id": sid, "name": name,
                         "brand": brand, "type": _scalar(kv["filament_type"], name + "/type"),
                         "color": color, "source_file": active["path"],
                         "profile_metadata": {"nozzle_temperature": _scalar(kv["nozzle_temperature"], name),
                                              "flow_ratio": _scalar(kv["filament_flow_ratio"], name),
                                              "pressure_advance": _scalar(kv["pressure_advance"], name)},
                         "record": deepcopy(wanted), "origin": "cloud",
                         "resolved": dict(kv, name=name)})
    for profile in imported:
        code = profile["material_id"]
        prepared.append((code, deepcopy(profile["record"])))
        exported.append(deepcopy(profile))
        sources[code] = {"profile_setting_id": profile["profile_setting_id"],
            "origin": "imported", "identity": profile["identity"],
            "origin_account_id": profile["origin_account_id"], "origin_setting_id": profile["origin_setting_id"]}
    # No result allocation/modification until every active profile is ready.
    merged = deepcopy(database)
    entries = merged["result"]["list"]
    next_receipt = deepcopy(receipt)
    next_receipt.update({"schema_version": 1, "source": "printer_cloud", "account_id": account})
    next_receipt.setdefault("owned_entries", {})
    next_receipt.setdefault("profile_bindings", {})
    changes = []
    for code, wanted in prepared:
        found = positions.get(code, [])
        if found:
            if old[found[0]] != wanted:
                entries[found[0]] = deepcopy(wanted)
                changes.append({"material_id": code, "name": wanted["base"]["name"], "action": "updated"})
        else:
            entries.append(deepcopy(wanted))
            changes.append({"material_id": code, "name": wanted["base"]["name"], "action": "added"})
        next_receipt["owned_entries"][code] = deepcopy(wanted)
        next_receipt["profile_bindings"][code] = deepcopy(sources[code])
    merged["result"]["count"] = len(entries)
    unrelated_before = [entry for entry in old if entry["base"].get("id") not in owned]
    unrelated_after = [entry for entry in entries if entry["base"].get("id") not in next_receipt["owned_entries"]]
    if unrelated_before != unrelated_after or merged["result"]["version"] != catalog["version"]:
        raise AssertionError("Unrelated native entries/version must remain unchanged")
    available = []
    assigned_sids = {profile["profile_setting_id"] for profile in profiles + imported}
    for sid in sorted(set(records) - assigned_sids):
        try:
            active = _active_index(records, sid)
            native, cloud, name, brand, color, _, _ = _native_record(old, active, cloud_files, printer, nozzle, set(owned))
            available.append({"profile_setting_id": sid, "name": name, "brand": brand,
                              "type": _scalar(native["kvParam"]["filament_type"], name), "color": color,
                              "source_file": active["path"], "cloud_version": active["version"], "status": "unassigned"})
        except DeferredSyncError as exc:
            available.append({"profile_setting_id": sid, "status": "cloud_pending", "reason": str(exc)})
    used = set(positions) | {profile["material_id"] for profile in profiles} | set(owned) | set(bindings) | set(reserved)
    used_material_ids = sorted(used)
    # The original twenty assignments occupy 99001..99020. New automatic
    # allocations start beyond that range even for a deliberately partial view.
    next_material_id = next((str(code) for code in range(99021, 100000) if str(code) not in used), None)
    report = {"status": "prepared_not_installed", "source": "printer_cloud", "old_count": len(old),
              "new_count": len(entries), "version": catalog["version"], "version_preserved": True,
              "registered_profiles": len(prepared), "changes": changes,
              "unrelated_records_unchanged": True, "cloud_sources": deepcopy(sources),
              "available_profiles": deepcopy(available), "restart_performed": False,
              "used_material_ids": used_material_ids, "next_material_id": next_material_id,
              "active_firmware_reload_verified": False}
    tag_materials = {"schema_version": 1, "source": "printer_cloud", "printer_registration_status": "pending",
                     "account_id": account, "profiles": exported, "available_profiles": available,
                     "used_material_ids": list(used_material_ids), "next_material_id": next_material_id}
    return merged, next_receipt, report, tag_materials
