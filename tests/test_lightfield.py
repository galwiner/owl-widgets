"""Contracts for the flatland light-field model."""

import json
from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest
from numpy.testing import assert_allclose

from owl.lightfield import (
    LightFieldLayer,
    LightFieldSpec,
    calculate_light_field,
    layer_beta,
    sample_radiance,
)


def _small(**changes) -> LightFieldSpec:
    return replace(
        LightFieldSpec(),
        u_count=33, s_count=129, view_count=3,
        refocus_count=21, integration_count=33,
        **changes,
    )


@pytest.fixture(scope="module")
def study():
    return calculate_light_field(_small())


def test_defaults_describe_a_three_layer_scene_at_one_focus_distance():
    spec = LightFieldSpec()
    assert_allclose(spec.focus_distance_mm, 1300.0)
    assert [layer.label for layer in spec.layers] == [
        "near texture", "focus target", "far backdrop"
    ]
    # The middle layer sits exactly on the focus distance, so beta is exactly 1.
    betas = [layer_beta(layer, spec.focal_length_mm, spec.image_distance_mm) for layer in spec.layers]
    assert betas[0] < 1.0 < betas[2]
    assert_allclose(betas[1], 1.0, atol=1e-12)


def test_result_is_finite_json_with_the_documented_sections(study):
    json.dumps(study, allow_nan=False)
    assert study["schema_version"] == 1
    assert set(study) == {
        "schema_version", "spec", "coordinates", "geometry",
        "ray_space", "layers", "sub_aperture", "refocus",
    }
    assert study["coordinates"]["array_order"]["ray_space_radiance"] == "[u,s]"


def test_ray_space_grid_matches_its_coordinates(study):
    spec = LightFieldSpec.from_dict(study["spec"])
    radiance = np.array(study["ray_space"]["radiance"])
    assert radiance.shape == (spec.u_count, spec.s_count)
    assert_allclose(study["ray_space"]["u_mm"][0], -spec.aperture_radius_mm)
    assert_allclose(study["ray_space"]["u_mm"][-1], spec.aperture_radius_mm)


@pytest.mark.parametrize("beta_case", ["in_focus", "out_of_focus"])
def test_a_layer_is_a_line_of_slope_one_minus_beta_in_ray_space(beta_case):
    # A single layer wide enough to fill the field isolates its ray-space slope.
    distance = 1300.0 if beta_case == "in_focus" else 900.0
    layer = LightFieldLayer(
        object_distance_mm=distance, half_width_mm=5000.0, period_mm=2.0,
        texture="bars", label="only",
    )
    spec = LightFieldSpec(layers=(layer,))
    beta = layer_beta(layer, spec.focal_length_mm, spec.image_distance_mm)
    u_values = np.array([-4.0, 0.0, 4.0])
    # Following s = s0 + u * (1 - beta) must hold the radiance constant.
    base = 0.37
    traced = sample_radiance(
        u_values, base + u_values * (1.0 - beta), layers=spec.layers,
        focal_length_mm=spec.focal_length_mm, image_distance_mm=spec.image_distance_mm,
    )
    assert_allclose(traced, traced[0], atol=1e-12)
    if beta_case == "in_focus":
        assert_allclose(beta, 1.0, atol=1e-12)


def test_occlusion_keeps_the_nearest_layer_and_hides_the_rest():
    front = LightFieldLayer(
        object_distance_mm=1000.0, half_width_mm=5000.0, period_mm=3.0,
        brightness=1.0, contrast_floor=0.999, texture="bars", label="front",
    )
    back = LightFieldLayer(
        object_distance_mm=3000.0, half_width_mm=5000.0, period_mm=3.0,
        brightness=0.2, contrast_floor=0.999, texture="bars", label="back",
    )
    both = sample_radiance(
        0.0, np.linspace(-2.0, 2.0, 21), layers=(front, back),
        focal_length_mm=50.0, image_distance_mm=52.0,
    )
    # The near layer covers the field everywhere, so the far layer never shows.
    assert_allclose(both, 1.0, atol=2e-3)


def test_rays_missing_every_layer_return_the_background():
    narrow = LightFieldLayer(
        object_distance_mm=1300.0, half_width_mm=0.5, center_mm=0.0, period_mm=0.2,
        label="speck",
    )
    values = sample_radiance(
        0.0, np.array([-2.5, 2.5]), layers=(narrow,),
        focal_length_mm=50.0, image_distance_mm=52.0, background=0.25,
    )
    assert_allclose(values, 0.25)


def test_refocus_recovers_each_layer_distance_from_its_visible_region(study):
    truth = {row["label"]: row["beta"] for row in study["layers"]}
    regions = study["refocus"]["regions"]
    assert len(regions) == len(truth)
    for region in regions:
        # Sharpness inside a layer's own region must peak at that layer's beta.
        assert abs(region["recovered_alpha"] - truth[region["label"]]) < 0.01
        assert region["visible_fraction"] > 0.05


def test_refocus_photos_are_shear_then_integrate(study):
    spec = LightFieldSpec.from_dict(study["spec"])
    photos = np.array(study["refocus"]["photos"])
    assert photos.shape == (spec.refocus_count, spec.s_count)
    alphas = np.array(study["refocus"]["alpha"])
    assert np.all(alphas > 0)
    # Integrating the aperture can never leave the radiance range of the scene.
    assert photos.min() >= 0.0
    assert photos.max() <= max(layer.brightness for layer in spec.layers) + 1e-12


def test_sub_aperture_views_shift_each_layer_by_its_disparity(study):
    spec = LightFieldSpec.from_dict(study["spec"])
    views = np.array(study["sub_aperture"]["images"])
    assert views.shape == (spec.view_count, spec.s_count)
    for row in study["layers"]:
        expected = (1.0 - row["beta"]) * 2.0 * spec.aperture_radius_mm
        assert_allclose(row["view_disparity_mm"], expected)


def test_json_round_trip_is_detached_and_independent():
    spec = _small()
    restored = LightFieldSpec.from_dict(json.loads(json.dumps(spec.to_dict(), allow_nan=False)))
    assert restored == spec
    assert restored.layers[0] is not None
    with pytest.raises(FrozenInstanceError):
        spec.u_count = 5  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        spec.layers[0].period_mm = 1.0  # type: ignore[misc]


def test_random_texture_is_deterministic_and_seed_dependent():
    x = np.linspace(-30.0, 30.0, 401)
    first = LightFieldLayer(period_mm=2.0, seed=7, texture="random")
    same = LightFieldLayer(period_mm=2.0, seed=7, texture="random")
    other = LightFieldLayer(period_mm=2.0, seed=8, texture="random")
    kwargs = {"focal_length_mm": 50.0, "image_distance_mm": 52.0}
    a = sample_radiance(0.0, x, layers=(first,), **kwargs)
    b = sample_radiance(0.0, x, layers=(same,), **kwargs)
    c = sample_radiance(0.0, x, layers=(other,), **kwargs)
    assert_allclose(a, b)
    assert not np.allclose(a, c)


def test_calculation_is_deterministic():
    spec = _small()
    assert calculate_light_field(spec) == calculate_light_field(spec)


@pytest.mark.parametrize(
    "changes",
    [
        {"focal_length_mm": 0.0},
        {"aperture_radius_mm": -1.0},
        {"image_distance_mm": 40.0},
        {"u_count": 2},
        {"view_count": 10_000},
        {"layers": ()},
        {"layers": ("not a layer",)},
        {"refocus_margin_ratio": 0.0},
        {"field_half_width_mm": float("nan")},
    ],
)
def test_spec_rejects_invalid_values(changes):
    with pytest.raises(ValueError):
        LightFieldSpec(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"object_distance_mm": -5.0},
        {"period_mm": 0.0},
        {"duty": 0.0},
        {"duty": 1.0},
        {"contrast_floor": 1.0},
        {"texture": "checkerboard"},
        {"seed": -1},
        {"label": "  "},
    ],
)
def test_layer_rejects_invalid_values(changes):
    with pytest.raises(ValueError):
        LightFieldLayer(**changes)


def test_a_layer_inside_the_focal_length_has_no_real_image():
    with pytest.raises(ValueError):
        LightFieldSpec(layers=(LightFieldLayer(object_distance_mm=30.0),))


def test_calculate_requires_a_spec():
    with pytest.raises(ValueError):
        calculate_light_field({"schema_version": 1})  # type: ignore[arg-type]


def test_from_dict_rejects_unknown_and_missing_keys():
    data = _small().to_dict()
    with pytest.raises(ValueError):
        LightFieldSpec.from_dict({**data, "surprise": 1})
    trimmed = {key: value for key, value in data.items() if key != "u_count"}
    with pytest.raises(ValueError):
        LightFieldSpec.from_dict(trimmed)
    with pytest.raises(ValueError):
        LightFieldSpec.from_dict({**data, "schema_version": 2})
