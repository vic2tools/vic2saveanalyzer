"""Compare invention settlement, finished nations, tables and state chunks."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from outcome import SKIPPED
import fastscan


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('saves')
    ap.add_argument('--mod', required=True)
    ap.add_argument('--every', type=int, default=17)
    args = ap.parse_args()
    binary = fastscan.available()
    if not binary:
        return SKIPPED
    with tempfile.TemporaryDirectory(prefix='vic2intermediate') as tmp:
        saves = Path(tmp, 'saves')
        saves.mkdir()
        names = sorted(Path(args.saves).glob('*.v2'))
        if not names:
            return SKIPPED
        # These inputs are read-only; no fixture builder is called here.
        for source in dict.fromkeys(names[::args.every] + names[-1:]):
            import shutil
            shutil.copy2(source, saves / source.name)
        out = Path(tmp, 'oracle')
        subprocess.run([sys.executable, str(HERE / 'testkit/engine_oracle.py'),
                        str(saves), args.mod, str(out), '--jobs', '3'], check=True)
        subprocess.run([binary, 'report', str(out / 'spec.json'), '--dump', str(out)],
                       check=True, stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, str(HERE / 'testkit/engine_dumpcheck.py'), str(out)],
                       check=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
