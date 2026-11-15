

# ---- split / low-confidence gate (issue: one panorama out of 39 deciding $722/yr) ----

def _reading(pano_id, section, fields, conf):
    from backend.analysis.vision.interior import PanoReading, Section
    kw = {"windows": None, "hvac": None, "water_heater": None, "lighting": None, "feasibility": None}
    kw[section] = Section(fields=fields, confidence=conf, note=None)
    return PanoReading(pano_id=pano_id, **kw)


def test_a_one_to_one_split_does_not_override_the_default():
    # The house: 2 of 39 panoramas see a thermostat and they disagree, 0.35 vs 0.30.
    # The old combiner picked the 0.05-higher one and returned it at confidence 0.19,
    # which swung a $722/yr recommendation on a $312 device.
    from backend.analysis.vision.interior import _categorical
    readings = [_reading("p1", "hvac", {"thermostat": "smart"}, 0.35),
                _reading("p2", "hvac", {"thermostat": "manual"}, 0.30)]
    assert _categorical(readings, "hvac", "thermostat") is None


def test_a_clear_majority_still_overrides():
    from backend.analysis.vision.interior import _categorical
    readings = [_reading(f"p{i}", "hvac", {"thermostat": "smart"}, 0.6) for i in range(3)]
    readings.append(_reading("p9", "hvac", {"thermostat": "manual"}, 0.3))
    out = _categorical(readings, "hvac", "thermostat")
    assert out is not None and out[0] == "smart"


def test_a_unanimous_single_confident_reading_still_overrides():
    # One clear sighting of something only visible once must still count.
    from backend.analysis.vision.interior import _categorical
    out = _categorical([_reading("p1", "hvac", {"thermostat": "smart"}, 0.8)], "hvac", "thermostat")
    assert out is not None and out[0] == "smart"


def test_a_unanimous_but_very_weak_reading_does_not_override():
    from backend.analysis.vision.interior import _categorical
    assert _categorical([_reading("p1", "hvac", {"thermostat": "smart"}, 0.1)],
                        "hvac", "thermostat") is None


def test_an_alphabetical_tie_break_can_no_longer_decide_anything():
    # Exactly equal weights previously resolved by sorting the value name.
    from backend.analysis.vision.interior import _categorical
    readings = [_reading("p1", "hvac", {"thermostat": "manual"}, 0.5),
                _reading("p2", "hvac", {"thermostat": "smart"}, 0.5)]
    assert _categorical(readings, "hvac", "thermostat") is None
