# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import errno
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch,MagicMock
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/creality-cfs-writer'))
from cfs_connection_errors import auth_issue,network_issue,ssh_issue,ssh_cli_issue
from cfs_printer_identity import probe_printer,printer_identity
from cfs_profile_sync import PrinterSSH,SyncError
from cfs_theme import PALETTES,contrast,apply

class Response:
    def __init__(self,data):self.raw=data if isinstance(data,bytes) else json.dumps(data).encode()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,_size):return self.raw

class Diagnostics(unittest.TestCase):
    def test_bad_password_is_actionable_and_never_echoes_input(self):
        import paramiko
        error=ssh_issue(paramiko.AuthenticationException('hidden-private-password'),'10.0.0.1',True)
        self.assertEqual(error.code,'SSH_AUTH_FAILED')
        self.assertIn('Passwort nicht akzeptiert',str(error))
        self.assertNotIn('hidden-private-password',str(error))
    def test_missing_password_is_not_claimed_to_be_wrong(self):
        self.assertIn('eingeben',str(auth_issue(False)))
    def test_connection_timeout_is_distinct(self):
        self.assertEqual(network_issue(TimeoutError(),'10.0.0.1').code,'NETWORK_TIMEOUT')
    def test_closed_ssh_port_requests_root_access(self):
        error=network_issue(ConnectionRefusedError(errno.ECONNREFUSED,''),ssh=True)
        self.assertEqual(error.code,'SSH_DISABLED');self.assertIn('Port 22',str(error))
    def test_host_key_mismatch_is_distinct_from_authentication(self):
        import paramiko
        key=paramiko.RSAKey.generate(1024)
        error=ssh_issue(paramiko.BadHostKeyException('test',key,key))
        self.assertEqual(error.code,'HOST_KEY_CHANGED')
    def test_openssh_password_failure_is_translated(self):
        self.assertEqual(ssh_cli_issue(5,'private-password').code,'SSH_AUTH_FAILED')
        self.assertEqual(ssh_cli_issue(255,'Permission denied').code,'SSH_AUTH_FAILED')
    def test_a_router_html_page_is_not_accepted_as_printer(self):
        with patch('urllib.request.urlopen',return_value=Response(b'<html>Router</html>')):
            with self.assertRaises(ValueError) as caught:probe_printer('10.0.0.1')
        self.assertEqual(caught.exception.code,'NOT_PRINTER')
    def test_dns_name_alone_does_not_make_a_computer_a_printer(self):
        with patch('urllib.request.urlopen',side_effect=ConnectionRefusedError(errno.ECONNREFUSED,'')),patch('socket.gethostbyaddr',return_value=('computer',[],[])):
            with self.assertRaises(ValueError):printer_identity('10.0.0.1')
    def test_json_from_another_service_is_rejected(self):
        with patch('urllib.request.urlopen',return_value=Response({'result':{'name':'router'}})):
            with self.assertRaises(ValueError) as caught:probe_printer('10.0.0.1')
        self.assertEqual(caught.exception.code,'NOT_PRINTER')
    def test_real_printer_states_are_recognized(self):
        for state in ('ready','startup','shutdown','error'):
            with patch('urllib.request.urlopen',return_value=Response({'result':{'state':state,'hostname':'K2Pro'}})):
                self.assertEqual(probe_printer('10.0.0.1')['hostname'],'K2Pro')
    def test_invalid_ip_is_not_queried(self):
        with patch('urllib.request.urlopen') as call:
            with self.assertRaises(ValueError):probe_printer('http://router')
        call.assert_not_called()
    def test_api_access_failure_is_not_an_ssh_password_error(self):
        err=urllib.error.HTTPError('http://test',403,'denied',{},None)
        self.assertEqual(network_issue(err).code,'PRINTER_API_AUTH')
    def test_paramiko_error_flows_through_real_client_wrapper(self):
        import paramiko,tempfile
        with tempfile.TemporaryDirectory() as folder:
            known=Path(folder)/'known';known.write_text('')
            client=MagicMock();client.connect.side_effect=paramiko.AuthenticationException('not-for-the-ui')
            with patch('paramiko.SSHClient',return_value=client):
                with self.assertRaises(SyncError) as caught:PrinterSSH('10.0.0.1',known,'private-value').run('true')
            self.assertEqual(caught.exception.code,'SSH_AUTH_FAILED')
            self.assertNotIn('private-value',str(caught.exception))
            client.close.assert_called_once()

class VisualTokens(unittest.TestCase):
    def test_text_contrast_for_normal_hover_selected_and_messages(self):
        for name,c in PALETTES.items():
            for fg,bg in ((c['fg'],c['surface']),(c['fg'],c['bg']),(c['fg'],c['field']),(c['fg'],c['hover']),(c['muted'],c['bg']),('#FFFFFF',c['selection']),(c.get('accent_fg','#FFFFFF'),c['accent_hover']),(c['notice_fg'],c['notice']),(c['error_fg'],c['error_bg'])):
                self.assertGreaterEqual(contrast(fg,bg),4.5,(name,fg,bg,contrast(fg,bg)))
    def test_interactive_outlines_are_visible(self):
        for name,c in PALETTES.items():
            for bg in ('surface','field','bg'):
                self.assertGreaterEqual(contrast(c['control_border'],c[bg]),3,(name,bg))
    def test_checkbox_hover_has_explicit_readable_colors(self):
        class Style:
            def __init__(self):self.maps={};self.configs={}
            def theme_use(self):return 'clam'
            def configure(self,name,**values):self.configs[name]=values
            def map(self,name,**values):self.maps.setdefault(name,{}).update(values)
        import tkinter as tk
        from tkinter import ttk
        root=MagicMock();root.winfo_children.return_value=[]
        for dark in (False,True):
            style=Style()
            with patch('tkinter.ttk.Style',return_value=style),patch('tkinter.font.families',return_value=['DejaVu Sans']),patch('tkinter.font.nametofont'):
                c=apply(root,tk,ttk,dark)
            for name in ('TCheckbutton','Card.TCheckbutton','TRadiobutton','Card.TRadiobutton'):
                bg=dict(style.maps[name]['background'])['active']
                fg=dict(style.maps[name]['foreground'])['active']
                self.assertGreaterEqual(contrast(fg,bg),4.5)
                if dark:self.assertNotEqual(bg,'#FFFFFF')

class DesktopIntegration(unittest.TestCase):
    def test_only_our_launcher_is_changed_and_other_fields_stay(self):
        from cfs_desktop import refresh_menu_icon
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            assets=Path(folder)/'assets';assets.mkdir()
            (assets/'cfs-tagwriter.png').write_bytes(b'icon')
            desktop=Path(folder)/'cfs-tagwriter.desktop'
            before='[Desktop Entry]\nName=CFS Tagwriter\nExec="'+str(assets/'Start-Tagwriter.sh')+'"\nIcon=old.svg\nTerminal=false\n'
            desktop.write_text(before)
            with patch('sys.platform','linux'):
                self.assertTrue(refresh_menu_icon(assets,desktop))
                self.assertFalse(refresh_menu_icon(assets,desktop))
            after=desktop.read_text()
            from cfs_versions import APP_VERSION
            self.assertIn('Icon='+str(assets/('cfs-tagwriter-'+APP_VERSION+'.png')),after)
            self.assertIn('Terminal=false',after)
            self.assertIn('Exec="'+str(assets/'Start-Tagwriter.sh')+'"',after)
    def test_unrelated_menu_entry_is_left_unchanged(self):
        from cfs_desktop import refresh_menu_icon
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            assets=Path(folder)/'assets';assets.mkdir();(assets/'cfs-tagwriter.png').write_bytes(b'icon')
            desktop=Path(folder)/'other.desktop';desktop.write_text('Name=Other app\nExec=/somewhere/else\nIcon=old.svg\n')
            before=desktop.read_bytes()
            with patch('sys.platform','linux'):self.assertFalse(refresh_menu_icon(assets,desktop))
            self.assertEqual(desktop.read_bytes(),before)
