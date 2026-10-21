"""Real temporary installs; retention never traverses live QSO/config trees."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from psrtty.update_storage import maintain_storage, storage_lock, StorageBusy, owner_marker, _archive


class StorageRetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'var/updates').mkdir(parents=True);(self.root/'var/backups').mkdir()
        (self.root/'var/psrtty-release.json').write_text(json.dumps({'product':'PSRTTY','version':'1.28'}),encoding='utf-8')
        (self.root/'psrtty.exe').write_bytes(b'MZcurrent')
        for n in ('config/user.json','logdata/202610.adi','logdata/20261021_all.txt','logdata/backups/user.zip'):
            p=self.root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'LIVE '+n.encode())
        self.live={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
    def generation(self,kind,index,owner=None):
        name=f'{index:032x}' if kind=='update' else f'20261021_1200{index:02}_{index:08x}'
        p=self.root/'var'/('updates' if kind=='update' else 'backups')/name;p.mkdir()
        if kind=='update':
            request=p/'request.json';request.write_text(json.dumps({'version':'1.28',**({'owner':owner} if owner else {})}),encoding='utf-8')
            (p/'release.zip').write_bytes(b'fake-compressed-release-'+str(index).encode())
            (p/'payload').mkdir();(p/'payload/psrtty.exe').write_bytes(b'redundant')
            (p/'psrtty-updater.exe').write_bytes(b'helper')
            os.utime(request,(index,index))
        else:
            (p/'psrtty.exe').write_bytes(b'MZold'+str(index).encode())
            for n in ('config/user.json','logdata/qso.adi','logdata/backups/duplicated.zip'):
                f=p/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b'snapshot '+n.encode())
        os.utime(p,(index,index));return p
    def unchanged(self):
        for name,data in self.live.items():self.assertEqual((self.root/name).read_bytes(),data,name)
    def test_existing_folders_become_one_and_two_archives_oldest_removed(self):
        updates=[self.generation('update',i) for i in range(1,9)]
        backups=[self.generation('backup',i) for i in range(1,6)]
        maintain_storage(self.root)
        u=list((self.root/'var/updates').iterdir());b=list((self.root/'var/backups').iterdir())
        self.assertEqual(len(u),1);self.assertEqual(len(b),2);self.assertTrue(all(p.suffix=='.zip' and p.is_file() for p in u+b))
        self.assertIn(updates[-1].name,u[0].name)
        self.assertEqual({p.name for p in b},{'backup_'+p.name+'.zip' for p in backups[-2:]})
        with zipfile.ZipFile(u[0]) as z:
            self.assertIn('release.zip',z.namelist());self.assertNotIn('payload/psrtty.exe',z.namelist());self.assertNotIn('psrtty-updater.exe',z.namelist())
        with zipfile.ZipFile(b[-1]) as z:
            self.assertIn('logdata/qso.adi',z.namelist());self.assertFalse(any('logdata/backups/' in n for n in z.namelist()))
        self.unchanged();before={p.name:p.read_bytes() for p in u+b};maintain_storage(self.root)
        self.assertEqual(before,{p.name:p.read_bytes() for p in u+b});self.unchanged()
    def test_later_generation_rotates_mixed_legacy_and_archived_storage(self):
        self.generation('update',1);self.generation('backup',1);maintain_storage(self.root)
        self.generation('update',2);self.generation('backup',2);maintain_storage(self.root)
        stale=self.root/'var/.update-storage-abcdefgh.tmp';stale.write_bytes(b'incomplete old archive')
        unrelated=self.root/'var/user.tmp';unrelated.write_bytes(b'keep')
        self.generation('update',3);self.generation('backup',3);maintain_storage(self.root)
        self.assertFalse(stale.exists());self.assertEqual(unrelated.read_bytes(),b'keep')
        self.assertEqual(len(list((self.root/'var/updates').iterdir())),1)
        self.assertEqual(len(list((self.root/'var/backups').iterdir())),2);self.unchanged()
    def test_owner_process_protects_prepared_update_and_pid_reuse_does_not(self):
        marker=owner_marker();self.assertTrue(marker['start'])
        p=self.generation('update',1,marker)
        with self.assertRaises(StorageBusy):maintain_storage(self.root)
        self.assertTrue(p.is_dir())
        request=json.loads((p/'request.json').read_text(encoding='utf-8'));request['owner']['start']='different process creation'
        (p/'request.json').write_text(json.dumps(request),encoding='utf-8')
        maintain_storage(self.root);self.assertFalse(p.exists());self.unchanged()
    def test_updater_lease_blocks_cleanup(self):
        p=self.generation('update',1)
        with storage_lock(self.root):
            with self.assertRaises(StorageBusy):maintain_storage(self.root)
        self.assertTrue(p.is_dir());maintain_storage(self.root);self.assertFalse(p.exists())
    def test_old_windows_helper_is_protected_without_new_lease(self):
        p=self.generation('update',1)
        with patch('psrtty.update_storage._legacy_helper_busy',return_value=True):
            with self.assertRaises(StorageBusy):maintain_storage(self.root)
        self.assertTrue(p.is_dir());self.unchanged()
    def test_failed_archive_commit_preserves_all_old_generations(self):
        generations=[self.generation('update',i) for i in range(1,4)]
        with patch('psrtty.update_storage.os.replace',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):maintain_storage(self.root)
        self.assertTrue(all(p.is_dir() for p in generations));self.assertFalse(list((self.root/'var').glob('.update-storage-*.tmp')));self.unchanged()
    def test_interrupted_folder_delete_resumes_using_complete_archive(self):
        p=self.generation('backup',1)
        with patch('psrtty.update_storage.shutil.rmtree',side_effect=OSError('locked')):
            with self.assertRaises(OSError):_archive(p,'backup')
        archive=p.with_name('backup_'+p.name+'.zip');self.assertTrue(archive.exists())
        (p/'config/user.json').unlink();_archive(p,'backup')
        self.assertFalse(p.exists())
        with zipfile.ZipFile(archive) as z:self.assertEqual(z.read('config/user.json'),b'snapshot config/user.json')
    def test_corrupt_retained_archive_never_causes_older_good_copy_deletion(self):
        p=self.generation('update',1);bad=p.parent/('update_'+f'{2:032x}'+'.zip');bad.write_bytes(b'corrupt');os.utime(bad,(2,2))
        with self.assertRaises(zipfile.BadZipFile):maintain_storage(self.root)
        self.assertTrue(p.is_dir());self.unchanged()
    def test_unknown_item_is_preserved_with_explicit_error(self):
        p=self.generation('update',1);note=p.parent/'my_notes.txt';note.write_text('keep',encoding='utf-8')
        with self.assertRaises(OSError):maintain_storage(self.root)
        self.assertEqual(note.read_text(encoding='utf-8'),'keep');self.assertTrue(p.is_dir())
    def test_symlink_generation_is_never_followed(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td);(target/'keep.txt').write_bytes(b'outside')
            link=self.root/'var/updates'/f'{1:032x}'
            try:link.symlink_to(target,target_is_directory=True)
            except (OSError,NotImplementedError):self.skipTest('OS cannot create test symlink')
            with self.assertRaises(OSError):maintain_storage(self.root)
            self.assertEqual((target/'keep.txt').read_bytes(),b'outside')
    def test_missing_install_manifest_never_removes_data(self):
        p=self.generation('update',1);(self.root/'var/psrtty-release.json').unlink()
        with self.assertRaises(OSError):maintain_storage(self.root)
        self.assertTrue(p.exists())
    def test_source_change_during_pack_preserves_originals(self):
        p=self.generation('backup',1)
        original=zipfile.ZipFile.write
        def mutate(z,filename,*args,**kwargs):
            result=original(z,filename,*args,**kwargs)
            if str(filename).endswith('psrtty.exe'):Path(filename).write_bytes(b'changed')
            return result
        with patch.object(zipfile.ZipFile,'write',mutate):
            with self.assertRaises(StorageBusy):_archive(p,'backup')
        self.assertTrue(p.exists());self.assertFalse(p.with_name('backup_'+p.name+'.zip').exists())
