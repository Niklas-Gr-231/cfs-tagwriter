# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Serial connection to CFS_Mega_Bridge; writes only sector 1 of a 1K tag."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import threading
import time

from cfs_codec import (
    DEFAULT_KEY, TagSpec, build_plaintext, decode_payload, derive_key,
    encrypt_payload, validate_spec,
)


class BridgeError(Exception):
    def __init__(self, code: str, message: str, *, backup: str | None = None):
        self.code = code
        self.backup = backup
        super().__init__(message)


MESSAGES = {
    "NO_TAG": "Kein Tag erkannt. Karte flach und dicht an die Antennenfläche halten.",
    "UID_MISMATCH": "Es liegt eine andere Karte auf. Bitte diese Karte zuerst erneut lesen.",
    "UNSUPPORTED_TAG": "Benötigt wird MIFARE Classic 1K mit einer 4-Byte-UID.",
    "AUTH_FAILED": "Der Sektorschlüssel passt nicht. Diese Karte kann nicht bearbeitet werden.",
    "READ_FAILED": "Lesen fehlgeschlagen. Karte ruhig aufliegen lassen und Kontakte prüfen.",
    "WRITE_FAILED": "Schreiben fehlgeschlagen. Karte ruhig aufliegen lassen.",
    "VERIFY_FAILED": "Die Rückleseprüfung ist fehlgeschlagen. Der Schreibvorgang ist unvollständig.",
    "ACCESS_BITS": "Der Tag hat abweichende Zugriffsrechte. Diese werden nicht automatisch geändert.",
    "PARSE_ERROR": "Arduino und PC sprechen nicht dasselbe Protokoll. Den mitgelieferten Bridge-Sketch hochladen.",
    "READER_UNAVAILABLE": "Der RC522 antwortet nicht. Versorgung und Verdrahtung prüfen.",
}


class Bridge:
    def __init__(self, port: str, *, serial_factory=None, reset_wait: float = 2.0):
        self.port = port
        self._lock = threading.RLock()
        self._serial = None
        if serial_factory is None:
            try:
                import serial
            except ImportError as exc:
                raise BridgeError("DEPENDENCY", "python3-serial fehlt. Installation: sudo apt install python3-serial") from exc
            serial_factory = serial.Serial
        try:
            self._serial = serial_factory(
                port=port, baudrate=115200, timeout=0.2, write_timeout=2, exclusive=True,
            )
            if reset_wait:
                time.sleep(reset_wait)
            self._serial.reset_input_buffer()
            self.hello()
        except BridgeError:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise BridgeError(
                "SERIAL", f"USB-Port {port} konnte nicht geöffnet werden: {exc}. "
                "Den seriellen Monitor der Arduino IDE vorher schließen.",
            ) from exc

    def close(self):
        # close() may be called while a background operation is waiting for I/O.
        device = self._serial
        if device is not None:
            self._serial = None
            try:
                device.close()
            except Exception:
                pass

    def _command(self, cmd: str, *args, timeout: float = 7.5) -> dict:
        with self._lock:
            if self._serial is None:
                raise BridgeError("SERIAL", "Keine USB-Verbindung.")
            line = " ".join([cmd, *(str(arg) for arg in args)]) + "\n"
            if len(line) > 190 or any("\n" in str(arg) or "\r" in str(arg) for arg in args):
                raise BridgeError("PROTOCOL", "Ungültiger Befehl.")
            try:
                self._serial.write(line.encode("ascii"))
                self._serial.flush()
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    raw = self._serial.readline()
                    if not raw:
                        continue
                    try:
                        response = json.loads(raw.decode("ascii"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if not isinstance(response, dict) or response.get("cmd") != cmd:
                        continue
                    if response.get("ok") is not True:
                        code = str(response.get("code", "DEVICE_ERROR"))
                        raise BridgeError(code, MESSAGES.get(code, "Arduino-Fehler: " + str(response.get("message", code))))
                    return response
            except BridgeError:
                raise
            except Exception as exc:
                raise BridgeError("SERIAL", f"USB-Verbindung unterbrochen: {exc}") from exc
            raise BridgeError(
                "TIMEOUT", "Keine passende Antwort vom Arduino. Bridge-Sketch hochgeladen? "
                "Seriellen Monitor schließen und USB-Verbindung erneut öffnen.",
            )

    def hello(self) -> dict:
        response = self._command("HELLO")
        if response.get("protocol") != 1:
            raise BridgeError("PROTOCOL", "Unbekannte Firmware-Version. Die passende Mega-/Nano-Bridge über die Einrichtung aufspielen.")
        if response.get("reader_version") in (0, 255):
            raise BridgeError("READER_UNAVAILABLE", MESSAGES["READER_UNAVAILABLE"])
        return response

    def scan(self) -> dict:
        response = self._command("SCAN")
        uid = response.get("uid", "")
        tag_type = response.get("type", "")
        if not isinstance(uid, str) or not re.fullmatch(r"[0-9A-Fa-f]{8}", uid) or tag_type != "MIFARE_1K":
            raise BridgeError("UNSUPPORTED_TAG", MESSAGES["UNSUPPORTED_TAG"])
        return {**response, "uid": uid.upper(), "tag_type": tag_type}

    def _read_block(self, uid: str, block: int, key: bytes) -> bytes:
        response = self._command("READ", uid, block, key.hex().upper())
        data = response.get("data", "")
        if response.get("uid", "").upper() != uid or response.get("block") != block:
            raise BridgeError("PROTOCOL", "Die Arduino-Antwort gehört nicht zum angeforderten Block.")
        if not isinstance(data, str) or not re.fullmatch(r"[0-9A-Fa-f]{32}", data):
            raise BridgeError("PROTOCOL", "Unvollständiger Datenblock vom Arduino.")
        return bytes.fromhex(data)

    def _inspect(self, expected_uid: str | None = None) -> dict:
        scan = self.scan()
        uid = scan["uid"]
        if expected_uid is not None and uid != expected_uid:
            raise BridgeError("UID_MISMATCH", MESSAGES["UID_MISMATCH"])
        tag_key = derive_key(uid)
        first = None
        current_key = None
        authentication = ""
        for key, mode in ((DEFAULT_KEY, "default"), (tag_key, "creality")):
            try:
                first = self._read_block(uid, 4, key)
                current_key, authentication = key, mode
                break
            except BridgeError as exc:
                if exc.code != "AUTH_FAILED":
                    raise
        if first is None or current_key is None:
            raise BridgeError("AUTH_FAILED", MESSAGES["AUTH_FAILED"])
        blocks = {4: first}
        for block in (5, 6, 7):
            blocks[block] = self._read_block(uid, block, current_key)
        encrypted = b"".join(blocks[block] for block in (4, 5, 6))
        try:
            profile = decode_payload(encrypted)
        except ValueError:
            profile = None
        return {
            "uid": uid, "tag_type": scan["tag_type"], "formatted": profile is not None,
            "profile": profile, "authentication": authentication,
            "cipher_hex": encrypted.hex().upper(), "access_hex": blocks[7][6:10].hex().upper(),
            "_blocks": blocks, "_key": current_key,
        }

    def read_tag(self) -> dict:
        with self._lock:
            result = self._inspect()
            return {key: value for key, value in result.items() if not key.startswith("_")}

    def write_tag(self, expected_uid: str, spec: TagSpec, backup_dir: Path) -> dict:
        validate_spec(spec)
        if not isinstance(expected_uid, str) or not re.fullmatch(r"[0-9A-Fa-f]{8}", expected_uid):
            raise BridgeError("UID_MISMATCH", "Bitte die zu beschreibende Karte zuerst lesen.")
        expected_uid = expected_uid.upper()
        encrypted = encrypt_payload(build_plaintext(spec))
        with self._lock:
            current = self._inspect(expected_uid)
            # Transport-mode rights permit reversible Key-A writes. Reject all
            # other rights before modifying any payload block.
            if current["_blocks"][7][6:9] != bytes.fromhex("FF0780"):
                raise BridgeError("ACCESS_BITS", MESSAGES["ACCESS_BITS"])
            backup_dir = Path(backup_dir)
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / f"{datetime.now():%Y%m%d-%H%M%S-%f}_{expected_uid}.json"
                backup = {
                    "format": "cfs-mega-sector1-backup-v1", "uid": expected_uid,
                    "created": datetime.now().astimezone().isoformat(),
                    "authentication": current["authentication"],
                    "key_a": current["_key"].hex().upper(),
                    "blocks": {str(n): value.hex().upper() for n, value in current["_blocks"].items()},
                    "note": "Key A is masked in the raw trailer; key_a records the authenticated key. "
                            "No automatic full-card restore is provided.",
                }
                with backup_path.open("x", encoding="utf-8") as stream:
                    json.dump(backup, stream, ensure_ascii=False, indent=2)
                    stream.write("\n")
            except OSError as exc:
                raise BridgeError("BACKUP", f"Sicherung konnte nicht gespeichert werden; nichts geschrieben: {exc}") from exc
            try:
                old_key = current["_key"]
                for block in (4, 5, 6):
                    data = encrypted[(block - 4) * 16:(block - 3) * 16]
                    response = self._command("WRITE", expected_uid, block, old_key.hex().upper(), data.hex().upper())
                    if response.get("uid", "").upper() != expected_uid or response.get("block") != block or response.get("verified") is not True:
                        raise BridgeError("VERIFY_FAILED", MESSAGES["VERIFY_FAILED"])
                written = b"".join(self._read_block(expected_uid, n, old_key) for n in (4, 5, 6))
                if written != encrypted:
                    raise BridgeError("VERIFY_FAILED", MESSAGES["VERIFY_FAILED"])
                new_key = derive_key(expected_uid)
                if old_key != new_key or current["_blocks"][7][10:16] != new_key:
                    response = self._command("KEY", expected_uid, old_key.hex().upper(), new_key.hex().upper())
                    if response.get("uid", "").upper() != expected_uid or response.get("verified") is not True:
                        raise BridgeError("VERIFY_FAILED", MESSAGES["VERIFY_FAILED"])
                verified = self._inspect(expected_uid)
                if verified["authentication"] != "creality" or verified["cipher_hex"] != encrypted.hex().upper() or verified["access_hex"] != current["access_hex"] or verified["_blocks"][7][10:16] != new_key:
                    raise BridgeError("VERIFY_FAILED", MESSAGES["VERIFY_FAILED"])
                return {"uid": expected_uid, "verified": True, "backup": str(backup_path)}
            except BridgeError as exc:
                raise BridgeError(
                    exc.code,
                    f"{exc}\nDer Schreibvorgang ist möglicherweise unvollständig. "
                    f"Sicherung: {backup_path}\nKarte erneut lesen, bevor du weiterarbeitest.",
                    backup=str(backup_path),
                ) from exc
