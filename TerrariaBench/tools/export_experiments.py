"""Export compact, audited experiment records without saves, screenshots or keys."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from analyze_experiments import analyze


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('campaign', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--prior-session-usd', default='0.086400375',
                   help='reported charges outside this campaign ledger, for the budget snapshot')
    args = p.parse_args()
    analyze(args.campaign)
    rows = json.loads((args.campaign / 'summary.json').read_text())
    if any(r['audit'].startswith('FAIL') for r in rows):
        raise ValueError('resolve artifact audit failures before exporting')
    args.output.mkdir(parents=True, exist_ok=True)
    provenance = {}
    for row in rows:
        source = args.campaign / row['run']
        target = args.output / row['run']
        target.mkdir(exist_ok=True)
        provenance[row['run']] = {}
        for name in ('manifest.json', 'result.json', 'audit.json'):
            data = (source / name).read_bytes()
            (target / name).write_bytes(data)
            provenance[row['run']][name] = hashlib.sha256(data).hexdigest()
    for name in ('summary.csv', 'summary.json'):
        shutil.copyfile(args.campaign / name, args.output / name)
    for plan in args.campaign.glob('*-frozen.json'):
        shutil.copyfile(plan, args.output / plan.name)
    ledger = json.loads((args.campaign / 'ledger.json').read_text())
    budget = {k: ledger[k] for k in ('limit_usd', 'spent_usd', 'pending')}
    budget['prior_session_reported_usd'] = args.prior_session_usd
    (args.output / 'budget-snapshot.json').write_text(json.dumps(budget, indent=2)+'\n')
    (args.output / 'record-hashes.json').write_text(json.dumps(provenance, indent=2)+'\n')
    probe = args.campaign / 'perception' / 'rescored.json'
    if probe.exists():
        shutil.copyfile(probe, args.output / 'perception-rescored.json')
    print(json.dumps({'exported_completed_runs': len(rows), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
