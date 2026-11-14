"""Validate UI fixtures against the live Pydantic block without changing shared files.
Requires pydantic v2: uv run --with 'pydantic>=2,<3' python scripts/check_contract.py
"""
import json
import re
import sys
import types
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = (ROOT / 'specs/SPEC.md').read_text()
block = spec.split('<!-- contract:start -->', 1)[1].split('<!-- contract:end -->', 1)[0]
source = re.search(r'```python\s*\n(.*?)```', block, re.S).group(1)
module = types.ModuleType('team_contract')
sys.modules[module.__name__] = module
exec(compile(source, str(ROOT / 'specs/SPEC.md'), 'exec'), module.__dict__)
count = 0
for path in sorted((ROOT / 'frontend/fixtures').glob('*.json')):
    fixture = json.loads(path.read_text())
    assert fixture['illustrative'] is True, f'{path}: missing illustrative marker'
    module.PropertySummary.model_validate(fixture['property'])
    for budget, run in fixture['runs'].items():
        result = module.RunResult.model_validate(run)
        assert result.plan.budget_usd == float(budget)
        assert result.plan.total_upfront_usd.expected <= result.plan.budget_usd
        count += 1
    print(f'{path.name}: valid PropertySummary + {len(fixture["runs"])} RunResult snapshots')
print(f'PASS: {count} complete run snapshots validate against schema {module.SCHEMA_VERSION}.')
