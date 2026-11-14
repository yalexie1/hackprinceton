"""Import completed shared RunResult examples; write only frontend-owned fixture files."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
shared = ROOT / 'specs/examples'
if not shared.exists():
    raise SystemExit('Shared specs/examples/ is not present yet; existing frontend fixtures were left unchanged.')
found = {'house': {}, 'office': {}}
for path in sorted(shared.rglob('*.json')):
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not {'run_id', 'request', 'property', 'plan'} <= data.keys():
        continue
    if data.get('status') != 'done' or not data.get('plan'):
        continue
    kind = 'office' if data['property']['segment'] == 'commercial' else 'house'
    # A fixture set corresponds to one property; never mix SIDs across budgets.
    prior = next(iter(found[kind].values()), None)
    if prior and prior['property']['sid'] != data['property']['sid']:
        continue
    key = str(int(data['request']['budget_usd']))
    found[kind][key] = data
if not all(found.values()):
    raise SystemExit('Need at least one completed house and office RunResult. Existing frontend fixtures were left unchanged.')
for kind, runs in found.items():
    prop = next(iter(runs.values()))['property']
    # Specs examples are illustrative. Real licensed sponsor captures belong to the data lane.
    output = {'illustrative': True, 'property': prop, 'runs': runs}
    (ROOT / f'frontend/fixtures/{kind}.json').write_text(json.dumps(output, indent=2) + '\n')
    print(f'Imported {len(runs)} {kind} budget scenario(s). Run check_contract.py before committing.')
