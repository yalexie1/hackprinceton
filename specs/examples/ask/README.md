# Ask-rule fixtures (package A27)

Two `BuildingModel` files, both derived from `../house/building_model.json`, so the ask rule
(SPEC 5.3) has one input that must fire and one that must stay silent (SPEC 14).

- `building_model_wide.json`: the house model as it stands. The editable assumptions carry the
  wide vintage-default and vision ranges: `electrical.service_amps` 60 / 100 / 200 A,
  `roof.u_value` 0.182 / 0.403 / 1.703 W/m2K, `infiltration.ach50` 6 / 15 / 30. Whatever plan
  function is passed to `sensitivity`, these spread the plan's annual savings by more than
  `ASK_WIDTH`, or change the selected measures, or both.
- `building_model_narrow.json`: the same model with every editable numeric assumption known
  to within one percent (`low = 0.99 x expected`, `high = 1.01 x expected`, `source = user`,
  `confidence = 1`). No single assumption can move the plan's savings by 40 percent.

Illustrative, like the rest of `specs/examples/`: no sponsor data. Tests: `pytest
backend/analysis/finance/sensitivity -q`.
