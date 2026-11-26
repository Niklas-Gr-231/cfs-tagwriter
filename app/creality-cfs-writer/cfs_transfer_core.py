# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Portable material bundles and deterministic collision-safe import plans.

Python 3.9 standard library only. This module never reads files or runs G-code.
"""
from copy import deepcopy
import hashlib
import json
import math
import re

FORMAT = "creality-cfs-material-profiles"
CODE = re.compile(r"99[0-9]{3}$")
SID = re.compile(r"[0-9a-f]{24}$")
MODEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nicht endlicher Profilwert")
    return result


def validate_record(record, model, nozzle):
    if not isinstance(record, dict) or record.get("printerIntName") != model or record.get("nozzleDiameter") != [nozzle]:
        raise ValueError("Druckermodell oder Düsendurchmesser des Profils passt nicht zum Ziel.")
    base, kv = record.get("base"), record.get("kvParam")
    if not isinstance(base, dict) or not isinstance(kv, dict) or not kv:
        raise ValueError("Vollständige Material- und Druckwerte fehlen im Profil.")
    for key in ("name", "brand", "meterialType", "diameter"):
        if not isinstance(base.get(key), str) or not base[key].strip() or len(base[key]) > 250:
            raise ValueError("Ungültige Materialbeschreibung: " + key)
    colors = base.get("colors")
    if not isinstance(colors, list) or not colors or any(not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in colors):
        raise ValueError("Ungültige Profilfarbe")
    if number(base.get("density", 0)) <= 0 or number(base["diameter"]) <= 0:
        raise ValueError("Ungültige Dichte oder Filamentdicke")
    low, high = number(kv.get("nozzle_temperature_range_low")), number(kv.get("nozzle_temperature_range_high"))
    if not 0 < low <= high <= 350:
        raise ValueError("Ungültiger Düsentemperaturbereich")
    for key in ("nozzle_temperature", "nozzle_temperature_initial_layer"):
        if not low <= number(kv.get(key)) <= high:
            raise ValueError("Düsentemperatur liegt außerhalb des Profilbereichs")
    if number(kv.get("filament_flow_ratio", 0)) <= 0 or number(kv.get("pressure_advance", -1)) < 0:
        raise ValueError("Ungültiger Flow- oder PA-Wert")
    for key, value in kv.items():
        if not isinstance(key, str) or not key or len(key) > 200 or not isinstance(value, (str, int, float, bool)):
            raise ValueError("Nicht unterstützter Druckparameter")
        if isinstance(value, str) and (len(value) > 100000 or "\x00" in value):
            raise ValueError("Ungültiger Text in Druckparametern")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Nicht endlicher Druckparameter")
    if not isinstance(kv.get("filament_type"), str) or not kv["filament_type"].strip():
        raise ValueError("Materialtyp fehlt in den Druckparametern")
    digest(record)
    return deepcopy(record)


def validate_bundle(bundle):
    if not isinstance(bundle, dict) or bundle.get("format") != FORMAT or bundle.get("schema_version") not in (1,2):
        raise ValueError("Keine unterstützte CFS-Profiltransferdatei")
    source = bundle.get("source", {})
    if not isinstance(source, dict):
        raise ValueError("Quelldrucker fehlt")
    model, nozzle = source.get("printer_int_name"), source.get("nozzle_diameter")
    if not isinstance(model, str) or not MODEL.fullmatch(model) or not isinstance(nozzle, str) or not re.fullmatch(r"[0-9]+\.[0-9]+", nozzle):
        raise ValueError("Druckermodell oder Düse fehlt im Export")
    profiles = bundle.get("profiles")
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 1000:
        raise ValueError("Die Transferdatei muss 1 bis 1000 Benutzerprofile enthalten")
    identities, codes = set(), set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError("Ungültiger Transferprofileintrag")
        if 'slicer_source' in profile:
            from cfs_slicer_policy import validate_source
            validate_source(profile['slicer_source'])
        code, account, sid = profile.get("material_id"), profile.get("origin_account_id"), profile.get("origin_setting_id")
        if not isinstance(code, str) or not CODE.fullmatch(code) or code in codes:
            raise ValueError("Ungültiger oder doppelter Materialcode in der Transferdatei")
        if bundle['schema_version']==2 and profile.get('origin_kind')=='local':
            if account is not None or not isinstance(sid,str) or not re.fullmatch(r'[0-9a-f]{32}',sid):
                raise ValueError('Dauerhafte lokale Profilidentität fehlt.')
            identity='local:'+sid
        else:
            if not isinstance(account, str) or not re.fullmatch(r"[0-9]+", account) or not isinstance(sid, str) or not SID.fullmatch(sid):
                raise ValueError("Eindeutige Herkunft des Profils fehlt")
            identity = "cloud:" + account + ":" + sid
        if profile.get("identity") != identity or identity in identities:
            raise ValueError("Doppelte oder widersprüchliche Profilidentität")
        record = validate_record(profile.get("record"), model, nozzle)
        if record["base"].get("id") != code:
            raise ValueError("Materialcode stimmt nicht mit den Profildaten überein")
        identities.add(identity)
        codes.add(code)
    return deepcopy(bundle)


def bundle_from_snapshot(snapshot, printer=None):
    source = {"printer_int_name": snapshot.get("printer_int_name"),
              "nozzle_diameter": snapshot.get("nozzle_diameter")}
    names={'F012':'Creality K2 Pro','F008':'Creality K2 Plus','F018':'Creality Hi'}
    source['printer_type'] = names.get(source['printer_int_name'],'Creality '+str(source['printer_int_name']))
    if printer:
        source.update({key: printer[key] for key in ("name", "ip") if key in printer})
    bundle = {"format": FORMAT, "schema_version": 2 if snapshot.get("schema_version")==2 else 1, "source": source, "profiles": []}
    for profile in snapshot["profiles"].values() if isinstance(snapshot["profiles"], dict) else snapshot["profiles"]:
        account = profile.get("origin_account_id", snapshot.get("account_id"))
        sid = profile.get("origin_setting_id", profile["profile_setting_id"])
        if "record" not in profile:
            raise ValueError("Der Druckerdienst benötigt ein Update für vollständige Profilexporte.")
        record = deepcopy(profile["record"])
        record["base"].update(id=profile["material_id"], name=profile["name"],
                              brand=profile["brand"], colors=[profile["color"]])
        bundle["profiles"].append({"material_id": profile["material_id"],
            "origin_account_id": account, "origin_setting_id": sid,
            'printer_type': source['printer_type'], 'printer_int_name': source['printer_int_name'],
            "identity": profile.get('identity',"cloud:" + str(account) + ":" + str(sid)), "record": record,
            **({'origin_kind':'local'} if profile.get('origin')=='local' else {}),
            **({'source_profile':deepcopy(profile['source_profile'])} if 'source_profile' in profile else {}),
            **({'slicer_source':deepcopy(profile['slicer_source'])} if 'slicer_source' in profile else {})})
    return validate_bundle(bundle)


def imported_exports(manifest):
    """Validate persistent imported copies and render public tagwriter rows."""
    records = manifest.get("imported_profiles", [])
    if not isinstance(records, list):
        raise ValueError("Ungültige Liste importierter Profile")
    result = []
    codes = {p["material_id"] for p in manifest["profiles"]}
    sids = {p["profile_setting_id"] for p in manifest["profiles"]}
    identities = set()
    for entry in records:
        code, sid = entry.get("material_id"), entry.get("profile_setting_id")
        if not isinstance(code, str) or not CODE.fullmatch(code) or code in codes or not isinstance(sid, str) or not SID.fullmatch(sid) or sid in sids:
            raise ValueError("Importierte Kennung kollidiert mit einer vorhandenen Zuordnung")
        account, origin_sid = entry.get("origin_account_id"), entry.get("origin_setting_id")
        local=entry.get('origin_kind')=='local'
        expected = 'local:'+str(origin_sid) if local else "cloud:" + str(account) + ":" + str(origin_sid)
        validate_bundle({"format": FORMAT, "schema_version": 2 if local else 1,
            "source": {"printer_int_name": manifest["printer_int_name"], "nozzle_diameter": manifest["nozzle_diameter"]},
            "profiles": [{"material_id": code, "origin_account_id": account,
                          "origin_setting_id": origin_sid, "identity": entry.get("identity"), "record": entry.get("record"),
                          **({'origin_kind':'local'} if local else {})}]})
        if entry["identity"] in identities:
            raise ValueError("Importiertes Profil ist mehrfach registriert")
        if 'slicer_source' in entry:
            from cfs_slicer_policy import validate_source
            validate_source(entry['slicer_source'])
        record = deepcopy(entry["record"])
        base, kv = record["base"], record["kvParam"]
        result.append({"material_id": code, "profile_setting_id": sid,
            "name": base["name"], "brand": base["brand"], "type": kv["filament_type"],
            "color": base["colors"][0].upper(), "source_file": ('local://' if local else "imported://") + expected,
            **({'source_profile':deepcopy(entry['source_profile'])} if 'source_profile' in entry else {}),
            **({'slicer_source':deepcopy(entry['slicer_source']),'values_source':'slicer','update_status':'slicer_current'} if 'slicer_source' in entry else {}),
            "origin": 'local' if local else "imported", "identity": expected, "origin_account_id": account,
            "origin_setting_id": origin_sid, "record": record,
            "profile_metadata": {"nozzle_temperature": str(kv["nozzle_temperature"]),
                "flow_ratio": str(kv["filament_flow_ratio"]), "pressure_advance": str(kv["pressure_advance"])},
            "resolved": dict(kv, name=base["name"])})
        codes.add(code); sids.add(sid); identities.add(entry["identity"])
    return result


def plan_import(bundle, database, manifest, receipt, export):
    """Preserve existing identities, allocate a fresh code for true collisions."""
    if manifest.get('schema_version')==2:
        from cfs_mixed_core import plan_mixed_import
        return plan_mixed_import(bundle,database,manifest,receipt,export)
    bundle = validate_bundle(bundle)
    if any('slicer_source' in p for p in bundle['profiles']):raise ValueError('Slicer-Vorrang benötigt das gemischte Profilmanifest des Dienstes 2.1.0.')
    if any(bundle["source"][key] != manifest[key] for key in ("printer_int_name", "nozzle_diameter")):
        raise ValueError("Export passt nicht zum Druckermodell bzw. zur Düse des Zieldruckers")
    target = deepcopy(manifest)
    target.setdefault("imported_profiles", [])
    imported_exports(target)
    receipt = receipt or {}
    used = {entry["base"]["id"] for entry in database["result"]["list"]}
    used.update(p["material_id"] for p in target["profiles"] + target["imported_profiles"])
    used.update(receipt.get("owned_entries", {})); used.update(receipt.get("profile_bindings", {}))
    used.update(receipt.get("reserved_material_ids", []))
    cloud_by_sid = {p["profile_setting_id"]: p for p in target["profiles"]}
    copies = {p["identity"]: p for p in target["imported_profiles"]}
    available = {p["profile_setting_id"]: p for p in export.get("available_profiles", []) if p.get("status") == "unassigned"}
    rows = []
    used_names = {p['name'].casefold() for p in export.get('profiles', [])}
    for profile in bundle["profiles"]:
        source_code = profile["material_id"]
        sid = profile["origin_setting_id"]
        same_account = profile["origin_account_id"] == target["account_id"]
        existing_cloud = cloud_by_sid.get(sid) if same_account else None
        existing_copy = copies.get(profile["identity"])
        historical = next(((code, binding) for code, binding in receipt.get('profile_bindings', {}).items()
                           if binding.get('identity') == profile['identity']), None)
        if existing_cloud:
            was_enabled = existing_cloud.get('enabled', True)
            existing_cloud['enabled'] = True
            code, action = existing_cloud["material_id"], "cloud_existing" if was_enabled else 'cloud_restored'
        else:
            if existing_copy:
                code = existing_copy["material_id"]
            elif historical:
                code = historical[0]
            elif source_code not in used:
                code = source_code
            else:
                code = next((str(n) for n in range(99021, 100000) if str(n) not in used), None)
                if code is None:
                    raise ValueError("Kein freier Materialcode im Bereich 99021–99999")
            used.add(code)
            if not existing_copy and same_account and sid in available:
                binding = {"material_id": code, "profile_setting_id": sid, "enabled": True}
                target["profiles"].append(binding)
                cloud_by_sid[sid] = binding
                action = "cloud_linked"
            else:
                record = deepcopy(profile["record"])
                record.pop("userMaterial", None)
                record["base"]["id"] = code
                own_name = existing_copy['record']['base']['name'].casefold() if existing_copy else None
                occupied_names = used_names - ({own_name} if own_name else set())
                original_name = record['base']['name']
                if original_name.casefold() in occupied_names:
                    suffix = " [Import " + sid[-6:] + "]"
                    record['base']['name'] = original_name[:220] + suffix
                    sequence = 2
                    while record['base']['name'].casefold() in occupied_names:
                        record['base']['name'] = original_name[:210] + suffix + " " + str(sequence)
                        sequence += 1
                used_names.add(record['base']['name'].casefold())
                if 'filament_settings_id' in record['kvParam']:
                    record['kvParam']['filament_settings_id'] = record['base']['name']
                local_sid = sid if same_account else hashlib.sha256(("cfs-import:" + profile["identity"]).encode()).hexdigest()[:24]
                copy = {**{key: profile[key] for key in ("identity", "origin_account_id", "origin_setting_id")},
                        "material_id": code, "profile_setting_id": local_sid, "record": record}
                if existing_copy:
                    action = "copy_unchanged" if existing_copy == copy else "copy_updated"
                    target["imported_profiles"][target["imported_profiles"].index(existing_copy)] = copy
                else:
                    action = "copy_restored" if historical else "copy_created"
                    target["imported_profiles"].append(copy)
                copies[profile["identity"]] = copy
        display_name = copies[profile["identity"]]['record']['base']['name'] if profile["identity"] in copies else profile["record"]["base"]["name"]
        rows.append({"identity": profile["identity"], "name": display_name,
            "source_code": source_code, "material_id": code, "action": action,
            "profile_setting_id": next(p["profile_setting_id"] for p in target["profiles"] + target["imported_profiles"] if p["material_id"] == code),
            "retag_required": source_code != code})
    imported_exports(target)
    return target, rows


def plan_delete(codes, database, manifest, receipt):
    if not isinstance(codes, list) or not codes or len(codes) > 1000 or len(set(codes)) != len(codes) or any(not isinstance(c, str) or not CODE.fullmatch(c) for c in codes):
        raise ValueError('Bitte mindestens ein gültiges eigenes Profil zum Entfernen auswählen')
    target, updated = deepcopy(manifest), deepcopy(database)
    profiles = {p['material_id']: p for p in target['profiles'] + target.get('imported_profiles', [])}
    rows = []
    for code in codes:
        profile = profiles.get(code)
        if profile is None or not profile.get('enabled', True) or code not in (receipt or {}).get('owned_entries', {}):
            raise ValueError('Nur aktive, vom Profildienst verwaltete RFID-Profile dürfen entfernt werden: ' + code)
        owned=(receipt or {}).get('owned_entries',{}).get(code)
        found=[r for r in database['result']['list'] if r['base']['id']==code]
        if len(found)>1 or (found and digest(found[0])!=digest(owned)):
            raise ValueError('Extern veränderter Materialcode wird nicht entfernt: '+code)
        cloud_profile = profile in target['profiles']
        if cloud_profile:
            profile['enabled'] = False
        else:
            target['imported_profiles'].remove(profile)
        rows.append({'material_id': code, 'profile_setting_id': profile['profile_setting_id'],
                     'cloud_original_preserved': cloud_profile})
    updated['result']['list'] = [p for p in updated['result']['list'] if p['base']['id'] not in codes]
    updated['result']['count'] = len(updated['result']['list'])
    return target, updated, rows
