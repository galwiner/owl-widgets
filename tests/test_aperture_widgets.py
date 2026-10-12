"""Shared experiment state, clipping, and sampled wave results."""

import json
from copy import deepcopy

import numpy as np
import pytest
from owl import Aperture, Bench, CrossSection, FreeSpace, GaussianBeam, OpticalSystem


@pytest.fixture
def bench():
    widget = Bench(OpticalSystem((Aperture(0.1), FreeSpace(30))),
                   beam=GaussianBeam(0.1, 633), grid_size=64, window_mm=1)
    yield widget
    widget.close()


def test_aperture_results_and_serialized_sampling(bench):
    assert len(bench.result["cross_sections"]["planes"]) == 3
    assert len(bench.result["longitudinal"]["z_mm"]) > 3
    aperture_row = np.asarray(bench.result["longitudinal"]["intensity"][1])
    x = np.asarray(bench.result["longitudinal"]["x_mm"])
    assert np.all(aperture_row[np.abs(x) > 0.1] == 0)
    assert bench.result["elements"][0]["label"].startswith("Aperture")
    alive = np.asarray(bench.result["rays"]["alive"])
    assert np.all(alive[0]) and not np.all(alive[-1])
    assert bench.result["metrics"]["output_ray_count"] == alive[-1].sum()
    assert bench.result["metrics"]["transmission"] == pytest.approx(1 - np.exp(-2), abs=0.02)
    assert bench.result["metrics"]["output_ray_half_span_mm"] <= 0.1
    saved = json.loads(json.dumps(bench.to_dict(), allow_nan=False))
    restored = Bench.from_dict(saved)
    try:
        assert restored.result == bench.result
        assert restored.settings["wave"] == {"grid_size": 64, "window_mm": 1}
    finally:
        restored.close()


def test_linked_views_follow_edits_and_detach(bench):
    first, second = CrossSection(bench), CrossSection(bench)
    try:
        assert first.result == second.result == bench.result["cross_sections"]
        original = deepcopy(first.result)
        settings = bench.to_dict()
        settings["system"]["elements"][0]["radius_mm"] = 0.05
        bench.settings = settings
        assert first.result == second.result == bench.result["cross_sections"]
        assert first.result != original
        first.close()
        frozen = deepcopy(first.result)
        settings = bench.to_dict()
        settings["beam"]["wavelength_nm"] = 800
        bench.settings = settings
        assert first.result == frozen
        assert second.result == bench.result["cross_sections"]
        assert second.result != frozen
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize("wave", [None, {}, {"grid_size": 63, "window_mm": 1},
    {"grid_size": True, "window_mm": 1}, {"grid_size": 128, "window_mm": 0},
    {"grid_size": 128, "window_mm": float("nan")}])
def test_invalid_sampling_rolls_back_linked_views(bench, wave):
    view = CrossSection(bench)
    before, result = bench.to_dict(), deepcopy(view.result)
    try:
        settings = bench.to_dict()
        settings["wave"] = wave
        bench.settings = settings
        assert bench.error and view.error
        assert bench.to_dict() == before
        assert view.result == result
        bench.settings = before
        assert not bench.error and not view.error
    finally:
        view.close()


def test_legacy_settings_gain_sampling_defaults(bench):
    settings = bench.to_dict()
    del settings["wave"]
    restored = Bench.from_dict(settings)
    try:
        assert restored.settings["wave"] == {"grid_size": 128, "window_mm": None}
    finally:
        restored.close()


def test_all_rays_blocked_stays_json_safe(bench):
    settings = bench.to_dict()
    settings["system"]["elements"][0]["x_mm"] = 0.5
    bench.settings = settings
    assert bench.result["metrics"]["output_ray_count"] == 0
    assert bench.result["metrics"]["output_ray_half_span_mm"] == 0
    json.dumps(bench.result, allow_nan=False)


def test_cross_section_requires_bench():
    with pytest.raises(ValueError, match="Bench"):
        CrossSection(OpticalSystem())
