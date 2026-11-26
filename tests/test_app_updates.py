# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""No real downloads/processes: integrity, platform isolation, and rollback."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import cfs_updates as updates
from cfs_versions import APP_VERSION


def release(version='99.0.0',key='linux-x86_64',raw=b'fake executable'):
    name=updates.asset_name(version,key)
    return {'available':True,'version':version,'key':key,'name':name,'size':len(raw),
            'sha256':hashlib.sha256(raw).hexdigest(),'url':'https://github.com/'+updates.REPOSITORY+'/releases/download/v'+version+'/'+name,'notes':'Neue Funktionen'}


def api(release):
    return {'tag_name':'v'+release['version'],'draft':False,'prerelease':False,'body':release['notes'],
            'assets':[{'name':release['name'],'size':release['size'],'digest':'sha256:'+release['sha256'],'browser_download_url':release['url']}]}


class Updates(unittest.TestCase):
    def test_platform_selection_and_unsupported_architecture(self):
        for os_name,machine,key in [('win32','AMD64','windows-x86_64'),('darwin','arm64','macos-arm64'),('darwin','x86_64','macos-x86_64'),('linux','x86_64','linux-x86_64')]:
            self.assertEqual(updates.platform_key(os_name,machine),key)
        for os_name,machine in [('linux','aarch64'),('win32','arm64'),('linux','i386')]:
            with self.assertRaises(ValueError):updates.platform_key(os_name,machine)

    def check(self,payload,current=APP_VERSION):
        with patch.object(updates,'_open',return_value=io.BytesIO(json.dumps(payload).encode())):
            return updates.check_release(current,'linux-x86_64')

    def test_official_stable_release_selected_with_exact_checksum(self):
        expected=release()
        self.assertEqual(self.check(api(expected)),expected)

    def test_same_older_and_multidigit_versions(self):
        self.assertFalse(self.check({'tag_name':'v'+APP_VERSION})['available'])
        self.assertFalse(self.check({'tag_name':'v1.0.0'})['available'])
        self.assertTrue(self.check(api(release('3.10.0')),'3.9.0')['available'])

    def test_rejects_unreleased_tags_missing_checksums_and_foreign_urls(self):
        for mutate in [lambda r:r.update(prerelease=True),lambda r:r.update(draft=True),lambda r:r.update(tag_name='v99.0.0-beta'),
                       lambda r:r['assets'][0].update(digest=None),lambda r:r['assets'][0].update(browser_download_url='https://example.com/app'),
                       lambda r:r.update(assets=[]),lambda r:r['assets'][0].update(size=-1)]:
            with self.subTest(mutation=mutate):
                payload=api(release());mutate(payload)
                with self.assertRaises(ValueError):self.check(payload)

    def test_redirects_and_downloads_never_allow_non_github_or_http(self):
        for url in ('http://github.com/file','https://github.com.evil.invalid/file','file:///tmp/app','https://example.com/app'):
            with self.assertRaises(ValueError):updates._safe_url(url)

    def stage(self,directory,raw=b'fake executable',descriptor=None,returncode=0,probe_version='99.0.0'):
        descriptor=descriptor or release(raw=raw)
        with patch.object(updates,'platform_key',return_value='linux-x86_64'),patch.object(updates,'_open',return_value=io.BytesIO(raw)),patch.object(updates.subprocess,'run',return_value=subprocess.CompletedProcess([],returncode,json.dumps({'app':probe_version,'dependencies':'ready'}),'')):
            return updates.stage_release(descriptor,directory)

    def test_verified_stage_does_not_activate_or_touch_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);profile=base/'profil-zuordnung.json';profile.write_text('keep me')
            result=self.stage(directory)
            self.assertTrue(Path(result['executable']).is_file())
            self.assertEqual(updates._checked_receipt(result,directory),Path(result['executable']))
            self.assertFalse((base/'app-update.json').exists())
            self.assertEqual(profile.read_text(),'keep me')

    def test_wrong_size_digest_or_probe_never_activate(self):
        for variant in ('truncated','digest','probe','version'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as directory:
                descriptor=release()
                if variant=='truncated':descriptor['size']+=1
                if variant=='digest':descriptor['sha256']='0'*64
                with self.assertRaises(ValueError):self.stage(directory,descriptor=descriptor,returncode=1 if variant=='probe' else 0,probe_version='1.0.0' if variant=='version' else '99.0.0')
                self.assertFalse((Path(directory)/'app-update.json').exists())
                self.assertEqual(list((Path(directory)/'updates').iterdir()),[])

    def test_wrong_platform_fails_before_network(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(updates,'platform_key',return_value='linux-x86_64'),patch.object(updates,'_open') as network:
            with self.assertRaises(ValueError):updates.stage_release(release(key='macos-arm64'),directory)
            network.assert_not_called()

    def test_launch_failure_restores_previous_pointer_and_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt=self.stage(directory);pointer=Path(directory)/'app-update.json';original=b'{"version":"1.0.0","custom":"keep"}'
            pointer.write_bytes(original)
            with patch.object(updates.subprocess,'Popen',side_effect=OSError('launch failed')):
                with self.assertRaises(OSError):updates.launch_updated(receipt,directory)
            self.assertEqual(pointer.read_bytes(),original)

    def test_tampered_package_never_launches_and_old_app_still_opens(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt=self.stage(directory);Path(receipt['executable']).write_text('modified')
            updates._atomic_json(Path(directory)/'app-update.json',receipt)
            with patch.object(updates.subprocess,'Popen') as launch:
                self.assertFalse(updates.redirect_to_update(APP_VERSION,directory))
            launch.assert_not_called()

    def test_external_executable_cannot_be_activated(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'outside';path.write_text('outside')
            with self.assertRaises(ValueError):updates._checked_receipt({'version':'99.0.0','executable':str(path),'sha256':updates._hash(path)},directory)

    def test_restart_drops_previous_bundle_environment_preserves_user_data(self):
        with patch.dict(os.environ,{'APPDIR':'old','LD_LIBRARY_PATH':'old','PYTHONHOME':'old'}):env=updates.launch_environment('test-data')
        for name in ('APPDIR','LD_LIBRARY_PATH','PYTHONHOME'):self.assertNotIn(name,env)
        self.assertEqual(env['PYINSTALLER_RESET_ENVIRONMENT'],'1')
        self.assertTrue(env['CFS_APP_DATA'].endswith('test-data'))

    def test_bundle_rejects_traversal_symlinks_and_wrong_root(self):
        for name,mode,content in [('CFS Tagwriter.app/../../escape',stat.S_IFREG,b'x'),('Other.app/file',stat.S_IFREG,b'x'),('CFS Tagwriter.app/link',stat.S_IFLNK,b'/tmp/escape'),('CFS Tagwriter.app/link',stat.S_IFLNK,b'../../escape')]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                package=Path(directory)/'app.zip'
                with zipfile.ZipFile(package,'w') as archive:
                    entry=zipfile.ZipInfo(name);entry.external_attr=(mode|0o755)<<16;archive.writestr(entry,content)
                with self.assertRaises(ValueError):updates._extract_mac(package,Path(directory)/'out')

    @unittest.skipIf(os.name=='nt','Creating framework links on Windows requires developer privileges.')
    def test_bundle_preserves_valid_framework_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            package=Path(directory)/'app.zip';destination=Path(directory)/'out'
            with zipfile.ZipFile(package,'w') as archive:
                archive.writestr('CFS Tagwriter.app/Contents/Frameworks/Versions/A/file',b'framework')
                entry=zipfile.ZipInfo('CFS Tagwriter.app/Contents/Frameworks/Versions/Current');entry.external_attr=(stat.S_IFLNK|0o777)<<16;archive.writestr(entry,'A')
            updates._extract_mac(package,destination)
            self.assertEqual((destination/'CFS Tagwriter.app/Contents/Frameworks/Versions/Current/file').read_bytes(),b'framework')


if __name__=='__main__':unittest.main()

class UpdateNotes(unittest.TestCase):
    def test_new_install_is_quiet_but_updated_version_notifies_until_acknowledged(self):
        from cfs_update_ui import notify_after_update
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            callbacks=[]
            root=SimpleNamespace(after=lambda delay,fn:callbacks.append(fn),grab_current=lambda:False)
            app=SimpleNamespace(data_dir=Path(directory),root=root,busy=False,close_pending=False)
            with patch('cfs_update_ui.show_notes') as show:
                notify_after_update(app,None,None)
                self.assertEqual(callbacks,[]);show.assert_not_called()
                (app.data_dir/'app-update-seen.json').write_text(json.dumps({'version':'1.0.0'}))
                notify_after_update(app,None,None);self.assertEqual(len(callbacks),1)
                callbacks.pop()();show.assert_called_once_with(app,None,None,automatic=True)
                # Only acknowledgement suppresses subsequent starts.
                notify_after_update(app,None,None);self.assertEqual(len(callbacks),1)
                callbacks.clear()
                (app.data_dir/'app-update-seen.json').write_text(json.dumps({'version':APP_VERSION}))
                notify_after_update(app,None,None);self.assertEqual(callbacks,[])

    def test_notification_waits_for_active_tag_operation(self):
        from cfs_update_ui import notify_after_update
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            callbacks=[]
            root=SimpleNamespace(after=lambda delay,fn:callbacks.append(fn),grab_current=lambda:False)
            app=SimpleNamespace(data_dir=Path(directory),root=root,busy=True,close_pending=False)
            (app.data_dir/'app-update.json').write_text(json.dumps({'version':APP_VERSION}))
            with patch('cfs_update_ui.show_notes') as show:
                notify_after_update(app,None,None);callbacks.pop()();show.assert_not_called()
                app.busy=False;callbacks.pop()();show.assert_called_once()
