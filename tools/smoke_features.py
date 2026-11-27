# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Offline UI checks with synthetic profiles and simulated USB transports only.

Requires a desktop display (on Linux, use xvfb-run). Optional --screenshots DIR
uses ImageMagick for development captures; normal test runs do not require it.
"""
from copy import deepcopy
import json,os,sys,tempfile,time,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'app/creality-cfs-writer'
sys.path[:0]=[str(APP),str(ROOT/'tests')]
import cfs_codec as codec
from cfs_writer import make_application
from cfs_device import BridgeError
from test_profile_roundtrip import generic_record
from cfs_transfer_core import digest
from cfs_fleet import FleetStore
from cfs_connections import ConnectionStore
record=generic_record();record['base'].update(id='99021',name='Synthetic Hi',brand='Example Hi')
profile={'material_id':'99021','profile_setting_id':'a'*24,'name':'Synthetic Hi','brand':'Example Hi','type':'PETG','color':'#FFFFFF','source_file':'test://profile','record':record,'resolved':record['kvParam']}
snapshot={'schema_version':1,'source':'printer_cloud','account_id':'123','printer_int_name':'F012','nozzle_diameter':'0.4','printer_registration_status':'installed','profiles':{'99021':profile}}
class Registry:
 sync_source='printer_cloud';printer={'name':'Test source','ip':'10.0.0.1','printer_int_name':'F012','nozzle_diameter':'0.4'};profile_status={};entries=[]
 def __init__(self,path):self.path=path
 def materials(self):return deepcopy(codec.DEFAULT_MATERIALS)
 def cloud_catalog(self,**kwargs):return deepcopy(snapshot)
 def printer_choices(self):return [deepcopy(self.printer),{'name':'Test target','ip':'10.0.0.2','printer_int_name':'F012','nozzle_diameter':'0.4'}]
 def _load(self):return {'profiles':[],'printer':deepcopy(self.printer)}
 def _cloud_snapshot(self,data,**kwargs):return deepcopy(snapshot)
class Device:
 fail_read=False;fail_write=False;uid='11223344';profile=None
 def hello(self):return {'protocol':1,'reader_version':0x92,'firmware_version':'1.1.0','capabilities':['cfs_sector1','ntag213']}
 def read_tag(self):
  if self.fail_read:raise BridgeError('NO_TAG','Test: no tag')
  return {'uid':self.uid,'formatted':self.profile is not None,'profile':deepcopy(self.profile)}
 def write_tag(self,uid,spec,backup):
  if self.fail_write:raise BridgeError('WRITE_FAILED','Test: interrupted')
  return {'uid':uid,'verified':True}
 def close(self):pass
errors=[];messages=[]
dialogs={'filedialog':SimpleNamespace(askopenfilenames=lambda **k:(),askopenfilename=lambda **k:'',asksaveasfilename=lambda **k:'',askdirectory=lambda **k:''),
 'messagebox':SimpleNamespace(showerror=lambda *a,**k:messages.append(a),showinfo=lambda *a,**k:None,askyesno=lambda *a,**k:False),
 'colorchooser':SimpleNamespace(askcolor=lambda **k:(None,None))}
with tempfile.TemporaryDirectory() as directory,patch('cfs_desktop.refresh_menu_icon',return_value=False),patch('urllib.request.urlopen',side_effect=AssertionError('UI smoke must not access a real printer')):
 os.environ['CFS_APP_DATA']=directory
 Path(directory,'ui-settings.json').write_text(json.dumps({'first_start_notice_acknowledged':True}))
 registry=Registry(Path(directory,'registry.json'));registry.path.write_text('{}')
 ConnectionStore(directory).remember('Test ACE','10.0.0.3',model='Anycubic Kobra S1',feeder_id='ace_pro',feeder_variant='s1')
 root=tk.Tk();root.report_callback_exception=lambda *args:errors.append(args)
 App=make_application(tk,ttk,dialogs,codec,lambda port:Device(),lambda:[],False,registry)
 App.load_initial_printer=lambda self:{'firmware':None,'firmware_error':'','materials':registry.materials(),'error':None}
 app=App(root);root.geometry('1150x1050+0+0')
 def settle(wait=.1):
  deadline=time.monotonic()+wait
  while time.monotonic()<deadline:root.update();time.sleep(.005)
 def idle():
  deadline=time.monotonic()+8
  while app.busy and time.monotonic()<deadline:settle(.025)
  settle(.08);assert not app.busy
 def shot(name,widget=None):
  if '--screenshots' not in sys.argv:return
  root.update();subprocess.run(['import','-display',os.environ['DISPLAY'],'-window',str((widget or root).winfo_id()),str(Path(sys.argv[sys.argv.index('--screenshots')+1]).resolve()/name)],check=True)
 settle();idle()
 assert app.read_button.master is app.write_button.master
 section=app.tag_actions.master
 assert section.cget('text')=='02   NFC-Tag lesen & schreiben'
 assert app.label_button.master is app.tag_actions
 assert not any(isinstance(widget,ttk.LabelFrame) and str(widget.cget('text')).startswith('04') for widget in section.master.winfo_children())
 app.port_var.set('FAKE');app.toggle_connection();idle()
 device=app.bridge
 device.fail_read=True;app.read_tag();idle();assert app.read_button.cget('text')=='Erneut lesen'
 device.fail_read=False;app.read_tag();idle();assert app.uid=='11223344'
 device.fail_write=True;app.write_tag();idle();assert app.write_button.cget('text')=='Erneut schreiben';assert app.uid=='11223344'
 device.fail_write=False;app.write_tag();idle();assert app.tag_feedback.phase=='success'
 app.weight_var.set('817');settle();assert app.tag_feedback.phase=='idle'
 for mode in ['light','dark']:
  app.theme_var.set(mode);app.apply_theme(False);settle()
  for title,menu in [('Verbindung',app.printer_menu),('Profile',app.profiles_menu),('Hilfe',app.help_menu),('Einstellungen',app.settings_menu)]:
   app.navigation['toggle'](title,menu);settle();assert app.navigation['panel'].winfo_ismapped();app.navigation['close']()
  # Direct navigation and app-styled history use the same appearance.
  home=next(button for title,button in app.navigation['buttons'] if title=='Lesen & Schreiben')
  home.invoke();settle();assert app.main_canvas.winfo_ismapped()
  assert str(app.log_widget.cget('font'))=='TkDefaultFont'
  for title,button in app.navigation['buttons']:
   assert button.winfo_rootx()+button.winfo_width()<=root.winfo_rootx()+root.winfo_width()
  # Both status slots persist across reading, failed writes and verified retry.
  if app.two_tags_var.get():app.pair_check.invoke()
  app.pair_check.invoke()
  petg=next(item for item in codec.DEFAULT_MATERIALS if 'PETG' in item['name'].upper())
  device.uid='11223344';device.profile={'material_id':petg['id'],'serial':'123456','color':'#112233','weight_g':825}
  app.read_tag();idle();assert app.serial_var.get()=='123456'
  app.write_tag();idle();assert app.pair_session.status_rows()[0]['written']
  first=app.pair_status_vars[0].get()
  device.uid='AABBCCDD';device.profile={'material_id':'00001','serial':'654321','color':'#FFFFFF','weight_g':500}
  app.read_tag();idle();assert app.serial_var.get()=='123456' and app.weight_var.get()=='825'
  assert app.pair_status_vars[0].get()==first
  assert app.pair_session.status_rows()[1]['read'] and not app.pair_session.status_rows()[1]['written']
  device.fail_write=True;app.write_tag();idle();assert app.pair_status_vars[0].get()==first
  assert app.pair_session.status_rows()[1]['error'] and not app.pair_session.status_rows()[1]['written']
  device.fail_write=False;app.write_tag();idle()
  assert all(row['written'] and row['read'] and not row['error'] for row in app.pair_session.status_rows())
  for text in ('PETG','#112233','825 g','123456'):assert text in app.tag_result_var.get(),app.tag_result_var.get()
  shot('two-tags-'+mode+'.png')
  app.main_canvas.yview_moveto(1);settle();shot('history-'+mode+'.png');app.main_canvas.yview_moveto(0)
  app.pair_check.invoke();device.uid='11223344';device.profile=None
  shot('main-'+mode+'.png')
  app.choose_printer();settle();chooser=app.printer_dialog_fields
  label=next(str(value) for value in app.printer_dialog.winfo_children()[0].winfo_children() if isinstance(value,ttk.Combobox))
  combo=root.nametowidget(label)
  chosen=next(str(value) for value in combo.cget('values') if 'Anycubic' in str(value))
  chooser['selection'].set(chosen);combo.event_generate('<<ComboboxSelected>>');settle()
  chooser['test'].invoke();settle();assert 'Kein Netzwerktest' in chooser['result'].get()
  chooser['save'].invoke();settle();assert app.target_form.ace
  assert registry.printer['ip']=='10.0.0.1';assert app.main_canvas.winfo_ismapped()
  app.target_form.select(None);settle()
  app.show_fleet();settle();fields=app.fleet_fields
  target=next(label for label,item in fields['state']['targets'].items() if item['ip']=='10.0.0.2')
  fields['selector'].set(target);fields['selector'].event_generate('<<ComboboxSelected>>');settle()
  fields['mode'].set('Rollennummern + Profile gleicher Druckertypen');fields['save']()
  fields['load']();idle();fields['table'].selection_set('99021');settle()
  def transfer(target,bundle,password,preview):
   return {'plan':[{'source_code':'99021','material_id':'99021','retag_required':False,'action':'imported'}],
   'printer':target.printer,'bundle_sha256':digest(bundle),'plan_token':'a'*64}
  with patch('cfs_profile_transfer.transfer',side_effect=transfer):
   fields['preview']();idle();assert fields['state']['preview'] is not None,fields['message'].get()
   fields['apply']();idle();assert 'übernommen' in fields['message'].get(),fields['message'].get()
  shot('fleet-'+mode+'.png');app.close_main_page();settle()
  from test_multi_printer_v350 import ExperimentalAce
  nt=ExperimentalAce().fake_bridge();app.bridge=nt
  app.show_anycubic(printer=ConnectionStore(directory).choices()[0]);settle();a=app.target_form
  assert a.ace and a.target_config()['variant']=='s1'
  assert app.main_canvas.winfo_ismapped()
  if not app.two_tags_var.get():app.pair_check.invoke()
  app.read_tag();idle();assert app.uid==nt.uid
  app.id_var.set('EXAMPLE-01');app.weight_var.set('817');app.write_tag();idle()
  assert len(app.pair_session.written)==1,app.status_var.get()
  ace_first=app.pair_status_vars[0].get()
  nt.uid='04776655443322';nt.memory[124:128]=(300).to_bytes(4,'little')
  app.read_tag();idle();assert app.weight_var.get()=='817'
  assert app.pair_status_vars[0].get()==ace_first and not app.pair_session.status_rows()[1]['written']
  app.write_tag();idle();assert len(app.pair_session.written)==2,app.status_var.get()
  assert all(row['written'] and row['read'] for row in app.pair_session.status_rows())
  assert '817 g' in app.tag_result_var.get() and 'lokal' in app.tag_result_var.get()
  app.main_canvas.yview_moveto(1);settle();shot('anycubic-'+mode+'.png');app.main_canvas.yview_moveto(0)
  assert 'Experimentell' in a.notice.get()
  # A printer change clears both the target UID and the two-tag payload.
  other=dict(a.printer,feeder_id='ace2_pro',feeder_variant='s1_x')
  a.select(other);settle();assert app.uid is None and not app.pair_session.written
  assert a.target_config()['variant']=='s1_x'
  app.read_tag();idle();app.id_var.set('EXAMPLE-01');app.write_tag();idle();assert app.tag_feedback.phase=='success',app.status_var.get()
  app.reset_two_tags();app.read_tag();idle()
  # Import current Slicer values into the same form without losing tag identity or quantity.
  sample=Path(directory)/'ace-profile.json'
  sample.write_text(json.dumps({'from':'User','name':'Synthetic ACE Ob','filament_vendor':['Example Ob'],
   'filament_type':['PETG'],'compatible_printers':['Anycubic Kobra S1 0.4 nozzle'],
   'default_filament_colour':['#224466'],'nozzle_temperature_range_low':['235'],'nozzle_temperature_range_high':['255'],
   'hot_plate_temp':['75'],'filament_flow_ratio':['0.95'],'pressure_advance':['0.04']}))
  old_sku=app.id_var.get();old_amount=app.weight_var.get()
  picker=dialogs['filedialog'].askopenfilenames
  dialogs['filedialog'].askopenfilenames=lambda **k:[str(sample)]
  app.import_materials();idle();dialogs['filedialog'].askopenfilenames=picker
  assert app.id_var.get()==old_sku and app.weight_var.get()==old_amount
  assert a.variables['type'].get()=='PETG' and a.variables['bed_high'].get()=='75'
  assert app.material_by_label[app.material_var.get()]['printer_manufacturer']=='Anycubic'
  app.label_for_selected();settle();assert app.main_page_fields['title'].startswith('Filament-Etiketten');app.close_main_page();settle()
  # A write failure keeps the UID and offers the same retry action as CFS.
  with patch('cfs_anycubic.AceDevice.write_tag',side_effect=BridgeError('WRITE_FAILED','Simulated interrupted ACE write')):
   app.write_tag();idle();assert app.uid==nt.uid;assert app.write_button.cget('text')=='Erneut schreiben'
  app.write_tag();idle();assert app.tag_feedback.phase=='success'
  app.show_setup();settle();assert app.setup_fields['target_model']()=='Anycubic Kobra S1';assert str(app.setup_fields['buttons']['install'].cget('state'))=='disabled';app.setup_fields['window'].destroy();settle()
  app.show_ssh_help();settle();assert 'keinen SSH-Installer' in app.ssh_help_fields['text'].get('1.0','end');app.ssh_help_fields['close']()
  integrated=dict(a.printer,model='Anycubic Kobra X',feeder_id='kobra_x_integrated',feeder_variant='integrated')
  a.select(integrated);app.read_tag();idle();assert str(app.write_button.cget('state'))=='disabled'
  a.printer['test_unknown_format']=True;settle();app.update_controls();assert str(app.write_button.cget('state'))=='normal'
  app.write_tag();idle();assert app.tag_feedback.phase=='success'
  shot('anycubic-integrated-'+mode+'.png')
  a.select(None);app.bridge=device;settle()
  root.geometry('1050x700');settle();shot('main-small-'+mode+'.png');root.geometry('1150x1050');settle()
  app.show_compatibility();settle();assert len(app.compatibility_fields['table'].get_children())>=18;assert len(app.compatibility_fields['feeder_table'].get_children())==8;app.compatibility_fields['notebook'].select(1);settle();shot('feeder-catalog-'+mode+'.png');app.close_main_page();settle()
  # The Slicer page compares on open and again on request, with explicit direction.
  app.import_directory=Path(directory)
  plan=[dict(identity=key,name='Synthetic '+key,material_id='9902'+str(i),action=action)
        for i,(key,action) in enumerate((('new','copy_created'),('updated','copy_updated'),('unchanged','copy_unchanged')))]
  prepared={'preview':{'plan':plan},'details':{row['identity']:{'filename':'synthetic.json','changes':{}} for row in plan}}
  with patch('cfs_slicer_sync.prepare',return_value=prepared) as prepare,patch('cfs_slicer_sync.apply',return_value={'materials':[]}) as apply:
   app.show_slicer_sync();settle();idle();sync=app.slicer_sync_fields
   assert prepare.call_count==1 and sync['state']['counts']=={'new':1,'updated':1,'unchanged':1}
   assert 'Slicer → Drucker' in sync['apply'].cget('text')
   sync['check'].invoke();idle();assert prepare.call_count==2
   sync['apply'].invoke();idle();assert apply.call_count==1 and prepare.call_count==3
   shot('slicer-sync-'+mode+'.png');app.close_main_page();settle()
  app.show_setup();settle();assert app.setup_fields['model_status'].get();app.setup_fields['window'].destroy();settle()
  app.show_hardware_guide();settle(.2);assert app.hardware_guide_fields['viewers'][0]['state']['photo'];app.hardware_guide_fields['choice'].set('Arduino Nano Classic ATmega328P (5 V)');app.hardware_guide_fields['selector'].event_generate('<<ComboboxSelected>>');settle(.2);assert app.hardware_guide_fields['viewers'][0]['state']['photo'];shot('guide-'+mode+'.png',app.hardware_guide_fields['window']);app.hardware_guide_fields['window'].destroy();settle()
  # Both download entry points work offline, preserve cancellation and ask for a target.
  from cfs_samples import sample_bytes
  save_picker=dialogs['filedialog'].asksaveasfilename
  reader=app.bridge;app.bridge=None
  app.show_label_home();settle()
  download=app.label_home_fields['buttons'][-1]
  assert 'Beispielplatte' in download.cget('text')
  before=app.status_var.get();download.invoke();settle();assert app.status_var.get()==before
  destination=Path(directory)/('Beispielplatte '+mode+'.3mf')
  dialogs['filedialog'].asksaveasfilename=lambda **kwargs:str(destination)
  download.invoke();settle();assert destination.read_bytes()==sample_bytes()
  assert 'Beispielplatte gespeichert' in app.status_var.get()
  shot('sample-download-'+mode+'.png')
  root.geometry('1050x700');settle();canvas=app.label_home_fields['body'].master
  assert isinstance(canvas,tk.Canvas);canvas.yview_moveto(1);settle()
  assert download.winfo_rooty()+download.winfo_height()<=root.winfo_rooty()+root.winfo_height()
  shot('sample-download-small-'+mode+'.png');app.close_main_page();root.geometry('1150x1050');settle()
  destination.unlink()
  index=next(i for i in range(app.help_menu.index('end')+1) if app.help_menu.type(i)=='command' and 'Beispielplatte' in app.help_menu.entrycget(i,'label'))
  app.help_menu.invoke(index);settle();assert destination.read_bytes()==sample_bytes()
  dialogs['filedialog'].asksaveasfilename=save_picker
  app.bridge=reader
  # App update page uses background operations and preserves the selected tag.
  from cfs_versions import APP_VERSION
  # New printer setup uses one brand/model form without network or keyring work.
  app.add_printer_button.invoke();settle();adder=app.add_printer_fields
  adder['values']['manufacturer'].set('Anycubic');adder['fields']['manufacturer'].event_generate('<<ComboboxSelected>>');settle()
  assert 'Kobra S1' in adder['fields']['model'].cget('values')
  adder['values']['model'].set('Kobra S1');adder['fields']['model'].event_generate('<<ComboboxSelected>>');settle()
  assert adder['fields']['feeder'].winfo_ismapped()
  adder['values']['manufacturer'].set('Creality');adder['fields']['manufacturer'].event_generate('<<ComboboxSelected>>');settle()
  assert not adder['fields']['feeder'].winfo_ismapped()
  adder['values']['model'].set('Hi');adder['fields']['model'].event_generate('<<ComboboxSelected>>');settle()
  adder['values']['name'].set('Synthetic Hi');adder['values']['ip'].set('10.0.0.77' if mode=='light' else '10.0.0.78')
  shot('add-printer-'+mode+'.png',adder['window']);adder['save'].invoke();settle()
  assert 'Hi' in app.printer_model_filter.cget('values')
  app.printer_brand_filter_var.set('Anycubic');settle();assert 'Hi' not in app.printer_model_filter.cget('values')
  app.clear_material_filters();settle()
  selected_uid=app.uid;selected_amount=app.weight_var.get()
  app.show_app_updates();settle();fields=app.update_page_fields
  assert fields['history'] is not None
  assert not any(isinstance(widget,ttk.Button) and widget.cget('text')=='Was ist neu?' for widget in fields['search'].master.winfo_children())
  assert '**' not in fields['notes'].get('1.0','end')
  with patch('cfs_update_ui.check_release',side_effect=ValueError('Simulated offline')):
   fields['search'].invoke();idle();assert 'Simulated offline' in fields['status'].get()
  offered={'available':True,'version':'99.0.0','size':1024,'notes':'Synthetic release notes'}
  with patch('cfs_update_ui.check_release',return_value=offered):
   fields['search'].invoke();idle();assert '99.0.0 verfügbar' in fields['status'].get()
  older=next(value for value in fields['history'].cget('values') if value=='3.7.0')
  fields['history_selection'].set(older);fields['history'].event_generate('<<ComboboxSelected>>');settle()
  assert '3.7.0' in fields['notes'].get('1.0','end')
  assert fields['state']['release']['version']=='99.0.0'
  with patch('cfs_update_ui.stage_release',side_effect=ValueError('Simulated checksum error')):
   fields['install'].invoke();idle();assert 'erneut' in fields['install'].cget('text')
  with patch('cfs_update_ui.stage_release',return_value={'version':'99.0.0'}):
   fields['install'].invoke();idle();assert 'neu starten' in fields['install'].cget('text')
  assert app.uid==selected_uid and app.weight_var.get()==selected_amount
  shot('app-updates-'+mode+'.png');app.close_main_page();settle()
  notes_window=app.show_release_notes();settle();assert 'Was ist neu?' in notes_window.title()
  notes_fields=app.release_notes_fields
  assert notes_fields['selector'] is not None
  from cfs_update_ui import show_notes
  notes_window.destroy();notes_window=show_notes(app,tk,ttk,automatic=True);settle()
  for size in ('800x600','560x400'):
   notes_window.geometry(size);settle()
   button=app.release_notes_fields['close']
   assert button.winfo_height()>=40
   assert button.winfo_rooty()+button.winfo_height()<=notes_window.winfo_rooty()+notes_window.winfo_height()-10
   assert '**' not in app.release_notes_fields['text'].get('1.0','end')
  shot('patchnotes-small-'+mode+'.png',notes_window)
  button.invoke();settle()
  assert json.loads((Path(directory)/'app-update-seen.json').read_text())['version']==APP_VERSION
  from cfs_labels import document
  from cfs_label_ui import show
  docs=[document(profile,registry.printer)]
  show(app,tk,ttk,dialogs,docs);settle(.3);shot('labels-'+mode+'.png');app.close_main_page();settle()
 ConnectionStore(directory).remember('Test ACE','10.0.0.3',model='Anycubic Kobra S1',feeder_id='ace2_pro',feeder_variant='s1_x')
 app.show_anycubic(printer=next(item for item in ConnectionStore(directory).choices() if item['ip']=='10.0.0.3'));settle()
 assert app.target_form.target_config()['feeder_id']=='ace2_pro'
 assert app.target_form.target_config()['variant']=='s1_x'
 assert app.main_canvas.winfo_ismapped()
 app.target_form.select(None);app.bridge=None;root.destroy()
 assert not errors,errors
 print('Feature UI smoke passed: retry/read/write states, all navigation groups, fleet preview/commit, ACE, compatibility, setup, hardware guide and labels, in both themes. Expected test-error dialogs:',len(messages))
