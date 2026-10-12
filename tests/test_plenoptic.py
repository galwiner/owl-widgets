"""Contracts for the unified plenoptic 1.0 / 2.0 camera model."""

import json
from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest
from numpy.testing import assert_allclose

from owl.lightfield import LightFieldLayer, _composite
from owl.plenoptic import PlenopticSpec, calculate_plenoptic, microlens_geometry


def _small(**changes) -> PlenopticSpec:
    return replace(
        PlenopticSpec(),
        lenslet_count=15, lenslet_sample_count=9, pixel_sample_count=1,
        patch_sweep_max=14, depth_baseline_count=2,
        **changes,
    )


@pytest.fixture(scope="module")
def study():
    return calculate_plenoptic(_small())


@pytest.fixture(scope="module")
def plenoptic_one():
    return calculate_plenoptic(_small(mode="plenoptic_1", microlens_offset_mm=0.0))


def test_result_is_finite_json_with_the_documented_sections(study):
    json.dumps(study, allow_nan=False)
    assert study["schema_version"] == 1
    assert set(study) == {
        "schema_version", "spec", "coordinates", "geometry", "raw_sensor",
        "sampling_tiles", "sub_aperture", "layers", "render", "depth",
    }
    assert study["coordinates"]["array_order"]["raw_sensor"] == "[lenslet,pixel]"


@pytest.mark.parametrize(
    ("mode", "offset", "sign"),
    [("plenoptic_1", 0.0, 1.0), ("keplerian", 3.0, 1.0), ("galilean", 3.0, -1.0)],
)
def test_every_mode_obeys_the_microlens_thin_lens_law(mode, offset, sign):
    geometry = microlens_geometry(
        mode, image_distance_mm=52.0, microlens_focal_length_mm=0.5,
        microlens_offset_mm=offset,
    )
    conjugate, gap = geometry["conjugate_a_mm"], geometry["gap_b_mm"]
    assert np.sign(conjugate) == sign
    assert gap > 0
    # 1/a + 1/b = 1/f must hold for the signed conjugate distance.
    assert_allclose(1.0 / conjugate + 1.0 / gap, 1.0 / 0.5, rtol=1e-12)
    assert_allclose(geometry["magnification"], gap / abs(conjugate))


def test_plenoptic_one_places_the_array_on_the_image_plane(plenoptic_one):
    geometry = plenoptic_one["geometry"]
    assert_allclose(geometry["array_z_mm"], geometry["image_distance_mm"])
    # Focusing each microlens on the aperture makes the conjugate the image distance.
    assert_allclose(geometry["conjugate_a_mm"], geometry["image_distance_mm"])


def test_plenoptic_one_reduces_to_one_rendered_pixel_per_microlens(plenoptic_one):
    # The microlens barely demagnifies the distant aperture, so the matched patch
    # collapses to a single pixel: the classic plenoptic 1.0 resolution penalty.
    assert plenoptic_one["geometry"]["matched_patch_pixels"] < 1.0
    assert plenoptic_one["render"]["matched_patch_pixels"] == 1
    spec = PlenopticSpec.from_dict(plenoptic_one["spec"])
    assert plenoptic_one["render"]["sweep"][0]["rendered_pixel_count"] == spec.lenslet_count


def test_focused_design_trades_angular_samples_for_spatial_samples(study, plenoptic_one):
    focused, unfocused = study["geometry"], plenoptic_one["geometry"]
    assert focused["spatial_samples_matched"] > unfocused["spatial_samples_matched"]
    assert focused["angular_samples_matched"] < unfocused["angular_samples_matched"]


@pytest.mark.parametrize("mode,offset", [("keplerian", 3.0), ("galilean", 3.0)])
def test_spatial_times_angular_samples_equals_the_pixel_count(mode, offset):
    geometry = calculate_plenoptic(_small(mode=mode, microlens_offset_mm=offset))["geometry"]
    product = geometry["spatial_samples_matched"] * geometry["angular_samples_matched"]
    assert_allclose(product, geometry["total_pixel_count"], rtol=1e-9)


def test_matched_patch_equals_the_microimage_disparity(study):
    geometry = study["geometry"]
    # Both quantities are pixels_per_lens * b / a, which is why one patch-size knob
    # serves as the refocus parameter and as the depth parameter.
    conjugate_row = next(
        row for row in study["layers"]
        if abs(row["conjugate_a_mm"] - geometry["conjugate_a_mm"]) < 1e-9
    )
    assert_allclose(conjugate_row["expected_shift_pixels"], geometry["matched_patch_pixels"])


def test_matched_pitch_makes_microimages_exactly_abut():
    spec = _small()
    geometry = calculate_plenoptic(spec)["geometry"]
    tuned = calculate_plenoptic(_small(microlens_pitch_mm=geometry["matched_pitch_mm"]))
    assert_allclose(tuned["geometry"]["microimage_fill_ratio"], 1.0, rtol=1e-9)


def test_raw_sensor_shape_and_pixel_pitch_follow_the_spec(study):
    spec = PlenopticSpec.from_dict(study["spec"])
    raw = np.array(study["raw_sensor"]["values"])
    assert raw.shape == (spec.lenslet_count, spec.pixels_per_lens)
    assert_allclose(spec.pixel_pitch_mm, spec.microlens_pitch_mm / spec.pixels_per_lens)
    assert raw.min() >= 0.0


def test_vignetting_darkens_microimage_edges_not_centres(study):
    fill = np.array(study["raw_sensor"]["aperture_fill"])
    middle = fill.shape[1] // 2
    # Rays needing the outside of the main aperture are blocked, so the edge of a
    # microimage collects fewer of them than its centre.
    assert fill[:, middle].mean() >= fill[:, 0].mean()
    assert fill[:, middle].mean() >= fill[:, -1].mean()
    assert fill.max() <= 1.0


def test_plenoptic_one_sampling_tiles_are_upright_in_ray_space(plenoptic_one, study):
    def tilt(result):
        u_corners = np.array(result["sampling_tiles"]["tile_u_mm"])
        s_corners = np.array(result["sampling_tiles"]["tile_s_mm"])
        return (np.ptp(u_corners, axis=-1).mean(), np.ptp(s_corners, axis=-1).mean())

    flat_u, flat_s = tilt(plenoptic_one)
    focused_u, focused_s = tilt(study)
    # A plenoptic 1.0 pixel fixes u and spans the microlens in s; the focused
    # design smears both, which is the sheared sampling that buys resolution.
    assert flat_u / flat_s < focused_u / focused_s


def test_sub_aperture_images_are_the_transpose_of_the_raw_sensor(study):
    raw = np.array(study["raw_sensor"]["values"])
    views = np.array(study["sub_aperture"]["images"])
    assert_allclose(views, raw.T)


def test_render_sweep_covers_every_patch_size_and_scales_resolution(study):
    spec = PlenopticSpec.from_dict(study["spec"])
    sweep = study["render"]["sweep"]
    assert [row["patch_pixels"] for row in sweep] == list(range(1, spec.patch_sweep_max + 1))
    for row in sweep:
        assert row["rendered_pixel_count"] == spec.lenslet_count * row["patch_pixels"]
        assert len(row["image"]) == row["rendered_pixel_count"]
        # A crop of mu' pixels tiles the plane at a' = d * b / mu'.
        expected = spec.microlens_pitch_mm * study["geometry"]["gap_b_mm"] / (
            row["patch_pixels"] * spec.pixel_pitch_mm
        )
        assert_allclose(row["conjugate_a_mm"], expected, rtol=1e-9)


def test_patch_rendering_seams_are_worst_for_plenoptic_one(study, plenoptic_one):
    def best(result):
        ratios = [row["seam_ratio"] for row in result["render"]["sweep"] if row["seam_ratio"]]
        return min(ratios)

    # Plenoptic 1.0 microimages are pictures of the aperture, not of scene patches,
    # so tiling crops of them can never join up.
    assert best(plenoptic_one) > 5.0 * best(study)


def test_depth_estimates_recover_the_layer_distances_where_confident():
    spec = PlenopticSpec()
    result = calculate_plenoptic(spec)
    truth = {row["label"]: row["object_distance_mm"] for row in result["layers"]}
    centers = np.array([row["center_mm"] for row in result["depth"]["estimates"]])
    _radiance, visible = _composite(
        np.zeros_like(centers), centers, layers=spec.layers,
        focal_length_mm=spec.focal_length_mm,
        image_distance_mm=spec.image_distance_mm, background=0.0,
    )
    errors = []
    for row, index in zip(result["depth"]["estimates"], visible):
        if not row["confident"] or index < 0 or row["object_distance_mm"] is None:
            continue
        expected = truth[spec.layers[index].label]
        errors.append(abs(row["object_distance_mm"] - expected) / expected)
    assert len(errors) >= 5
    assert float(np.median(errors)) < 0.15


def test_every_default_layer_stays_inside_the_microimage_depth_of_field(study):
    for row in study["layers"]:
        assert row["microlens_images_it"]
        assert row["disparity_resolvable"]
        # Blur below the texture cell is what lets correspondence work at all.
        assert row["microimage_detail_resolved"]


def test_a_layer_far_from_the_conjugate_plane_loses_microimage_detail():
    # Moving this layer well off the conjugate plane blurs its microimages past
    # their own texture, which is the focused camera's depth-of-field limit.
    near = LightFieldLayer(
        object_distance_mm=700.0, half_width_mm=400.0, period_mm=1.0, label="too near",
    )
    result = calculate_plenoptic(_small(layers=(near,)))
    row = result["layers"][0]
    assert row["microimage_blur_pixels"] > row["texture_cell_pixels"]
    assert not row["microimage_detail_resolved"]


def test_galilean_disparity_has_the_opposite_sign_to_keplerian():
    keplerian = calculate_plenoptic(_small(mode="keplerian", microlens_offset_mm=3.0))
    galilean = calculate_plenoptic(_small(mode="galilean", microlens_offset_mm=3.0))
    for left, right in zip(keplerian["layers"], galilean["layers"]):
        assert left["expected_shift_pixels"] > 0
        assert right["expected_shift_pixels"] < 0


def test_calculation_is_deterministic():
    spec = _small()
    assert calculate_plenoptic(spec) == calculate_plenoptic(spec)


def test_json_round_trip_is_detached_and_independent():
    spec = _small()
    restored = PlenopticSpec.from_dict(json.loads(json.dumps(spec.to_dict(), allow_nan=False)))
    assert restored == spec
    with pytest.raises(FrozenInstanceError):
        spec.lenslet_count = 5  # type: ignore[misc]


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": "lytro"},
        {"focal_length_mm": 0.0},
        {"microlens_pitch_mm": -0.1},
        {"image_distance_mm": 10.0},
        {"lenslet_count": 2},
        {"pixels_per_lens": 1},
        {"patch_sweep_max": 10_000},
        {"depth_min_overlap_pixels": 10_000},
        {"depth_shift_step_pixels": 0.0},
        {"layers": ()},
        # Keplerian needs the image plane beyond the microlens focal length.
        {"mode": "keplerian", "microlens_offset_mm": 0.25},
    ],
)
def test_spec_rejects_invalid_values(changes):
    with pytest.raises(ValueError):
        PlenopticSpec(**changes)


def test_calculate_requires_a_spec():
    with pytest.raises(ValueError):
        calculate_plenoptic({"schema_version": 1})  # type: ignore[arg-type]


def test_microlens_geometry_rejects_an_unknown_mode():
    with pytest.raises(ValueError):
        microlens_geometry(
            "unfocused", image_distance_mm=52.0,
            microlens_focal_length_mm=0.5, microlens_offset_mm=3.0,
        )


def test_from_dict_rejects_unknown_missing_and_mismatched_keys():
    data = _small().to_dict()
    with pytest.raises(ValueError):
        PlenopticSpec.from_dict({**data, "surprise": 1})
    with pytest.raises(ValueError):
        PlenopticSpec.from_dict({key: value for key, value in data.items() if key != "mode"})
    with pytest.raises(ValueError):
        PlenopticSpec.from_dict({**data, "schema_version": 2})
