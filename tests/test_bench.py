"""Notebook bench contracts, using the installed package and local assets."""

import json
from copy import deepcopy
from importlib.resources import files

import numpy as np
import pytest
from owl.bench import Bench
from owl import Interface, Mirror, ThickLens
from owl.core import FreeSpace, GaussianBeam, OpticalSystem, ThinLens


@pytest.fixture
def system():
    return OpticalSystem((FreeSpace(100), ThinLens(75), FreeSpace(150)))


@pytest.fixture
def bench(system):
    widget = Bench(system)
    yield widget
    widget.close()


def test_defaults_and_core_owned_results(bench, system):
    assert bench.beam == GaussianBeam(0.1, 550)
    assert bench.settings["ray_span_mm"] == 0.25
    assert bench.settings["ray_count"] == 11
    assert bench.error == ""
    rays = system.trace(np.vstack((np.linspace(-0.25, 0.25, 11), np.zeros(11))))
    gaussian = system.gaussian(bench.beam)
    np.testing.assert_allclose(bench.result["rays"]["z_mm"], rays.z_mm)
    np.testing.assert_allclose(bench.result["rays"]["y_mm"], rays.rays[:, 0, :])
    np.testing.assert_allclose(bench.result["gaussian"]["radius_mm"], gaussian.radius_mm)
    assert bench.result["elements"][1]["z_mm"] == 100
    assert bench.result["metrics"]["length_mm"] == 250
    assert bench.result["metrics"]["output_radius_mm"] == gaussian.radius_mm[-1]
    json.dumps(bench.get_state(), allow_nan=False)
    for name in ("settings", "result", "error"):
        assert bench.traits()[name].metadata["sync"] is True


def test_python_updates_and_observable_result(bench):
    changes = []
    bench.observe(changes.append, names="result")
    settings = bench.to_dict()
    settings["beam"]["waist_mm"] = 0.2
    settings["beam"]["wavelength_nm"] = 780
    settings["ray_count"] = 1
    settings["system"]["elements"][1]["focal_length_mm"] = -50
    bench.settings = settings
    assert changes
    assert bench.beam == GaussianBeam(0.2, 780)
    assert bench.system.elements[1] == ThinLens(-50)
    assert all(row == [0.0] for row in bench.result["rays"]["y_mm"])
    assert bench.error == ""


@pytest.mark.parametrize("section,key,value", [
    (None, "ray_span_mm", -1), (None, "ray_span_mm", float("nan")),
    (None, "ray_span_mm", float("inf")), (None, "ray_span_mm", True),
    (None, "ray_span_mm", "0.2"), (None, "ray_span_mm", 10**400),
    (None, "ray_count", 0), (None, "ray_count", 2.5),
    (None, "ray_count", True), (None, "ray_count", float("inf")),
    ("beam", "waist_mm", 0), ("beam", "wavelength_nm", -550),
    ("beam", "waist_mm", 1e-300), ("beam", "waist_mm", 1e300),
    ("beam", "wavelength_nm", float("nan")),
])
def test_invalid_update_rolls_back_and_recovers(bench, section, key, value):
    before = bench.to_dict()
    result = deepcopy(bench.result)
    invalid = deepcopy(before)
    (invalid if section is None else invalid[section])[key] = value
    bench.settings = invalid
    assert bench.error
    assert bench.settings == before
    assert bench.to_dict() == before
    assert bench.result == result
    json.dumps(bench.get_state(), allow_nan=False)
    valid = bench.to_dict()
    valid["ray_span_mm"] = 0.5
    bench.settings = valid
    assert bench.error == ""
    assert bench.settings == valid


def test_equal_settings_are_validated_and_can_clear_errors(bench):
    valid = bench.to_dict()
    invalid = deepcopy(valid)
    invalid["beam"]["schema_version"] = True
    bench.settings = invalid
    assert bench.error
    assert type(bench.settings["beam"]["schema_version"]) is int
    bench.settings = valid
    assert not bench.error


def test_frontend_state_update_rollback(bench):
    before = bench.to_dict()
    invalid = deepcopy(before)
    invalid["system"]["elements"][1]["focal_length_mm"] = 0
    bench.set_state({"settings": invalid})
    assert bench.error
    assert bench.settings == before
    valid = deepcopy(before)
    valid["system"]["elements"][0]["distance_mm"] = 25
    bench.set_state({"settings": valid})
    assert not bench.error
    assert bench.result["metrics"]["length_mm"] == 175


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(extra=1),
    lambda s: s.pop("beam"),
    lambda s: s["beam"].update(schema_version=True),
    lambda s: s["system"].update(elements=[{"type": "unknown"}]),
    lambda s: s["system"].update(elements=None),
    lambda s: s["system"]["elements"][0].update(distance_mm=-1),
    lambda s: s["system"]["elements"][1].update(focal_length_mm=0),
])
def test_strict_serialization_and_update_schema(bench, mutation):
    before = bench.to_dict()
    invalid = deepcopy(before)
    mutation(invalid)
    with pytest.raises(ValueError):
        Bench.from_dict(invalid)
    bench.settings = invalid
    assert bench.settings == before
    assert bench.error


def test_round_trip_and_detached_instances(bench):
    payload = json.loads(json.dumps(bench.to_dict(), allow_nan=False))
    restored = Bench.from_dict(payload)
    other = Bench(bench.system)
    try:
        assert restored.to_dict() == bench.to_dict()
        assert restored.result == bench.result
        payload["beam"]["waist_mm"] = 99
        assert restored.beam.waist_mm == 0.1
        settings = restored.to_dict()
        settings["beam"]["waist_mm"] = 0.3
        restored.settings = settings
        assert bench.beam.waist_mm == other.beam.waist_mm == 0.1
        restored.result["rays"]["y_mm"][0][0] = 999
        assert bench.result["rays"]["y_mm"][0][0] != 999
    finally:
        restored.close()
        other.close()


@pytest.mark.parametrize("elements", [(), (ThinLens(-50),), (FreeSpace(0), ThinLens(50), FreeSpace(0))])
def test_zero_length_and_empty_systems(elements):
    widget = Bench(OpticalSystem(elements), ray_span_mm=0, ray_count=1)
    try:
        assert widget.result["metrics"]["length_mm"] == 0
        assert widget.result["metrics"]["output_ray_half_span_mm"] == 0
        json.dumps(widget.get_state(), allow_nan=False)
    finally:
        widget.close()


@pytest.mark.parametrize("kwargs", [
    {"system": None}, {"beam": None}, {"ray_count": False},
    {"ray_span_mm": float("inf")}, {"ray_span_mm": 10**400},
    {"beam": GaussianBeam(1e-300, 550)},
])
def test_invalid_constructor_raises_value_error(system, kwargs):
    with pytest.raises(ValueError):
        Bench(**{"system": system, **kwargs})


def test_new_elements_positions_after_internal_and_reflected_travel():
    system = OpticalSystem((
        FreeSpace(20), ThickLens(60, -60, 10, 1.5),
        Mirror(), FreeSpace(50), Interface(np.inf, 1, 1.5), FreeSpace(10),
    ))
    widget = Bench(system)
    try:
        elements = widget.result["elements"]
        assert [e["start_z_mm"] for e in elements] == [0, 20, 30, 30, -20, -20]
        assert [e["z_mm"] for e in elements] == [20, 30, 30, -20, -20, -30]
        assert elements[1]["type"] == "thick_lens"
        assert "Thick lens" in elements[1]["label"]
        assert elements[2]["radius_mm"] is None
        assert "Mirror" in elements[2]["label"]
        assert "Interface" in elements[4]["label"]
        assert widget.result["metrics"]["length_mm"] == 90
        assert widget.result["metrics"]["output_z_mm"] == -30
        assert widget.result["metrics"]["output_n"] == 1.5
        assert widget.result["metrics"]["output_direction"] == -1
        payload = json.loads(json.dumps(widget.to_dict(), allow_nan=False))
        restored = Bench.from_dict(payload)
        try:
            assert restored.result == widget.result
        finally:
            restored.close()
    finally:
        widget.close()


def test_frontend_new_elements_reject_mismatched_medium(bench):
    settings = bench.to_dict()
    settings["system"]["elements"] = [Interface(np.inf, 1, 1.5).to_dict()]
    bench.set_state({"settings": settings})
    assert not bench.error
    valid = bench.to_dict()
    settings = deepcopy(valid)
    settings["system"]["elements"].append(ThickLens(60, -60, 10, 1.5).to_dict())
    bench.set_state({"settings": settings})
    assert "surrounding air" in bench.error
    assert bench.to_dict() == valid


def test_rounded_settings_match_calculated_field(bench):
    settings = bench.to_dict()
    settings["beam"].update(waist_mm=0.223057660321567, wavelength_nm=685.888550041586)
    bench.set_state({"settings": settings})
    assert bench.beam == GaussianBeam(0.223, 686)
    expected = bench.system.gaussian(bench.beam)
    np.testing.assert_allclose(bench.result["gaussian"]["radius_mm"], expected.radius_mm)
    assert bench.result["metrics"]["output_radius_mm"] == expected.radius_mm[-1]


def test_installed_assets_are_local_and_complete(bench):
    static = files("owl").joinpath("static")
    js = static.joinpath("bench.js").read_text()
    css = static.joinpath("bench.css").read_text()
    assert "export default { render }" in js
    assert 'model.off("change:settings", drawControls)' in js
    assert 'model.off("change:result", drawPlot)' in js
    assert 'model.off("change:error", showError)' in js
    assert "root.remove()" in js
    assert "https://" not in js
    assert ".owl-bench" in css
    assert "focus-visible" in css
    assert bench.get_state()["_esm"] == js
    assert bench.get_state()["_css"] == css
