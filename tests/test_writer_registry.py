# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Headless data-flow checks for the writer's registered-profile UI."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app/creality-cfs-writer"))
import cfs_codec as codec
from cfs_writer import make_application, material_identity


class Variable:
    def __init__(self, value=""):
        self.value, self.callbacks = value, []
    def get(self):
        return self.value
    def set(self, value):
        self.value = value
        for callback in self.callbacks:
            callback("", "", "write")
    def trace_add(self, _kind, callback):
        self.callbacks.append(callback)


class Widget:
    def __init__(self):
        self.options = {}
    def configure(self, **kwargs):
        self.options.update(kwargs)


class Registry:
    def __init__(self, material):
        self.material, self.fail, self.alias, self.calls = deepcopy(material), None, False, 0
    def refresh_material(self, item):
        self.calls += 1
        if not item.get("registry_managed"):
            return item
        if self.fail:
            raise self.fail
        return item if self.alias else deepcopy(self.material)
    @property
    def entries(self):
        return [{"material_id":self.material["id"], "profile_setting_id":self.material["profile_setting_id"], "enabled":True}]


class Device:
    def __init__(self):
        self.writes = []
        self.tag = {"uid":"11223344", "formatted":False}
    def write_tag(self, uid, spec, backup_dir):
        self.writes.append((uid, deepcopy(spec)))
        return {"uid":uid, "verified":True, "backup":"mock-backup.json"}
    def read_tag(self):
        return deepcopy(self.tag)


class WriterRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.material = {
            "id":"99006", "name":"HISPD PETG Sunlu Beispiel Cyan 0.4", "brand":"Sunlu", "type":"PETG",
            "color":"#AEEAFF", "source":"slicer", "source_file":"/test/Beispiel Cyan.json",
            "mapping_status":"registry_assigned", "registry_managed":True,
            "registry_material_id":"99006", "profile_setting_id":"stable-setting-id",
            "registry_registration_status":"installed",
            "profile_metadata":{"nozzle_temperature":"245", "flow_ratio":"0.9375", "pressure_advance":"0.045"},
        }
        self.registry = Registry(self.material)
        App = make_application(None, None, {}, codec, None, None, registry=self.registry)
        self.app = App.__new__(App)
        app = self.app
        app.root, app.registry = None, self.registry
        app.bridge = Device(); app.uid = "11223344"
        app.busy = app.close_pending = app.close_started = False
        app.materials = []; app.material_by_label = {}; app.material_by_id = {}
        app.backup_dir = Path(self.tmp.name)
        for name in ("port_combo", "refresh_button", "connect_button", "read_button", "write_button", "material_combo",
                     "id_entry", "name_entry", "color_entry", "color_button", "color_swatch"):
            setattr(app, name, Widget())
        app.controls = [(app.id_entry,"normal"), (app.name_entry,"normal"), (app.color_entry,"normal"), (app.color_button,"normal")]
        values = {
            "port_var":"DEMO", "material_var":"", "id_var":"00001", "name_var":"", "color_var":"#0088CC",
            "weight_var":"1000", "serial_var":"123456", "summary_var":"", "write_hint_var":"",
            "profile_info_var":"", "mapping_hint_var":"", "status_var":"", "tag_var":"", "tag_hint_var":"",
        }
        for name, value in values.items():
            setattr(app, name, Variable(value))
        self.logs, self.errors = [], []
        app.log = self.logs.append
        app.show_error = self.errors.append
        # Execute the same main-thread completion handlers without creating a
        # Tk window, USB connection, or worker thread.
        def operation(_label, function, on_success):
            try:
                on_success(function())
            except Exception as error:
                app.clear_tag()
                app.show_error(error)
            app.update_controls()
        app.run_operation = operation
        for name in ("id_var", "name_var", "color_var", "weight_var", "serial_var"):
            getattr(app, name).trace_add("write", app.fields_changed)
        app.set_materials([*codec.DEFAULT_MATERIALS, self.material])
        self.select_managed()

    def tearDown(self):
        self.tmp.cleanup()

    def selected(self):
        return self.app.material_by_label.get(self.app.material_var.get())

    def test_shared_roll_selects_target_binding_but_amount_always_comes_from_tag(self):
        from cfs_fleet import FleetStore
        app = self.app
        app.data_dir = Path(self.tmp.name)
        self.registry.printer = {'ip': '10.0.0.1'}
        store = FleetStore(app.data_dir)
        store.set_policy('10.0.0.1', 'rolls')
        store.remember('10.0.0.1', 'cfs', '11223344', '123456', self.material['id'], 500)
        app.bridge.tag = {'uid': '11223344', 'formatted': True,
                          'profile': {'material_id': '99999', 'serial': '123456', 'weight_g': 817, 'color': '#123456'}}
        app.read_tag()
        self.assertFalse(self.errors)
        self.assertEqual(app.id_var.get(), self.material['id'])
        self.assertEqual(app.serial_var.get(), '123456')
        self.assertEqual(app.weight_var.get(), '817')
        self.assertEqual(store.material_for_roll('10.0.0.1', '123456'), self.material['id'])

    def select_managed(self):
        label = next(label for label, item in self.app.material_by_label.items() if item.get("registry_managed"))
        self.app.material_var.set(label)
        self.app.material_selected()

    def test_selection_refreshes_name_color_metadata_and_keeps_identity(self):
        old_object = self.selected()
        old_identity = material_identity(old_object)
        self.registry.material.update(name="Neu benannt", color="#112233", source_file="/test/Neu benannt.json")
        self.registry.material["profile_metadata"]["nozzle_temperature"] = "250"
        self.app.material_selected()
        self.assertIs(self.selected(), old_object)
        self.assertIs(self.app.material_by_id["99006"], old_object)
        self.assertEqual(material_identity(old_object), old_identity)
        self.assertEqual(self.app.name_var.get(), "Neu benannt")
        self.assertEqual(self.app.color_var.get(), "#112233")
        self.assertIn("250", self.app.profile_info_var.get())
        self.assertEqual(self.app.id_entry.options["state"], "readonly")

    def test_pending_blocks_button_and_direct_write(self):
        self.registry.material["registry_registration_status"] = "pending"
        self.app.material_selected()
        self.assertEqual(self.app.write_button.options["state"], "disabled")
        self.assertIn("Druckereinrichtung", self.app.write_hint_var.get())
        self.app.write_tag()
        self.assertEqual(self.app.bridge.writes, [])
        self.assertTrue(self.errors)

    def test_write_uses_fresh_saved_source_and_expected_uid(self):
        self.registry.material.update(name="Frisch gespeichert", color="#445566")
        self.registry.material["profile_metadata"]["flow_ratio"] = "0.97"
        self.app.write_tag()
        uid, spec = self.app.bridge.writes[0]
        self.assertEqual((uid, spec.material_id, spec.name, spec.color), ("11223344", "99006", "Frisch gespeichert", "#445566"))
        self.assertEqual(spec.serial, "123456")
        self.assertEqual(self.app.name_var.get(), "Frisch gespeichert")
        self.assertEqual(self.errors, [])

    def test_fixed_code_cannot_be_used_as_manual_other_id(self):
        self.app.id_var.set("99007")
        self.assertEqual(self.app.write_button.options["state"], "disabled")
        with self.assertRaisesRegex(ValueError,"feste Materialcode"):
            self.app.make_spec()
        self.app.write_tag()
        self.assertEqual(self.app.bridge.writes[0][1].material_id, "99006")

    def test_selection_handles_refresh_returning_same_dictionary(self):
        self.registry.alias = True
        self.app.material_selected()
        self.assertEqual(self.selected()["id"], "99006")
        self.assertTrue(self.selected()["registry_managed"])
        self.assertEqual(self.errors, [])

    def test_write_handles_refresh_returning_same_dictionary(self):
        self.registry.alias = True
        self.app.write_tag()
        self.assertEqual(self.app.bridge.writes[0][1].material_id, "99006")
        self.assertTrue(self.selected()["registry_managed"])
        self.assertEqual(self.errors, [])

    def test_source_io_failure_stops_write_with_actionable_error(self):
        self.registry.fail = OSError("saved source disappeared")
        self.app.write_tag()
        self.assertEqual(self.app.bridge.writes, [])
        self.assertTrue(self.errors)

    def test_tag_lookup_prefers_registered_profile_over_imported_catalog_record(self):
        # An imported printer database may include the same already-managed
        # material code. It must not downgrade its fixed profile assignment.
        catalog_record = {"id":"99006", "name":"AAA catalog", "brand":"AAA", "type":"PETG"}
        self.app.set_materials([*codec.DEFAULT_MATERIALS, catalog_record, self.material])
        self.app.bridge.tag = {
            "uid":"11223344", "formatted":True,
            "profile":{"material_id":"99006", "color":"#AEEAFF", "weight_g":1000, "serial":"123456", "name":""},
        }
        self.app.read_tag()
        self.assertTrue(self.selected().get("registry_managed"))
        self.assertEqual(self.app.id_entry.options["state"], "readonly")
        self.assertEqual(self.app.name_var.get(), self.material["name"])

    def test_unconfirmed_notes_code_is_not_selected_by_read_tag(self):
        declared = {"id":"99007", "name":"Unconfirmed native profile", "source":"slicer", "source_file":"/test/unconfirmed.json", "mapping_status":"declared"}
        self.app.set_materials([*codec.DEFAULT_MATERIALS, self.material, declared])
        self.app.bridge.tag = {
            "uid":"11223344", "formatted":True,
            "profile":{"material_id":"99007", "color":"#AEEAFF", "weight_g":1000, "serial":"123456", "name":""},
        }
        self.app.read_tag()
        self.assertIsNone(self.selected())


if __name__ == "__main__":
    unittest.main(verbosity=2)
