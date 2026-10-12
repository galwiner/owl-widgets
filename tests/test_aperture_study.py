import json
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from owl.aperture_study import ApertureStudySpec, calculate_aperture_study


@pytest.fixture(scope="module")
def study():
    return calculate_aperture_study(ApertureStudySpec(grid_size=128, ray_count=20_000, longitudinal_samples=120))


def _scenario(result, ratio):
    return next(item for item in result["scenarios"] if item["diameter_ratio"] == ratio)


def _comparison(result, ratio):
    return next(item for item in result["image_plane_comparison"]["scenarios"] if item["diameter_ratio"] == ratio)


def test_spec_defaults_are_original_and_frozen():
    spec = ApertureStudySpec()
    assert spec.waist_mm == 0.25
    assert spec.wavelength_nm == 1000
    assert spec.distance_mm == 100
    assert spec.focal_length_mm == 50
    assert spec.aperture_diameter_ratios == (None, 2.0, 1.0, 0.5)
    assert spec.grid_size == 256
    assert spec.window_mm == 8
    assert spec.longitudinal_samples == 180
    assert spec.ray_count == 100_000
    assert spec.seed == 0
    with pytest.raises(FrozenInstanceError):
        spec.grid_size = 64


@pytest.mark.parametrize("grid", [64, 128, 256, 512, 1024])
def test_supported_grid_sizes(grid):
    assert ApertureStudySpec(grid_size=grid).grid_size == grid


@pytest.mark.parametrize("grid", [32, 63, 65, 2048, 128.0, True])
def test_invalid_grid_sizes(grid):
    with pytest.raises(ValueError):
        ApertureStudySpec(grid_size=grid)


def test_schema_is_exact_finite_json_and_coordinates_are_explicit(study):
    assert set(study) == {
        "schema_version", "coordinates", "spec", "grids", "normalization",
        "gaussian_reference", "scenarios", "ray_fan", "image_plane_comparison",
    }
    assert set(study["grids"]) == {"x_mm", "z_mm", "image_histogram_edges_mm"}
    assert set(study["gaussian_reference"]) == {
        "rayleigh_range_mm", "lens_radius_mm", "radius_by_z_mm",
        "geometric_image_z_mm", "geometric_image_radius_mm", "true_waist_z_mm",
        "true_waist_radius_mm", "magnification",
    }
    assert set(study["scenarios"][0]) == {
        "diameter_ratio", "aperture_radius_mm", "analytic_transmission",
        "sampled_transmission", "fresnel_number", "brightest_z_mm",
        "focal_shift_mm", "peak_ratio", "longitudinal_intensity",
        "brightest_spot_intensity",
    }
    assert study["coordinates"]["array_order"]["longitudinal_intensity"] == "[x,z]"
    assert study["coordinates"]["array_order"]["spots_and_histograms"] == "[y,x]"
    encoded = json.dumps(study, allow_nan=False)
    assert json.loads(encoded) == study


def test_gaussian_reference_is_one_to_one_and_numerical_lens_radius(study):
    ref = study["gaussian_reference"]
    assert ref["magnification"] == pytest.approx(-1)
    assert ref["geometric_image_z_mm"] == pytest.approx(200)
    assert ref["geometric_image_radius_mm"] == pytest.approx(0.25, rel=1e-3)
    expected_lens_radius = 0.25 * np.sqrt(1 + (100 / (np.pi * 0.25**2 / 0.001)) ** 2)
    assert ref["lens_radius_mm"] == pytest.approx(expected_lens_radius, rel=1e-12)
    assert ref["true_waist_z_mm"] < 160
    assert ref["true_waist_radius_mm"] < ref["geometric_image_radius_mm"]


def test_throughput_and_focus_match_original_study(study):
    ref = study["gaussian_reference"]
    clear = _scenario(study, None)
    assert clear["analytic_transmission"] == clear["sampled_transmission"] == pytest.approx(1)
    assert clear["brightest_z_mm"] == pytest.approx(ref["true_waist_z_mm"], abs=2.5)
    for ratio in (2.0, 1.0, 0.5):
        scenario = _scenario(study, ratio)
        assert scenario["analytic_transmission"] == pytest.approx(1 - np.exp(-ratio**2 / 2))
        # At this deliberately practical 128 grid the smallest opening is only
        # about one pixel in radius; one-pixel feathering still tracks throughput.
        assert scenario["sampled_transmission"] == pytest.approx(scenario["analytic_transmission"], rel=0.25, abs=0.015)
        assert scenario["fresnel_number"] > 0
    assert _scenario(study, 0.5)["brightest_z_mm"] < clear["brightest_z_mm"]
    assert _scenario(study, 0.5)["peak_ratio"] < clear["peak_ratio"]


def test_deterministic_fan_images_and_stops_blocked_paths(study):
    fan = study["ray_fan"]
    assert len(fan["launch_heights_mm"]) == 5
    assert len(fan["launch_angles_rad"]) == 11
    clear = next(item for item in fan["scenarios"] if item["diameter_ratio"] is None)
    assert clear["passing_count"] == 55
    for path in clear["paths"]:
        assert path["blocked"] is False
        assert path["y_mm"][2] == pytest.approx(-path["launch_height_mm"], abs=1e-12)
        assert 0 <= path["color_scalar"] <= 1
    clipped = next(item for item in fan["scenarios"] if item["diameter_ratio"] == 0.5)
    assert 0 < clipped["passing_count"] < 55
    assert all(len(path["z_mm"]) == (2 if path["blocked"] else 4) for path in clipped["paths"])


def test_image_plane_controls_and_clipped_wave_differs_from_rays(study):
    expected = 1 - np.exp(-2)
    clear = _comparison(study, None)
    assert clear["passing_ray_count"] == 20_000
    assert clear["ray_encircled_incident_fraction"] == pytest.approx(expected, abs=0.02)
    assert clear["wave_encircled_incident_fraction"] == pytest.approx(expected, abs=0.03)
    assert np.max(clear["ray_histogram"]) == pytest.approx(1)
    assert np.max(clear["wave_intensity"]) == pytest.approx(1)

    clipped = _comparison(study, 0.5)
    assert clipped["passing_ray_count"] < clear["passing_ray_count"]
    assert clipped["ray_encircled_incident_fraction"] > clipped["wave_encircled_incident_fraction"]
    assert clipped["ray_encircled_incident_fraction"] / clipped["wave_encircled_incident_fraction"] > 1.5
    assert np.shape(clipped["wave_intensity"]) == (128, 128)
    assert np.shape(clipped["ray_histogram"])[0] == np.shape(clipped["ray_histogram"])[1]


def test_seed_makes_all_ray_outputs_deterministic():
    spec = ApertureStudySpec(
        aperture_diameter_ratios=(None, 0.5), grid_size=64,
        longitudinal_samples=16, ray_count=1_000, seed=7,
    )
    first = calculate_aperture_study(spec)
    second = calculate_aperture_study(spec)
    assert first["ray_fan"] == second["ray_fan"]
    assert first["image_plane_comparison"] == second["image_plane_comparison"]
