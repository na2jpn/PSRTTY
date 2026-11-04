"""ExtIO block contracts, error propagation and rebuilt native bridges."""
import io
import os
import struct
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from psrtty import i18n
from psrtty.ry_iq import ExtIOInput,pe_bits

ROOT=Path(__file__).resolve().parents[1]

class ExtIO132Tests(unittest.TestCase):
    def setUp(self):i18n.configure('ja')
    def tearDown(self):i18n.configure('ja')
    def test_reader_preserves_corrected_pairs_and_exact_gap(self):
        # Native counts are already I/Q PAIRS. Python must not halve them again.
        frames=[]
        for pos in (0,512,1536):
            iq=np.arange(1024,dtype='<f4').reshape(512,2)
            frames.append(struct.pack('<4sIIdq',b'RYIQ',512,1920000,7035000.,pos)+iq.tobytes())
        seen=[];error=Mock();source=ExtIOInput('fake.dll',7035000,lambda *a:seen.append(a),error)
        source.process=Mock(stdout=io.BytesIO(b''.join(frames)),stderr=io.BytesIO(b''));source.process.poll.return_value=0
        with patch('psrtty.ry_iq.event'):source._read()
        self.assertEqual([len(x[0]) for x in seen],[512]*3)
        self.assertEqual([x[3] for x in seen],[0,0,512])
        self.assertTrue(all(x[1]==1920000 for x in seen))
        self.assertEqual(seen[0][0][-1],1022+1023j)

    def test_native_contract_and_rate_errors_are_explained_in_each_language(self):
        for lang in i18n.LANGUAGES:
            i18n.configure(lang)
            for code,key in [('IQ_BLOCK_MISMATCH','ry.block_stopped'),('IQ_RATE_MISMATCH','ry.rate_stopped')]:
                errors=[];source=ExtIOInput('fake.dll',7035000,Mock(),errors.append)
                source.process=Mock(stdout=io.BytesIO(b''),stderr=io.BytesIO(('[error] '+code+' detail').encode()))
                source.process.poll.return_value=1
                with patch('psrtty.ry_iq.event'):source._read()
                self.assertEqual(len(errors),1);self.assertTrue(errors[0].startswith(i18n.tr(key)))
                self.assertIn(code,errors[0]);self.assertIn('(exit=1)',errors[0])
                self.assertNotEqual(i18n.tr(key),key)

    def test_packaged_bridges_have_new_contract_regression(self):
        for bits in (32,64):
            p=ROOT/f'lib/iq/psrtty-extio{bits}.exe'
            self.assertEqual(pe_bits(p),bits)
            self.assertIn('ExtIO pair/scalar contract'.encode('utf-16le'),p.read_bytes())

    @unittest.skipUnless(os.name=='nt','Windows native bridge execution; tested separately under Mono on Linux')
    def test_native_bridges_contract_formats_queue_clock_and_boundaries(self):
        for bits in (32,64):
            p=subprocess.run([str(ROOT/f'lib/iq/psrtty-extio{bits}.exe'),'--self-test'],capture_output=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stderr.decode('utf-8','replace'))
            self.assertIn(b'pair/scalar contract',p.stdout)
            self.assertNotIn(b'[error]',p.stderr)
