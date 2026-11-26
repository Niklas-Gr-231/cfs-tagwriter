# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from copy import deepcopy
import io,json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app/creality-cfs-writer'))
from cfs_nozzles import split_manufacturer,matches,nozzle_text
from cfs_labels import document,render_png,label_values,write_png,safe_filename,documents_from_bundle


def example(brand='Sunlu Hi'):
    return document({'material_id':'99006','profile_setting_id':'a'*24,'name':'HISPD PETG Sunlu Beispiel Cyan 0.4 Hi','brand':brand,'type':'PETG','color':'#AEEAFF','origin':'cloud','resolved':{'name':'HISPD PETG Sunlu Beispiel Cyan 0.4 Hi','filament_flow_ratio':['0.9375'],'pressure_advance':['0.045'],'enable_pressure_advance':['1'],'filament_max_volumetric_speed':['19.5'],'filament_cost':['18.5'],'nozzle_temperature':['245'],'nozzle_temperature_initial_layer':['245'],'textured_plate_temp':['70'],'textured_plate_temp_initial_layer':['75'],'hot_plate_temp':['60']}},{'printer_int_name':'F012','nozzle_diameter':'0.4'},'fixture')

class NozzleConvention(unittest.TestCase):
    def test_only_separate_manufacturer_suffix_is_a_nozzle(self):
        for raw,wanted in (('Sunlu Hi',('Sunlu','Hi')),('Sunlu Ob',('Sunlu','Ob')),('Soleyin Hi',('Soleyin','Hi')),('Sunlu',('Sunlu','')),('Tob',('Tob','')),('Company Hi-Fi',('Company Hi-Fi',''))):self.assertEqual(split_manufacturer(raw),wanted)
    def test_combined_filters_are_case_insensitive_and_distinct(self):
        material={'name':'Sky blue','brand':'Sunlu Hi','type':'PETG','id':'99006'}
        self.assertTrue(matches(material,'blue','Sunlu','High Unicorn (Hi)'))
        self.assertFalse(matches(material,'blue','Sunlu','Obsidian (Ob)'))
        self.assertEqual(nozzle_text({'brand':'Sunlu'}),'nicht erfasst')
    def test_selected_hardware_never_implies_unknown_profile_nozzle(self):
        doc=example('Sunlu');self.assertEqual(label_values(doc)['nozzle_type'],'nicht erfasst')
        self.assertEqual(label_values(example('Sunlu Ob'))['nozzle_type'],'Obsidian')

class Labels(unittest.TestCase):
    def test_profile_values_are_exact_and_bed_uses_selected_plate(self):
        doc=example();before=deepcopy(doc);values=label_values(doc,{'plate':'Texturierte PEI-Platte'})
        self.assertEqual(values['flow'],'0,9375');self.assertEqual(values['pressure_advance'],'0,045')
        self.assertEqual(values['volumetric_speed'],'19,5 mm³/s');self.assertEqual(values['bed_temperature'],'75→70 °C')
        self.assertEqual(values['price'],'18,5 €/kg');self.assertEqual(values['nozzle_type'],'High Unicorn')
        self.assertEqual(label_values(doc,{'plate':'Glatte / High-Temp-Platte'})['bed_temperature'],'60 °C');self.assertEqual(doc,before)
    def test_correct_smooth_plate_default_and_no_invented_fallback(self):
        doc=example();doc['params'].update(hot_plate_temp='70',hot_plate_temp_initial_layer='70',textured_plate_temp='0',textured_plate_temp_initial_layer='0')
        self.assertEqual(label_values(doc)['bed_temperature'],'70 °C')
        self.assertEqual(label_values(doc)['bed_temperature_key'],'hot_plate_temp')
        self.assertEqual(label_values(doc,{'plate':'Texturierte PEI-Platte'})['bed_temperature'],'n. a.')
        self.assertTrue(label_values(doc,{'plate':'Texturierte PEI-Platte'})['plate_unsupported'])
        doc['params'].pop('hot_plate_temp');doc['params'].pop('hot_plate_temp_initial_layer')
        self.assertEqual(label_values(doc)['bed_temperature'],'n. a.')
    def test_hispd_description_does_not_change_material_or_profile(self):
        doc=example();before=deepcopy(doc)
        self.assertEqual(label_values(doc)['display_type'],'PETG High Speed Matte')
        self.assertEqual(label_values(doc)['type'],'PETG');self.assertEqual(doc,before)
        for dpi in (203,300,600):
            raw,values,boxes=render_png(doc,{'dpi':dpi});self.assertTrue(raw);self.assertEqual(values['display_type'],'PETG High Speed Matte')
        for brand,kind,name in (('Other','PETG','HISPD PETG'),('Sunlu','PLA','HISPD PLA'),('Sunlu','PETG','PETG Beispiel Gelb'),('Sunlu','PETG','NOHISPD')):
            changed=deepcopy(doc);changed.update(brand=brand,type=kind,name=name)
            self.assertEqual(label_values(changed)['display_type'],kind)
    def test_disabled_pa_and_zero_price_are_not_lost(self):
        doc=example();doc['params'].update(enable_pressure_advance='0',filament_cost='0')
        self.assertEqual(label_values(doc)['pressure_advance'],'0,045 (aus)');self.assertEqual(label_values(doc)['price'],'0 €/kg')
        doc['params']['enable_pressure_advance']=False;self.assertIn('aus',label_values(doc)['pressure_advance'])
    def test_missing_fields_are_explicit_not_invented(self):
        doc=example();doc['params']={};values=label_values(doc)
        self.assertEqual([values[k] for k in ('flow','volumetric_speed','price','pressure_advance')],['n. a.']*4)
    def test_optional_fields_do_not_change_numeric_profile_values(self):
        doc=example();raw,values,boxes=render_png(doc,{'show_pa':False,'show_price':False})
        self.assertFalse(values['show_pa']);self.assertFalse(values['show_price']);self.assertEqual(values['flow'],'0,9375')
    def test_all_dpi_sizes_metadata_and_text_stay_inside_label(self):
        from PIL import Image
        for dpi in (203,300,600):
            raw,values,boxes=render_png(example(),{'dpi':dpi});image=Image.open(io.BytesIO(raw))
            self.assertEqual(image.size,(round(40*dpi/25.4),round(30*dpi/25.4)))
            self.assertAlmostEqual(image.info['dpi'][0],dpi,delta=.03)
            metadata=json.loads(image.info['CFS Label']);self.assertEqual(metadata['flow'],'0,9375');self.assertEqual(metadata['nozzle_code'],'Hi')
            self.assertTrue(all(0<=x1<x2<=image.width and 0<=y1<y2<=image.height for x1,y1,x2,y2 in boxes))
    def test_very_precise_values_are_never_rounded_to_fit(self):
        doc=example();doc['params']['filament_flow_ratio']='0.123456789012345678901234567890'
        with self.assertRaisesRegex(ValueError,'passt'):render_png(doc)
    def test_image_export_is_explicit_and_does_not_overwrite_batch_files(self):
        raw,_,_=render_png(example())
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'label.png';write_png(target,raw)
            with self.assertRaises(FileExistsError):write_png(target,raw)
            self.assertEqual(target.read_bytes(),raw);self.assertFalse(list(Path(folder).glob('.cfs-label-*')))
    def test_filenames_do_not_escape_destination(self):
        doc=example();doc['name']='../../Bad:name?*';name=safe_filename(doc)
        self.assertNotIn('/',name);self.assertNotIn(':',name);self.assertTrue(name.endswith('-Hi.png'))
    def test_label_name_override_changes_no_profile_values(self):
        doc=example();before=deepcopy(doc);_,values,_=render_png(doc,{'display_name':'Beispielcyan Hi'})
        self.assertEqual(values['name'],'Beispielcyan Hi');self.assertEqual(doc,before)
    def test_different_material_and_nozzle_identity_produce_distinct_labels(self):
        hi=example();ob=example('Sunlu Ob')
        self.assertNotEqual(render_png(hi)[0],render_png(ob)[0])
    def test_wrong_plate_and_invalid_dpi_fail_before_writing(self):
        for option in ({'dpi':0},{'plate':'guess'}):
            with self.assertRaises(ValueError):render_png(example(),option)
