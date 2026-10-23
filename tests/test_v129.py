"""Packaging regression: runtime NumPy backend discovery and frozen build gate."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from build_support.scipy_bundle import scipy_hidden_imports
from psrtty.skimmer_selftest import main
from tools.check_frozen_skimmer import check

ROOT=Path(__file__).resolve().parents[1]


class Bundle129Tests(unittest.TestCase):
    def test_both_scipy_locations_collect_numpy_and_common_not_gpu_backends(self):
        for parent in ('scipy._external','scipy._lib'):
            def present(name):
                return object() if name==parent+'.array_api_compat' else None
            def modules(package, **kwargs):
                self.assertEqual(kwargs['on_error'],'raise')
                return [package,package+'.fft',package+'.linalg'] if package.endswith('.numpy') else [package,package+'._helpers']
            with patch('build_support.scipy_bundle.find_spec',side_effect=present),patch('PyInstaller.utils.hooks.collect_submodules',side_effect=modules):
                found=scipy_hidden_imports()
            self.assertIn(parent+'.array_api_compat.numpy.fft',found)
            self.assertIn(parent+'.array_api_compat.numpy.linalg',found)
            self.assertFalse(any('torch' in s or 'cupy' in s for s in found))

    def test_new_unknown_layout_or_incomplete_backend_stops_build(self):
        with patch('build_support.scipy_bundle.find_spec',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'not found'):scipy_hidden_imports()
        with patch('build_support.scipy_bundle.find_spec',return_value=object()),patch('PyInstaller.utils.hooks.collect_submodules',side_effect=lambda p,**kw:[p]):
            with self.assertRaisesRegex(RuntimeError,'Incomplete'):scipy_hidden_imports()

    def test_actual_installed_backend_includes_fft_and_linalg(self):
        hidden=scipy_hidden_imports()
        for name in hidden:self.assertIsNotNone(importlib.util.find_spec(name))
        self.assertTrue(any(name.endswith('.numpy.fft') for name in hidden))
        self.assertTrue(any(name.endswith('.numpy.linalg') for name in hidden))


class SelfTest129Tests(unittest.TestCase):
    def test_source_smoke_decodes_both_calls_without_hardware(self):
        with tempfile.TemporaryDirectory() as d:
            report=Path(d)/'result.json'
            self.assertEqual(main(report),0)
            data=json.loads(report.read_text(encoding='utf-8'))
            self.assertTrue(data['ok']);self.assertFalse(data['frozen'])
            self.assertEqual(data['calls'],['JA1ABC','JA2XYZ'])

    def test_missing_fft_is_caught_before_release(self):
        code='''import importlib.abc,sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.endswith('.array_api_compat.numpy.fft'):
   raise ModuleNotFoundError('simulated missing '+fullname,name=fullname)
sys.meta_path.insert(0,Block())
from psrtty.skimmer_selftest import main
raise SystemExit(main(sys.argv[1]))
'''
        with tempfile.TemporaryDirectory() as d:
            report=Path(d)/'result.json'
            p=subprocess.run([sys.executable,'-c',code,str(report)],cwd=ROOT,timeout=30,capture_output=True)
            self.assertEqual(p.returncode,1,p.stderr)
            data=json.loads(report.read_text(encoding='utf-8'))
            self.assertFalse(data['ok']);self.assertIn('ModuleNotFoundError',data['error']);self.assertIn('numpy.fft',data['error'])

    def test_gate_rejects_bad_or_nonfrozen_reports_and_nonzero_exit(self):
        for frozen,ok,exitcode in [(False,True,0),(True,False,0),(True,True,1)]:
            def run(args,**kw):
                self.assertNotEqual(Path(kw['cwd']),ROOT)
                Path(args[-1]).write_text(json.dumps({'ok':ok,'frozen':frozen,'version':'1.30','calls':['JA1ABC','JA2XYZ']}),encoding='utf-8')
                return subprocess.CompletedProcess(args,exitcode,stdout=b'',stderr=b'')
            with patch('tools.check_frozen_skimmer.subprocess.run',side_effect=run):
                with self.assertRaises(RuntimeError):check(ROOT/'psrtty.py')

    def test_gate_rejects_absent_report(self):
        with patch('tools.check_frozen_skimmer.subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout=b'',stderr=b'')):
            with self.assertRaisesRegex(RuntimeError,'no report'):check(ROOT/'psrtty.py')
