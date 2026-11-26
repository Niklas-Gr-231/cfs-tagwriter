# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Creality CFS sector-1 encoding, based on DnG-Crafts/K2-RFID.

Only the 48-byte spool record is encoded here. Printer profiles stay in the
printer's material database. See QUELLEN.md for the reference implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import secrets


KEY_DERIVATION = bytes([113, 51, 98, 117, 94, 116, 49, 110, 113, 102, 90, 40, 112, 102, 36, 49])
KEY_DATA = bytes([72, 64, 67, 70, 107, 82, 110, 122, 64, 75, 65, 116, 66, 74, 112, 50])
DEFAULT_KEY = bytes.fromhex("FFFFFFFFFFFF")
WEIGHT_LENGTHS = {1000: "0330", 750: "0247", 600: "0198", 500: "0165", 250: "0082"}
MAX_WEIGHT_G=30300  # 9999 whole metres at the reference conversion 330 m/kg.

def validate_weight(grams):
    if isinstance(grams,bool) or not isinstance(grams,int) or not 0<=grams<=MAX_WEIGHT_G:
        raise ValueError(f"Restmenge muss eine ganze Grammzahl zwischen 0 und {MAX_WEIGHT_G} sein.")

def weight_to_length(grams):
    validate_weight(grams)
    metres=0 if grams==0 else max(1,grams*33//100)
    return f"{metres:04d}"

def length_to_weight(code):
    # Preserve the original named sizes and avoid read/rewrite rounding drift.
    legacy=next((g for g,value in WEIGHT_LENGTHS.items() if value==code),None)
    if legacy is not None:return legacy
    if not isinstance(code,str) or not re.fullmatch(r"[0-9]{4}",code):return None
    return (int(code)*100+32)//33

DEFAULT_MATERIALS = [
    {"id": "00001", "name": "Generic PLA", "brand": "Generic", "type": "PLA"},
    {"id": "00003", "name": "Generic PETG", "brand": "Generic", "type": "PETG"},
    {"id": "00004", "name": "Generic ABS", "brand": "Generic", "type": "ABS"},
    {"id": "00007", "name": "Generic ASA", "brand": "Generic", "type": "ASA"},
]


@dataclass
class TagSpec:
    material_id: str
    color: str
    weight_g: int = 1000
    serial: str = ""
    name: str = ""


def new_serial() -> str:
    return f"{secrets.randbelow(900_000):06d}"


def validate_spec(spec: TagSpec) -> None:
    if not isinstance(spec.material_id, str) or not re.fullmatch(r"[A-Za-z0-9]{5}", spec.material_id):
        raise ValueError("Der Materialcode muss genau 5 Buchstaben/Ziffern enthalten, z. B. 00001.")
    if not isinstance(spec.color, str) or not re.fullmatch(r"#?[0-9A-Fa-f]{6}", spec.color):
        raise ValueError("Die Farbe muss ein RGB-Hexcode sein, z. B. #3366FF.")
    validate_weight(spec.weight_g)
    if not isinstance(spec.serial, str) or not re.fullmatch(r"[0-9]{6}", spec.serial):
        raise ValueError("Die Rollen-Seriennummer muss genau 6 Ziffern enthalten.")
    if not isinstance(spec.name, str) or len(spec.name) > 120:
        raise ValueError("Der lokale Profilname darf höchstens 120 Zeichen enthalten.")


def _aes(data: bytes, key: bytes, *, decrypt: bool = False) -> bytes:
    if not data or len(data) % 16:
        raise ValueError("AES-Daten müssen aus vollständigen 16-Byte-Blöcken bestehen.")
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    context = cipher.decryptor() if decrypt else cipher.encryptor()
    return context.update(data) + context.finalize()


def derive_key(uid: bytes | str) -> bytes:
    try:
        uid = bytes.fromhex(uid) if isinstance(uid, str) else bytes(uid)
    except (TypeError, ValueError) as exc:
        raise ValueError("Ungültige Tag-UID.") from exc
    if len(uid) != 4:
        raise ValueError("Diese Version unterstützt ausschließlich Tags mit 4-Byte-UID.")
    return _aes(uid * 4, KEY_DERIVATION)[:6]


def build_plaintext(spec: TagSpec) -> bytes:
    validate_spec(spec)
    # The reference writers use this literal. Its five characters are opaque;
    # interpreting them as a calendar date would reject valid existing tags.
    stamp = "AB124"
    record = (
        stamp + "0276" + "A2" + "1" + spec.material_id
        + "0" + spec.color.lstrip("#").upper() + weight_to_length(spec.weight_g)
        + spec.serial + "0" * 14
    ).encode("ascii")
    assert len(record) == 48
    return record


def encrypt_payload(plaintext: bytes) -> bytes:
    if len(plaintext) != 48:
        raise ValueError("Ein Creality-Datensatz muss genau 48 Bytes enthalten.")
    return _aes(plaintext, KEY_DATA)


def decode_payload(encrypted: bytes) -> dict:
    if len(encrypted) != 48:
        raise ValueError("Ein Creality-Datensatz muss genau 48 Bytes enthalten.")
    try:
        record = _aes(encrypted, KEY_DATA, decrypt=True).decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Kein gültiger Creality-Datensatz.") from exc
    if (
        not re.fullmatch(r"[0-9A-Za-z]{5}", record[:5])
        or not re.fullmatch(r"[0-9A-Za-z]{4}", record[5:9])
        or not re.fullmatch(r"[0-9A-Za-z]{2}", record[9:11])
        or record[11] != "1"
        or not re.fullmatch(r"[A-Za-z0-9]{5}", record[12:17])
        or record[17] != "0"
        or not re.fullmatch(r"[0-9A-Fa-f]{6}", record[18:24])
        or not re.fullmatch(r"[0-9A-Fa-f]{4}", record[24:28])
        or not re.fullmatch(r"[0-9]{6}", record[28:34])
        or not all(32 <= ord(char) < 127 for char in record[34:])
    ):
        raise ValueError("Kein gültiger Creality-Datensatz.")
    weight=length_to_weight(record[24:28])
    return {
        "material_id": record[12:17], "color": "#" + record[18:24].upper(),
        "weight_g":weight,"weight_estimated":record[24:28] not in WEIGHT_LENGTHS.values(),"length_code":record[24:28], "serial": record[28:34],
        "name": "", "vendor_code": record[5:9], "batch": record[9:11],
        "date_code": record[:5], "plaintext": record,
    }


def _scalar(value, default=""):
    if isinstance(value, list):
        return value[0] if value else default
    return default if value is None else value


def _is_slicer_profile(entry: dict) -> bool:
    return "filament_settings_id" in entry or entry.get("from") == "User" or ("inherits" in entry and "name" in entry)


def _slicer_parent(name: str, source: Path) -> Path | None:
    # Parent names are preset names, never arbitrary paths from a JSON file.
    if not name or Path(name).name != name or name in (".", ".."):
        return None
    filename = name + ".json"
    candidates = [source.parent / filename]
    for ancestor in source.parents:
        candidates.extend([
            ancestor / "system" / "Creality" / "filament" / filename,
            ancestor / "system" / "Custom" / "filament" / filename,
        ])
    # Also resolve profiles copied/exported out of their installation folder.
    local = Path.home() / ".config" / "Creality" / "Creality Print"
    if local.is_dir():
        for version in sorted(local.iterdir(), reverse=True):
            candidates.extend([
                version / "system" / "Creality" / "filament" / filename,
                version / "system" / "Custom" / "filament" / filename,
            ])
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _resolve_slicer(entry: dict, source: Path, stack=()) -> dict:
    if len(stack) >= 16 or source.resolve() in stack:
        raise ValueError("Zirkuläre oder zu tiefe Vererbung im Slicerprofil.")
    parent_name = str(_scalar(entry.get("inherits")))
    result = {}
    parent_path = _slicer_parent(parent_name, source) if parent_name else None
    if parent_path is not None:
        with parent_path.open(encoding="utf-8-sig") as stream:
            parent = json.load(stream)
        if isinstance(parent, dict):
            result.update(_resolve_slicer(parent, parent_path, (*stack, source.resolve())))
    result.update(entry)
    return result


def _slicer_material(entry: dict, source: Path) -> dict:
    resolved = _resolve_slicer(entry, source)
    notes = _scalar(entry.get("filament_notes"))
    metadata = {}
    # Free-form notes remain valid; only explicit JSON metadata supplies a code.
    if isinstance(notes, str):
        try:
            decoded = json.loads(notes)
            if isinstance(decoded, str):
                decoded = json.loads(decoded)
            if isinstance(decoded, dict):
                metadata = decoded
        except (ValueError, TypeError):
            pass
    code = str(metadata.get("id", ""))
    if code and not re.fullmatch(r"[A-Za-z0-9]{5}", code):
        raise ValueError("Der Materialcode in den Profil-Notizen muss genau 5 Buchstaben/Ziffern enthalten.")
    color = str(_scalar(resolved.get("default_filament_colour", resolved.get("filament_colour", ""))))
    if color and not re.fullmatch(r"#?[0-9A-Fa-f]{6}", color):
        color = ""
    return {
        "id": code, "name": str(_scalar(entry.get("name", entry.get("filament_settings_id", source.stem)))),
        "brand": str(_scalar(resolved.get("filament_vendor", metadata.get("vendor", "")))),
        "type": str(_scalar(resolved.get("filament_type", metadata.get("type", "")))),
        "color": ("#" + color.lstrip("#").upper()) if color else "",
        "source": "slicer", "source_file": str(source.resolve()),
        "mapping_status": "declared" if code else "missing",
        "profile_metadata": {
            "nozzle_temperature": str(_scalar(resolved.get("nozzle_temperature"))),
            "flow_ratio": str(_scalar(resolved.get("filament_flow_ratio"))),
            "pressure_advance": str(_scalar(resolved.get("pressure_advance"))),
        },
    }


def load_materials(path: str | Path) -> list[dict]:
    """Read a material DB, a native slicer preset, or a list of either.

    A slicer preset without an explicit notes.id is imported without a CFS code.
    Its base_id / inherited filament_id never establish a custom CFS mapping.
    """
    path = Path(path)
    with path.open(encoding="utf-8-sig") as stream:
        data = json.load(stream)
    if isinstance(data, dict) and _is_slicer_profile(data):
        entries = [data]
    elif isinstance(data, dict) and isinstance(data.get("result"), dict):
        entries = data["result"].get("list", [])
    elif isinstance(data, dict):
        entries = data.get("materials", data.get("profiles", data.get("list", [])))
    else:
        entries = data
    if not isinstance(entries, list):
        raise ValueError("Keine Materialliste in der JSON-Datei gefunden.")
    materials = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if _is_slicer_profile(entry):
            item = _slicer_material(entry, path)
            # Profile names, rather than the possibly absent CFS ID, distinguish
            # different colors/settings in the user's native slicer presets.
            materials[("slicer", item["source_file"], item["name"])] = item
            continue
        base = entry.get("base", entry)
        if not isinstance(base, dict):
            continue
        code = str(base.get("id", ""))
        if not re.fullmatch(r"[A-Za-z0-9]{5}", code):
            continue
        materials.setdefault(("material", code), {
            "id": code, "name": str(base.get("name", code)),
            "brand": str(base.get("brand", "")),
            "type": str(base.get("meterialType", base.get("materialType", base.get("type", "")))),
        })
    if not materials:
        raise ValueError("Keine Slicerprofile oder gültigen Materialcodes mit genau 5 Zeichen gefunden.")
    return sorted(materials.values(), key=lambda item: (item["brand"].lower(), item["name"].lower(), item["id"]))
