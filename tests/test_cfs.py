# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Host-side CFS tests. Run: python -m unittest discover -s tests

No pyserial installation or physical reader is needed. The transport model uses
the documented bridge protocol; firmware has a separate real-.ino C++ harness.
AES fixtures were independently reproduced with Python cryptography and OpenSSL.
"""
from __future__ import annotations

from collections import deque
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1] / "app" / "creality-cfs-writer"
sys.path.insert(0, str(PACKAGE))

from cfs_codec import (  # noqa: E402
    DEFAULT_KEY, TagSpec, build_plaintext, decode_payload, derive_key,
    encrypt_payload, load_materials, new_serial, validate_spec,
)
from cfs_device import Bridge, BridgeError  # noqa: E402


UID = "11223344"
OTHER_UID = "01020304"
DERIVED_KEY = bytes.fromhex("16785090548E")
PLA_RED = TagSpec("00001", "#FF0000", 1000, "000001", "Mein rotes PLA")
PLA_RED_PLAIN = b"AB1240276A21000010FF0000033000000100000000000000"
PLA_RED_CIPHER = bytes.fromhex(
    "E7399BFFFE09D37BB07CC5C4C17DC9FA"
    "11A04C3E0D0BDF51734B011C49C7A9AB"
    "FAC8F07509292DF943D4CDF64CBA06A1"
)
FORMAT_PLAIN = b"AB1240276A210100100000FF016500000100000000000000"
FORMAT_CIPHER = bytes.fromhex(
    "57F25B78076D4C1797B1BE35CA269540"
    "C2381A51F9728D1E66BAA1FF4781D677"
    "FAC8F07509292DF943D4CDF64CBA06A1"
)


class MifareTag:
    """A sector model with masked Key A and transport-readable Key B."""

    def __init__(self, uid=UID, *, key=DEFAULT_KEY, gp=0x42):
        self.uid = uid
        self.key_a = key
        self.key_b = key
        self.access = bytes.fromhex("FF0780") + bytes([gp])
        # Blank chips do NOT guarantee zero-filled user data (NXP datasheet).
        self.blocks = {4: b"\xAA" * 16, 5: bytes(range(16)), 6: b"\xFF" * 16}
        self.mutations = []
        self.before_mutation = None

    def read(self, block):
        if block == 7:
            return b"\0" * 6 + self.access + self.key_b
        return self.blocks[block]

    def mutate(self, command, block, data):
        if self.before_mutation:
            self.before_mutation(command, block, data)
        self.mutations.append((command, block, data))
        if command == "WRITE":
            self.blocks[block] = data
        else:
            self.key_a = self.key_b = data


class FakeSerial:
    """Serial framing plus NFC state, with fault injection at real boundaries."""

    def __init__(self, tag, **kwargs):
        self.tag = tag
        self.kwargs = kwargs
        self.requests = []
        self.responses = deque()
        self.closed = False
        self.reset_count = self.flush_count = 0
        self.before_request = None
        self.response_filter = None
        self.noise_once = False
        self.fail_on = None

    def reset_input_buffer(self):
        self.reset_count += 1
        self.responses.clear()

    def flush(self):
        self.flush_count += 1

    def close(self):
        self.closed = True

    def readline(self):
        return self.responses.popleft() if self.responses else b""

    def write(self, data):
        if self.closed:
            raise OSError("port closed")
        if not data.endswith(b"\n") or b"\r" in data:
            raise AssertionError("Bad serial frame")
        request = tuple(data.decode("ascii").strip().split())
        self.requests.append(request)
        if self.before_request:
            self.before_request(request)
        if self.fail_on and self.fail_on(request):
            raise BrokenPipeError("injected USB disconnect")
        response = self.handle(request)
        if self.response_filter:
            response = self.response_filter(request, response)
        if self.noise_once:
            self.noise_once = False
            self.responses.extend([
                b"boot chatter\n", b"{not-json}\n", b"[]\n",
                b'{"ok":true,"cmd":"BOOT","protocol":1}\n',
            ])
        self.responses.append(json.dumps(response).encode("ascii") + b"\n")
        return len(data)

    def handle(self, request):
        command = request[0]

        def error(code):
            return {"cmd": command, "ok": False, "code": code}

        if command == "HELLO":
            return {"cmd": command, "ok": True, "protocol": 1, "reader_version": 0x92}
        if command == "SCAN":
            return {"cmd": command, "ok": True, "uid": self.tag.uid,
                    "type": "MIFARE_1K", "uid_size": 4, "sak": 8}
        if request[1] != self.tag.uid:
            return error("UID_MISMATCH")
        key = bytes.fromhex(request[2] if command == "KEY" else request[3])
        if key != self.tag.key_a:
            return error("AUTH_FAILED")
        if command == "KEY":
            if self.tag.access[:3] != bytes.fromhex("FF0780"):
                return error("ACCESS_BITS")
            new_key = bytes.fromhex(request[3])
            self.tag.mutate("KEY", 7, new_key)
            return {"cmd": command, "ok": True, "uid": self.tag.uid, "verified": True}
        block = int(request[2])
        # Same externally documented restrictions as the separate firmware.
        if block not in ((4, 5, 6, 7) if command == "READ" else (4, 5, 6)):
            return error("PARSE_ERROR")
        if command == "READ":
            return {"cmd": command, "ok": True, "uid": self.tag.uid, "block": block,
                    "data": self.tag.read(block).hex().upper()}
        if command == "WRITE":
            self.tag.mutate("WRITE", block, bytes.fromhex(request[4]))
            return {"cmd": command, "ok": True, "uid": self.tag.uid,
                    "block": block, "verified": True}
        return error("PARSE_ERROR")


class CodecTests(unittest.TestCase):
    def test_independent_uid_key_vector(self):
        self.assertEqual(derive_key(bytes.fromhex(UID)), DERIVED_KEY)
        self.assertEqual(derive_key("11 22 33 44"), DERIVED_KEY)

    def test_independent_payload_vector_and_exact_offsets(self):
        self.assertEqual(build_plaintext(PLA_RED), PLA_RED_PLAIN)
        self.assertEqual(len(PLA_RED_PLAIN), 48)
        self.assertEqual(encrypt_payload(PLA_RED_PLAIN), PLA_RED_CIPHER)
        decoded = decode_payload(PLA_RED_CIPHER)
        self.assertEqual(decoded["material_id"], "00001")
        self.assertEqual(decoded["color"], "#FF0000")
        self.assertEqual(decoded["weight_g"], 1000)
        self.assertEqual(decoded["serial"], "000001")
        self.assertEqual(decoded["date_code"], "AB124")
        self.assertEqual(decoded["plaintext"], PLA_RED_PLAIN.decode("ascii"))
        self.assertEqual(decoded["name"], "")  # Local name never enters tag data.

    def test_format_fixture_decodes_without_calendar_assumption(self):
        self.assertEqual(encrypt_payload(FORMAT_PLAIN), FORMAT_CIPHER)
        profile = decode_payload(FORMAT_CIPHER)
        self.assertEqual(profile["material_id"], "01001")
        self.assertEqual(profile["color"], "#0000FF")
        self.assertEqual(profile["weight_g"], 500)

    def test_weight_code_mapping(self):
        for grams, code in [(250, b"0082"), (500, b"0165"), (600, b"0198"),
                            (750, b"0247"), (1000, b"0330")]:
            with self.subTest(grams=grams):
                plain = build_plaintext(replace(PLA_RED, weight_g=grams))
                self.assertEqual(plain[24:28], code)
                self.assertEqual(decode_payload(encrypt_payload(plain))["weight_g"], grams)

    def test_malformed_specs_fail_before_encoding(self):
        bad = [
            {"material_id": "0001"}, {"material_id": "000001"},
            {"material_id": "é0000"}, {"material_id": "A BCD"},
            {"color": "#GG0000"}, {"color": "12345"}, {"color": "##FF0000"},
            {"color": 0}, {"weight_g": 30301}, {"weight_g": True},
            {"serial": ""}, {"serial": 123456}, {"serial": "12345\n"},
            {"serial": "１２３４５６"}, {"name": None}, {"name": "x" * 121},
        ]
        for changes in bad:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    build_plaintext(replace(PLA_RED, **changes))

    def test_invalid_uid_and_payload_lengths_are_rejected(self):
        for uid in ["", "not hex", "010203", "01020304050607", None]:
            with self.subTest(uid=uid), self.assertRaises(ValueError):
                derive_key(uid)
        for size in [0, 1, 16, 47, 49]:
            with self.subTest(size=size):
                with self.assertRaises(ValueError):
                    encrypt_payload(b"A" * size)
                with self.assertRaises(ValueError):
                    decode_payload(b"A" * size)
        with self.assertRaises(ValueError):
            decode_payload(encrypt_payload(b"\0" * 48))

    def test_random_serial_has_fixed_ascii_width(self):
        for _ in range(50):
            serial = new_serial()
            self.assertRegex(serial, r"^[0-9]{6}$")
            validate_spec(replace(PLA_RED, serial=serial))

    def test_database_import_deduplicates_nozzle_variants_and_keeps_names(self):
        entries = [
            {"base": {"id": "00003", "name": "Generic PETG", "brand": "Generic",
                      "meterialType": "PETG"}, "nozzleDiameter": ["0.4"]},
            {"base": {"id": "00003", "name": "Generic PETG", "brand": "Generic",
                      "meterialType": "PETG"}, "nozzleDiameter": ["0.6"]},
            {"base": {"id": "PLA01", "name": "Meine rote Rolle", "brand": "Acme",
                      "materialType": "PLA"}},
            None, "garbage", {"base": []}, {"base": {"id": "1234"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "materials.json"
            path.write_text(json.dumps({"result": {"list": entries}}), encoding="utf-8-sig")
            materials = load_materials(path)
        self.assertEqual([row["id"] for row in materials], ["PLA01", "00003"])
        self.assertEqual(materials[0]["name"], "Meine rote Rolle")
        self.assertEqual(materials[1]["type"], "PETG")

    def test_bad_database_shapes_and_json_are_rejected(self):
        for data in [None, 0, [], {}, {"result": {"list": {}}},
                     [{"base": {"id": "bad"}}]]:
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "bad.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_materials(path)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("not JSON", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_materials(path)


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.backup_dir = Path(self.temp.name) / "backups"
        self.tag = MifareTag()
        self.serial = FakeSerial(self.tag)
        self.bridge = Bridge("/dev/fake", serial_factory=self.factory, reset_wait=0)
        self.addCleanup(self.bridge.close)

    def factory(self, **kwargs):
        self.serial.kwargs = kwargs
        return self.serial

    def assert_no_mutation(self):
        self.assertEqual(self.tag.mutations, [])

    def backup_files(self):
        return list(self.backup_dir.glob("*.json")) if self.backup_dir.exists() else []

    def test_connection_protocol_noise_and_close(self):
        self.assertEqual(self.serial.kwargs["baudrate"], 115200)
        self.assertEqual(self.serial.reset_count, 1)
        self.assertTrue(self.serial.kwargs["exclusive"])
        self.serial.noise_once = True
        self.assertEqual(self.bridge.hello()["protocol"], 1)
        self.bridge.close()
        self.assertTrue(self.serial.closed)
        with self.assertRaises(BridgeError) as ctx:
            self.bridge.scan()
        self.assertEqual(ctx.exception.code, "SERIAL")

    def test_read_arbitrary_initial_data_is_read_only(self):
        profile = self.bridge.read_tag()
        self.assertEqual(profile["uid"], UID)
        self.assertEqual(profile["authentication"], "default")
        self.assertFalse(profile["formatted"])
        self.assertEqual(profile["access_hex"], "FF078042")
        self.assertNotIn("_key", profile)
        self.assert_no_mutation()

    def test_full_write_backup_precedes_mutation_and_key_changes_last(self):
        original = {str(block): self.tag.read(block).hex().upper() for block in (4, 5, 6, 7)}

        def verify_backup_exists(command, block, data):
            files = self.backup_files()
            self.assertEqual(len(files), 1)
            backup = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(backup["uid"], UID)
            self.assertEqual(backup["key_a"], "FFFFFFFFFFFF")
            self.assertEqual(backup["blocks"], original)

        self.tag.before_mutation = verify_backup_exists
        result = self.bridge.write_tag(UID, PLA_RED, self.backup_dir)
        self.assertTrue(result["verified"])
        self.assertEqual(Path(result["backup"]), self.backup_files()[0])
        self.assertEqual([(cmd, block) for cmd, block, _ in self.tag.mutations],
                         [("WRITE", 4), ("WRITE", 5), ("WRITE", 6), ("KEY", 7)])
        self.assertEqual(b"".join(self.tag.blocks[i] for i in (4, 5, 6)), PLA_RED_CIPHER)
        self.assertEqual(self.tag.key_a, DERIVED_KEY)
        self.assertEqual(self.tag.key_b, DERIVED_KEY)
        self.assertEqual(self.tag.access, bytes.fromhex("FF078042"))
        key_index = next(i for i, request in enumerate(self.serial.requests) if request[0] == "KEY")
        later = self.serial.requests[key_index + 1:]
        self.assertTrue(any(r[0] == "READ" and r[-1] == DERIVED_KEY.hex().upper() for r in later))
        profile = self.bridge.read_tag()
        self.assertEqual(profile["authentication"], "creality")
        self.assertEqual(profile["profile"]["color"], "#FF0000")

    def test_repeated_clock_tick_still_produces_distinct_backups(self):
        from datetime import datetime
        with patch('cfs_device.datetime') as clock:
            clock.now.return_value=datetime(2026,1,1,12)
            first=self.bridge.write_tag(UID,PLA_RED,self.backup_dir)
            first_contents=Path(first['backup']).read_bytes()
            second=self.bridge.write_tag(UID,replace(PLA_RED,color='#0000FF'),self.backup_dir)
        self.assertNotEqual(first['backup'],second['backup'])
        self.assertEqual(Path(first['backup']).read_bytes(),first_contents)
        self.assertEqual(len(self.backup_files()),2)
        self.assertTrue(second['verified'])

    def test_rewrite_own_tag_without_another_key_change(self):
        self.bridge.write_tag(UID, PLA_RED, self.backup_dir)
        self.tag.mutations.clear()
        blue = replace(PLA_RED, color="#0000FF", serial="000002")
        result = self.bridge.write_tag(UID, blue, self.backup_dir)
        self.assertTrue(result["verified"])
        self.assertEqual([(cmd, block) for cmd, block, _ in self.tag.mutations],
                         [("WRITE", 4), ("WRITE", 5), ("WRITE", 6)])
        profile = self.bridge.read_tag()["profile"]
        self.assertEqual(profile["color"], "#0000FF")
        self.assertEqual(profile["serial"], "000002")
        backups = [json.loads(p.read_text(encoding="utf-8")) for p in self.backup_files()]
        self.assertEqual(len(backups), 2)
        self.assertIn("creality", [backup["authentication"] for backup in backups])

    def test_uid_swap_before_preflight_does_not_create_backup_or_write(self):
        self.tag.uid = OTHER_UID
        with self.assertRaises(BridgeError) as ctx:
            self.bridge.write_tag(UID, PLA_RED, self.backup_dir)
        self.assertEqual(ctx.exception.code, "UID_MISMATCH")
        self.assert_no_mutation()
        self.assertEqual(self.backup_files(), [])

    def test_uid_swap_immediately_before_write_is_blocked_by_protocol(self):
        def swap(request):
            if request[0] == "WRITE":
                self.tag.uid = OTHER_UID
        self.serial.before_request = swap
        with self.assertRaises(BridgeError) as ctx:
            self.bridge.write_tag(UID, PLA_RED, self.backup_dir)
        self.assertEqual(ctx.exception.code, "UID_MISMATCH")
        self.assertTrue(Path(ctx.exception.backup).is_file())
        self.assert_no_mutation()

    def test_nonstandard_access_rejected_before_any_mutation(self):
        self.tag.access = bytes.fromhex("7F078869")
        with self.assertRaises(BridgeError) as ctx:
            self.bridge.write_tag(UID, PLA_RED, self.backup_dir)
        self.assertEqual(ctx.exception.code, "ACCESS_BITS")
        self.assert_no_mutation()
        self.assertEqual(self.backup_files(), [])

    def test_unknown_key_fails_without_write_or_backup(self):
        self.tag.key_a = self.tag.key_b = bytes.fromhex("123456789ABC")
        for operation in (self.bridge.read_tag,
                          lambda: self.bridge.write_tag(UID, PLA_RED, self.backup_dir)):
            with self.assertRaises(BridgeError) as ctx:
                operation()
            self.assertEqual(ctx.exception.code, "AUTH_FAILED")
        self.assert_no_mutation()
        self.assertEqual(self.backup_files(), [])

    def test_io_failure_after_first_write_retains_backup_and_reports_its_path(self):
        self.serial.fail_on = lambda request: request[:3] == ("WRITE", UID, "5")
        with self.assertRaises(BridgeError) as ctx:
            self.bridge.write_tag(UID, PLA_RED, self.backup_dir)
        error = ctx.exception
        self.assertEqual(error.code, "SERIAL")
        self.assertEqual([(cmd, block) for cmd, block, _ in self.tag.mutations], [("WRITE", 4)])
        self.assertEqual(self.tag.key_a, DEFAULT_KEY)
        self.assertTrue(Path(error.backup).is_file())
        self.assertIn(error.backup, str(error))
        self.assertIn("unvollständig", str(error))
        backup = json.loads(Path(error.backup).read_text(encoding="utf-8"))
        self.assertEqual(backup["blocks"]["4"], "AA" * 16)

    def test_failed_backup_file_creation_stops_before_writes(self):
        self.backup_dir.write_text("a file blocks directory creation", encoding="utf-8")
        with self.assertRaises(BridgeError) as ctx:
            self.bridge.write_tag(UID, PLA_RED, self.backup_dir)
        self.assertEqual(ctx.exception.code, "BACKUP")
        self.assertIsNone(ctx.exception.backup)
        self.assert_no_mutation()

    def test_backup_disk_write_failure_stops_before_mutation(self):
        original_open = Path.open

        def fail_backup(path, mode="r", *args, **kwargs):
            if mode == "x":
                raise OSError("disk full")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", fail_backup):
            with self.assertRaises(BridgeError) as ctx:
                self.bridge.write_tag(UID, PLA_RED, self.backup_dir)
        self.assertEqual(ctx.exception.code, "BACKUP")
        self.assert_no_mutation()

    def test_false_verified_response_stops_and_retains_backup(self):
        def corrupt(request, response):
            if request[0] == "WRITE":
                return {**response, "verified": False}
            return response
        self.serial.response_filter = corrupt
        with self.assertRaises(BridgeError) as ctx:
            self.bridge.write_tag(UID, PLA_RED, self.backup_dir)
        self.assertEqual(ctx.exception.code, "VERIFY_FAILED")
        self.assertTrue(Path(ctx.exception.backup).is_file())
        self.assertEqual([(cmd, block) for cmd, block, _ in self.tag.mutations], [("WRITE", 4)])

    def test_wrong_block_response_is_rejected(self):
        def corrupt(request, response):
            return {**response, "block": 7} if request[0] == "READ" else response
        self.serial.response_filter = corrupt
        with self.assertRaises(BridgeError) as ctx:
            self.bridge.read_tag()
        self.assertEqual(ctx.exception.code, "PROTOCOL")
        self.assert_no_mutation()

    def test_invalid_spec_does_not_send_any_command(self):
        requests_before = len(self.serial.requests)
        with self.assertRaises(ValueError):
            self.bridge.write_tag(UID, replace(PLA_RED, material_id="BAD"), self.backup_dir)
        self.assertEqual(len(self.serial.requests), requests_before)
        self.assert_no_mutation()

    def test_newline_in_protocol_argument_is_rejected_without_serial_write(self):
        requests_before = len(self.serial.requests)
        with self.assertRaises(BridgeError) as ctx:
            self.bridge._command("READ", UID + "\nWRITE", 4, "FFFFFFFFFFFF")
        self.assertEqual(ctx.exception.code, "PROTOCOL")
        self.assertEqual(len(self.serial.requests), requests_before)
        self.assert_no_mutation()


if __name__ == "__main__":
    unittest.main(verbosity=2)
