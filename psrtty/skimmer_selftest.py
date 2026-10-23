"""Hardware-free DSP smoke test, executed by the actual packaged application.

Imports are deliberately inside the test so even import failures produce a
UTF-8 JSON report. No audio device, CAT/PTT, DLL or GUI is opened.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


def check_dsp():
    import numpy as np
    import scipy
    from scipy.signal import hilbert, lfilter
    from .ry_skimmer import FIRDecimator, SkimmerEngine
    from .live_tx import ToneEncoder

    # Check streaming FIR state at an awkward block boundary, not just import.
    x = (np.arange(4097) % 17 - 8).astype(np.complex64)
    decimator = FIRDecimator(8)
    actual = np.concatenate([decimator.feed(x[:733]), decimator.feed(x[733:])])
    expected = lfilter(decimator.taps, [1], x)[::8]
    if not np.allclose(actual, expected, atol=2e-6):
        raise RuntimeError('Skimmer streaming FIR check failed')

    rate = 48000
    signals = []
    for offset, call in ((-3000, 'JA1ABC'), (3000, 'JA2XYZ')):
        encoder = ToneEncoder(rate, 45.45, 2210, 2040, False)
        text = ('CQ CQ DE ' + call + ' ' + call + ' 599 001 ') * 3
        audio = np.concatenate([encoder.tone(True, 8), encoder.code(31),
                                *[encoder.char(ch) for ch in text], encoder.tone(True, 20)])
        signals.append(hilbert(audio) * np.exp(2j * np.pi * (offset - 2125) * np.arange(len(audio)) / rate))
    iq = sum(signals)
    received = []
    engine = SkimmerEngine(on_text=lambda *args: received.append(args))
    for start in range(0, len(iq), 4096):
        engine.feed(iq[start:start + 4096], rate, 14090000)
    calls = sorted({item[1] for item in received})
    if calls != ['JA1ABC', 'JA2XYZ'] or not all('599 001' in item[2] for item in received):
        raise RuntimeError('Skimmer synthetic IQ decode failed: ' + repr(calls))
    return {'numpy': np.__version__, 'scipy': scipy.__version__, 'calls': calls,
            'checks': ['streaming_fir', 'two_signal_iq_decode']}


def check_high_rate(seconds=3., decode=False):
    """Real-time asynchronous 1.92 MS/s / 512-sample producer.

    Generate only one short low-rate source; expand blocks as they are sent,
    never allocate a multi-gigabyte high-rate capture. This stresses the actual
    worker/queue, not just direct calls to SkimmerEngine.feed().
    """
    import time
    import numpy as np
    from scipy.signal import hilbert
    from .live_tx import ToneEncoder
    from .ry_skimmer import SkimmerWorker
    rate=1920000;low_rate=48000
    signals=[]
    for offset,call in ((-3000,'JA1ABC'),(3000,'JA2XYZ')):
        encoder=ToneEncoder(low_rate,45.45,2210,2040,False)
        text=('CQ DE '+call+' '+call+' 599 001 ')*3
        audio=np.concatenate([encoder.tone(True,8),encoder.code(31),
            *[encoder.char(ch) for ch in text],encoder.tone(True,20)])
        signals.append(hilbert(audio)*np.exp(2j*np.pi*(offset-2125)*np.arange(len(audio))/low_rate))
    low=np.asarray(sum(signals),dtype=np.complex64)
    duration=min(seconds,len(low)/low_rate);target=int(duration*rate)//512*512
    output=[];spectra=[]
    worker=SkimmerWorker(on_text=lambda *a:output.append(a),on_spectrum=lambda *a:spectra.append(a))
    worker.start();start=time.monotonic();position=0;max_queue=0.
    try:
        # Supply about 10 ms per producer wake-up, retaining 512-sample calls.
        while position<target:
            end=min(target,position+512*38)
            indexes=np.arange(position,end,dtype=np.int64)//40
            block=low[indexes]
            for i in range(0,len(block),512):worker.offer(block[i:i+512],rate,14090000)
            position=end;max_queue=max(max_queue,worker.queued_seconds)
            delay=start+position/rate-time.monotonic()
            if delay>0:worker.stop_event.wait(delay)
            if worker.error:raise RuntimeError(worker.error)
        deadline=time.monotonic()+3
        while worker.samples<target and time.monotonic()<deadline and not worker.error:
            worker.stop_event.wait(.01)
        elapsed=time.monotonic()-start
        stats=worker.snapshot()
        calls=sorted({r[1] for r in output})
        if worker.error or worker.samples!=target or worker.lost_samples or not spectra:
            raise RuntimeError('High-rate IQ stream failed: '+repr(stats)+' spectra='+str(len(spectra)))
        if decode and (calls!=['JA1ABC','JA2XYZ'] or not all('599 001' in r[2] for r in output)):
            raise RuntimeError('High-rate IQ decode failed: '+repr(calls))
        return dict(rate=rate,block=512,seconds=round(duration,3),samples=target,
            processed=worker.samples,lost_samples=worker.lost_samples,spectra=len(spectra),
            max_queue_ms=round(max_queue*1000,2),wall_seconds=round(elapsed,3),calls=calls)
    finally:worker.stop()


def main(report_path):
    from . import __version__
    report = {'version': __version__, 'frozen': bool(getattr(sys, 'frozen', False)), 'ok': False}
    code = 1
    try:
        report.update(check_dsp())
        report['high_rate']=check_high_rate()
        report['checks'].append('async_1920000_512')
        report['ok'] = True
        code = 0
    except Exception:
        report['error'] = traceback.format_exc()
    target = Path(report_path).resolve()
    # Caller creates the report directory. Write atomically; a stale/partial
    # report cannot be mistaken for a completed test by the build driver.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.tmp', mode='w',
                                         encoding='utf-8', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return code
