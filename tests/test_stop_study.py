"""Contracts for the reusable aperture/field/vignetting stop study."""

import json
from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest
from numpy.testing import assert_allclose
from owl.stop_study import StopStudySpec, calculate_stop_study


def _by_id(items):
    return {item["id"]: item for item in items}


@pytest.fixture(scope="module")
def study():
    return calculate_stop_study()


def test_defaults_are_the_original_relay_and_sampling_spec():
    spec = StopStudySpec()
    assert spec.relay_distance_mm == 100
    assert spec.focal_length_mm == 50
    assert spec.pupil_sample_radius_mm == 0.9
    assert (spec.aperture_stop_z_mm, spec.aperture_stop_radius_mm) == (100, 0.5)
    assert (spec.field_stop_z_mm, spec.field_stop_radius_mm) == (200, 1.2)
    assert (spec.vignette_stop_z_mm, spec.vignette_stop_radius_mm) == (150, 0.8)
    assert spec.diagram_field_heights_mm == (-2, -1, 0, 1, 2)
    assert_allclose(spec.diagram_pupil_heights_mm, np.linspace(-0.9, 0.9, 7), atol=0)
    assert_allclose(spec.illumination_field_heights_mm, np.linspace(-2.4, 2.4, 49))
    assert spec.pupil_map_field_heights_mm == (0, 1.4, 1.8, 2.05)
    assert (spec.pupil_count, spec.seed, spec.display_pupil_count) == (20_000, 1, 4_000)


def test_result_schema_is_finite_json_and_complete_for_all_panels(study):
    json.dumps(study, allow_nan=False)
    assert set(study) == {
        "schema_version", "spec", "ray_diagrams", "illumination", "pupil_maps",
        "stop_table", "plot",
    }
    assert len(study["ray_diagrams"]) == 3
    assert all(len(panel["paths"]) == 35 for panel in study["ray_diagrams"])
    assert all(len(panel["distinguished_paths"]) == 2 for panel in study["ray_diagrams"])
    assert len(study["illumination"]["field_heights_mm"]) == 49
    assert len(study["pupil_maps"]) == 4
    assert all(item["metric_sample_count"] == 20_000 for item in study["pupil_maps"])
    assert all(item["display_sample_count"] == 4_000 for item in study["pupil_maps"])


def test_original_flat_cliff_and_rolloff_assertions(study):
    heights = np.array(study["illumination"]["field_heights_mm"])
    curves = {item["id"]: np.array(item["relative"]) for item in study["illumination"]["curves"]}
    assert_allclose(curves["aperture_only"], 1, atol=0.02)
    assert curves["field_stop"][np.abs(heights) < 1.1].min() > 0.98
    assert curves["field_stop"][np.abs(heights) > 1.3].max() < 0.02
    edge = np.abs(heights) > 1.4
    assert 0.02 < curves["vignette_stop"][edge].max() < 0.7
    assert np.all(np.diff(curves["vignette_stop"][heights >= 0]) <= 1e-9)


def test_stop_coefficients_and_classification_match_taxonomy(study):
    stops = _by_id(study["stop_table"])
    assert_allclose([stops["aperture"]["A_pupil"], stops["aperture"]["B_field"]], [1, 0], atol=1e-12)
    assert_allclose([stops["field"]["A_pupil"], stops["field"]["B_field"]], [0, -1], atol=1e-12)
    assert_allclose([stops["vignette"]["A_pupil"], stops["vignette"]["B_field"]], [0.5, -0.5], atol=1e-12)
    assert {key: stops[key]["classification"] for key in stops} == {
        "aperture": "aperture", "field": "field", "vignette": "vignette",
    }


def test_ray_paths_end_at_the_first_blocking_stop_and_mark_it_red(study):
    panels = _by_id(study["ray_diagrams"])
    field_path = next(
        path for path in panels["field_stop"]["paths"]
        if path["field_height_mm"] == 2 and path["pupil_height_mm"] == pytest.approx(0)
    )
    assert field_path["first_blocked"] == {
        "z_mm": 200, "y_mm": pytest.approx(-2), "stop_id": "field", "color": "#ff4d4d",
    }
    assert field_path["z_mm"][-1] <= 200
    vignette_path = next(
        path for path in panels["vignette_stop"]["paths"]
        if path["field_height_mm"] == 2 and path["pupil_height_mm"] == pytest.approx(0.3)
    )
    assert vignette_path["first_blocked"]["stop_id"] == "vignette"
    assert vignette_path["first_blocked"]["z_mm"] == 150
    clear_path = next(
        path for path in panels["aperture_only"]["paths"]
        if path["field_height_mm"] == 0 and path["pupil_height_mm"] == pytest.approx(0)
    )
    assert clear_path["first_blocked"] is None
    assert clear_path["z_mm"][-1] == 240


def test_projected_vignette_circle_slides_with_field(study):
    maps = {item["field_height_mm"]: item for item in study["pupil_maps"]}
    for height, pupil_map in maps.items():
        circles = {item["stop_id"]: item for item in pupil_map["projected_stop_circles"]}
        assert circles["aperture"] == {
            "stop_id": "aperture", "center_x_mm": 0, "center_y_mm": pytest.approx(0),
            "radius_mm": pytest.approx(0.5),
        }
        assert circles["vignette"]["center_y_mm"] == pytest.approx(height)
        assert circles["vignette"]["radius_mm"] == pytest.approx(1.6)
    assert maps[0]["relative_pass"] == 1
    assert maps[2.05]["relative_pass"] < maps[1.8]["relative_pass"] < maps[1.4]["relative_pass"]


def test_sampling_is_deterministic_and_display_cap_does_not_change_metrics(study):
    again = calculate_stop_study()
    assert again["illumination"] == study["illumination"]
    assert again["pupil_maps"] == study["pupil_maps"]
    smaller = calculate_stop_study(replace(StopStudySpec(), display_pupil_count=17))
    assert [item["relative_pass"] for item in smaller["pupil_maps"]] == [
        item["relative_pass"] for item in study["pupil_maps"]
    ]
    assert all(item["display_sample_count"] == 17 for item in smaller["pupil_maps"])


def test_spec_strict_round_trip_detachment_and_immutability():
    spec = StopStudySpec()
    payload = json.loads(json.dumps(spec.to_dict(), allow_nan=False))
    restored = StopStudySpec.from_dict(payload)
    assert restored == spec
    payload["diagram_field_heights_mm"][0] = -99
    assert restored.diagram_field_heights_mm[0] == -2
    with pytest.raises(FrozenInstanceError):
        spec.seed = 2
    for mutation in (
        lambda data: data.update(extra=1),
        lambda data: data.pop("seed"),
        lambda data: data.update(schema_version=True),
    ):
        invalid = spec.to_dict()
        mutation(invalid)
        with pytest.raises(ValueError):
            StopStudySpec.from_dict(invalid)


@pytest.mark.parametrize("kwargs", [
    {"relay_distance_mm": 0}, {"focal_length_mm": 0}, {"pupil_sample_radius_mm": np.inf},
    {"aperture_stop_radius_mm": -1}, {"pupil_count": True}, {"pupil_count": 0},
    {"seed": -1}, {"display_pupil_count": 20_001}, {"ray_z_count": 1},
    {"diagram_field_heights_mm": (0, 0)},
    {"illumination_field_heights_mm": (-1, 1)},
    {"pupil_map_field_heights_mm": (1,)},
])
def test_spec_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        StopStudySpec(**kwargs)


def test_calculation_rejects_unvalidated_mapping():
    with pytest.raises(ValueError, match="StopStudySpec"):
        calculate_stop_study(StopStudySpec().to_dict())
