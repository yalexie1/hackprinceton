"""Validate UI fixtures against the live Pydantic block without changing shared files.
Requires pydantic v2: uv run --with 'pydantic>=2,<3' python scripts/check_contract.py
"""
import json
import re
import sys
sys.dont_write_bytecode = True
import types
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = (ROOT / 'specs/SPEC.md').read_text()
block = spec.split('<!-- contract:start -->', 1)[1].split('<!-- contract:end -->', 1)[0]
source = re.search(r'```python\s*\n(.*?)```', block, re.S).group(1)
module = types.ModuleType('team_contract')
sys.modules[module.__name__] = module
exec(compile(source, str(ROOT / 'specs/SPEC.md'), 'exec'), module.__dict__)
actual = None
if (ROOT / 'backend/schema.py').exists():
    import importlib
    sys.path.insert(0, str(ROOT))
    actual = importlib.import_module('backend.schema')
    assert actual.SCHEMA_VERSION == module.SCHEMA_VERSION
    assert actual.RunResult.model_json_schema() == module.RunResult.model_json_schema(), 'Backend RunResult differs from SPEC'
    assert actual.DocumentDraft.model_json_schema() == module.DocumentDraft.model_json_schema(), 'Backend DocumentDraft differs from SPEC'
    print('Backend schema.py matches the SPEC contract.')
count = 0
for path in sorted((ROOT / 'frontend/fixtures').glob('*.json')):
    fixture = json.loads(path.read_text())
    assert fixture['illustrative'] is True, f'{path}: missing illustrative marker'
    module.PropertySummary.model_validate(fixture['property'])
    for budget, run in fixture['runs'].items():
        result = module.RunResult.model_validate(run)
        if actual:
            actual.RunResult.model_validate(run)
        assert result.schema_version == module.SCHEMA_VERSION
        assert result.plan.budget_usd == float(budget)
        assert result.plan.total_upfront_usd.expected <= result.plan.budget_usd
        count += 1
    print(f'{path.name}: valid PropertySummary + {len(fixture["runs"])} RunResult snapshots')
for run_path in sorted((ROOT / 'specs/examples').glob('*/run_result.json')):
    folder = run_path.parent
    kind = folder.name
    for name, cls in [('run_result', module.RunResult), ('property_bundle', module.PropertyBundle), ('building_model', module.BuildingModel), ('document_request', module.DocumentRequest), ('document_draft', module.DocumentDraft)]:
        model = cls.model_validate_json((folder / f'{name}.json').read_text())
        if actual:
            getattr(actual, cls.__name__).model_validate_json((folder / f'{name}.json').read_text())
        if hasattr(model, 'schema_version'):
            assert model.schema_version == module.SCHEMA_VERSION
    for event in json.loads((folder / 'run_events.json').read_text()):
        module.RunEvent.model_validate(event)
    count += 1
    print(f'Shared {kind}: valid run, bundle, model, document request/draft, and event stream')
print(f'PASS: {count} complete run snapshots validate against schema {module.SCHEMA_VERSION}.')
