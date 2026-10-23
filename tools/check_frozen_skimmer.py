"""Fail the build unless this exact frozen executable can decode synthetic IQ."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def check(executable, timeout=120):
    from psrtty import __version__
    executable = Path(executable).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='psrtty-frozen-check-') as directory:
        report_path = Path(directory) / 'result.json'
        # A separate empty cwd prevents accidental imports from the source tree.
        result = subprocess.run([str(executable), '--self-test-skimmer', str(report_path)],
                                cwd=directory, timeout=timeout, capture_output=True)
        if not report_path.is_file():
            raise RuntimeError('Frozen skimmer test produced no report; exit=' + str(result.returncode)
                               + '\n' + result.stderr.decode('utf-8', errors='replace')[-4000:])
        report = json.loads(report_path.read_text(encoding='utf-8'))
        if result.returncode or report.get('ok') is not True or report.get('frozen') is not True:
            raise RuntimeError('Frozen skimmer test failed: ' + json.dumps(report, ensure_ascii=False))
        if report.get('version') != __version__ or report.get('calls') != ['JA1ABC', 'JA2XYZ']:
            raise RuntimeError('Unexpected frozen skimmer test report: ' + repr(report))
        high=report.get('high_rate',{})
        if ('async_1920000_512' not in report.get('checks',[]) or high.get('rate')!=1920000
                or high.get('block')!=512 or high.get('lost_samples')!=0
                or high.get('processed')!=high.get('samples') or not high.get('spectra')):
            raise RuntimeError('Frozen high-rate IQ stream test missing or failed: '+repr(high))
        return report


if __name__ == '__main__':
    # Direct invocation adds tools/, so explicitly expose the project package.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    print(json.dumps(check(sys.argv[1]), ensure_ascii=False, indent=2))
