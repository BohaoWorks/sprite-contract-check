"""Run the two synthetic examples and check their documented exit codes.

Install the checkout first: python -m pip install .
Run: python examples/quickstart.py --output-dir demo-output
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('demo-output'))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parent / 'demo'
    print('sprite-contract-check | original synthetic fixtures', flush=True)
    for case, expected in [('repacked', 0), ('changed', 1)]:
        report = args.output_dir / case
        command = [sys.executable, '-m', 'sprite_contract_check',
                   str(fixtures / 'before.json'), str(fixtures / 'before.png'),
                   str(fixtures / f'{case}.json'), str(fixtures / f'{case}.png'),
                   '--old-indices', str(fixtures / 'before-indices.json'),
                   '--new-indices', str(fixtures / f'{case}-indices.json'),
                   '--json', str(report.with_suffix('.json')),
                   '--html', str(report.with_suffix('.html'))]
        run = subprocess.run(command, capture_output=True, text=True)
        if run.returncode != expected:
            print(f'{case}: expected exit {expected}; received {run.returncode}', file=sys.stderr)
            print(run.stderr or run.stdout, file=sys.stderr)
            return 2
        try:
            result = json.loads(run.stdout)
            counts = result['summary']
            if result['compatible'] != (expected == 0):
                raise ValueError('exit code and compatible field disagree')
            print(f'\n{case}: {result["status"]} | exit {run.returncode}')
            for key in ['matched', 'packing_changed', 'pixels_changed',
                        'duration_changed', 'removed', 'tags_changed']:
                print(f'  {key}: {counts[key]}')
        except (KeyError, ValueError, TypeError) as exc:
            print(f'{case}: unexpected report: {exc}', file=sys.stderr)
            return 2
        print(f'  HTML report: {report.with_suffix(".html")}')
    print('\nBoth expected outcomes verified. Open the HTML files locally.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
