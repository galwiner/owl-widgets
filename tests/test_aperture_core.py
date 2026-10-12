import json
from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from numpy.testing import assert_allclose
from owl.core import (
    Aperture,
    FreeSpace,
    GaussianBeam,
    Interface,
    Mirror,
    OpticalSystem,
    RayTrace,
    ThickLens,
    ThinLens,
)
from owl.wave import cross_sections, longitudinal_section


def test_aperture_round_trip_and_identity():
    aperture = Aperture(2, 0.5, -1)
    assert aperture.to_dict() == {"type": "aperture", "radius_mm": 2, "x_mm": 0.5, "y_mm": -1}
    assert_allclose(aperture.matrix(), np.eye(2))
    with pytest.raises(FrozenInstanceError):
        aperture.radius_mm = 1
    system = OpticalSystem((FreeSpace(10), aperture, ThinLens(20)))
    data = json.loads(json.dumps(system.to_dict(), allow_nan=False))
    assert OpticalSystem.from_dict(data) == system
    assert Aperture.from_dict(aperture.to_dict()) == aperture
    assert Aperture(1).x_mm == Aperture(1).y_mm == 0
    assert_allclose(system.matrix(), ThinLens(20).matrix() @ FreeSpace(10).matrix())


@pytest.mark.parametrize("value", [None, True, np.bool_(False), "1", 1j, np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("field", ["radius_mm", "x_mm", "y_mm"])
def test_aperture_invalid_numbers(field, value):
    data = {"radius_mm": 1, "x_mm": 0, "y_mm": 0, field: value}
    with pytest.raises(ValueError):
        Aperture(**data)


@pytest.mark.parametrize("radius", [0, -1])
def test_aperture_invalid_radius(radius):
    with pytest.raises(ValueError):
        Aperture(radius)


@pytest.mark.parametrize("data", [
    None, {}, {"type": "aperture", "radius_mm": 1},
    {"type": "other", "radius_mm": 1, "x_mm": 0, "y_mm": 0},
    {"type": "aperture", "radius_mm": 1, "x_mm": 0, "y_mm": 0, "extra": 0},
    {"type": "aperture", "radius_mm": None, "x_mm": 0, "y_mm": 0},
    {"type": "aperture", "radius_mm": 1, "x_mm": 0},
    {"type": "aperture", "radius_mm": 1, "y_mm": 0},
])
def test_aperture_strict_schema(data):
    with pytest.raises(ValueError):
        Aperture.from_dict(data)
    with pytest.raises(ValueError):
        OpticalSystem.from_dict({"schema_version": 1, "elements": [data]})


def test_meridional_clipping_is_monotone_and_keeps_geometry():
    system = OpticalSystem((Aperture(1, 0.6, 0), FreeSpace(2), Aperture(0.5), FreeSpace(3)))
    incoming = np.array([[0, 0.8, 1, 2], [0, -0.4, -0.5, -1]])
    trace = system.trace(incoming)
    assert trace.alive.dtype == np.bool_
    assert trace.alive.shape == (5, 4)
    assert_allclose(trace.alive, [[1, 1, 1, 1], [1, 1, 0, 0], [1, 1, 0, 0], [1, 1, 0, 0], [1, 1, 0, 0]])
    assert np.isfinite(trace.rays).all()
    assert_allclose(trace.rays[-1], system.matrix() @ incoming)
    with pytest.raises(ValueError):
        trace.alive.setflags(write=True)
    assert not OpticalSystem((Aperture(1, 2),)).trace([[0], [0]]).alive[-1, 0]
    assert OpticalSystem((Aperture(1, 0, 2),)).trace([[2], [0]]).alive[-1, 0]
    assert OpticalSystem().trace(np.empty((2, 0))).alive.shape == (1, 0)


def test_later_aperture_removes_additional_rays():
    system = OpticalSystem((Aperture(1), FreeSpace(1), Aperture(0.5), Aperture(2)))
    trace = system.trace([[0, 0.75, 1.5], [0, 0, 0]])
    assert_allclose(trace.alive, [[1, 1, 1], [1, 1, 0], [1, 1, 0], [1, 0, 0], [1, 0, 0]])


def test_alive_defaults_validation_and_copy():
    rays = np.zeros((2, 2, 3))
    assert RayTrace([0, 1], rays).alive.all()
    alive = np.ones((2, 3), dtype=bool)
    trace = RayTrace([0, 1], rays, alive=alive)
    alive[:] = False
    assert trace.alive.all()
    for invalid in (np.ones((2, 3)), np.ones((2, 2), dtype=bool), [[True]], [[np.nan]]):
        with pytest.raises(ValueError):
            RayTrace([0, 1], rays, alive=invalid)


def test_gaussian_is_unclipped_reference():
    beam = GaussianBeam(0.1, 500)
    clear = OpticalSystem((FreeSpace(10), ThinLens(40), FreeSpace(20)))
    clipped = OpticalSystem((Aperture(0.001),) + clear.elements)
    expected, actual = clear.gaussian(beam), clipped.gaussian(beam)
    assert_allclose(actual.radius_mm[1:], expected.radius_mm)
    assert_allclose(actual.q_mm[1:], expected.q_mm)
    assert_allclose(actual.z_mm[1:], expected.z_mm)


def test_centered_aperture_analytic_throughput_and_binary_mask():
    beam = GaussianBeam(0.2, 532)
    radius = 0.15
    result = cross_sections(OpticalSystem((Aperture(radius),)), beam, grid_size=512, window_mm=1.2)
    x = np.array(result["x_mm"])
    assert x[256] == 0
    assert_allclose(np.diff(x), 1.2 / 512)
    before, after = [np.array(p["intensity"]) for p in result["planes"]]
    mask = np.hypot(x[:, None], x[None, :]) <= radius
    assert_allclose(after, before * mask, atol=0)
    assert result["planes"][1]["transmission"] == pytest.approx(1 - np.exp(-2 * radius**2 / beam.waist_mm**2), abs=0.002)
    assert before.max() == 1
    json.dumps(result, allow_nan=False)


def test_multiple_offset_apertures_intersect_without_renormalizing():
    beam = GaussianBeam(0.2, 500)
    apertures = (Aperture(0.18, 0.04, -0.03), Aperture(0.12, -0.04, 0.05), Aperture(0.12, -0.04, 0.05))
    result = cross_sections(OpticalSystem(apertures), beam, grid_size=256, window_mm=1.2)
    x = np.array(result["x_mm"])
    xx, yy = np.meshgrid(x, x)
    expected = np.array(result["planes"][0]["intensity"])
    input_power = expected.sum()
    previous = 1
    for aperture, plane in zip(apertures, result["planes"][1:]):
        expected *= np.hypot(xx - aperture.x_mm, yy - aperture.y_mm) <= aperture.radius_mm
        assert_allclose(plane["intensity"], expected)
        assert plane["transmission"] == pytest.approx(expected.sum() / input_power)
        assert plane["transmission"] <= previous
        previous = plane["transmission"]


@pytest.mark.parametrize("elements", [
    (), (FreeSpace(100),), (ThinLens(40), FreeSpace(35)),
    (ThinLens(-40), FreeSpace(35)),
    (FreeSpace(15), Mirror(80), FreeSpace(35)),
    (FreeSpace(15), Mirror(), FreeSpace(35), Mirror(), FreeSpace(10)),
    (Interface(np.inf, 1, 1.5), FreeSpace(100)),
    (Interface(np.inf, 1, 1.5), ThinLens(40), FreeSpace(35)),
    (Interface(np.inf, 1, 1.5), Mirror(80), FreeSpace(35)),
    (Interface(30, 1, 1.5), FreeSpace(35), Interface(-40, 1.5, 1), FreeSpace(20)),
    (ThickLens(30, -40, 8, 1.5), FreeSpace(30)),
    (Mirror(), ThickLens(30, -40, 8, 1.5), FreeSpace(30)),
])
def test_untruncated_wave_matches_gaussian_at_every_original_exit(elements):
    beam = GaussianBeam(0.1, 532)
    system = OpticalSystem(elements)
    result = cross_sections(system, beam, grid_size=256)
    assert len(result["planes"]) == len(elements) + 1
    x = np.array(result["x_mm"])
    r2 = x[:, None] ** 2 + x[None, :] ** 2
    for index, plane in enumerate(result["planes"]):
        prefix = OpticalSystem(elements[:index])
        radius = prefix.gaussian(beam).radius_mm[-1]
        expected = (beam.waist_mm / radius) ** 2 * np.exp(-2 * r2 / radius**2)
        assert_allclose(plane["intensity"], expected, atol=2e-6, rtol=2e-4)
        assert plane["transmission"] == pytest.approx(1, abs=1e-12)
        assert plane["z_mm"] == prefix.output_z_mm
    assert result["planes"][0]["label"] == "input"
    json.dumps(result, allow_nan=False)


def test_thick_lens_matches_explicit_expansion():
    beam = GaussianBeam(0.1, 500)
    lens = ThickLens(30, -40, 8, 1.5)
    prefix = (Aperture(0.08, 0.01), Mirror())
    actual = cross_sections(OpticalSystem(prefix + (lens,)), beam, grid_size=128, window_mm=0.8)
    expected = cross_sections(OpticalSystem(prefix + (Interface(30, 1, 1.5), FreeSpace(8), Interface(-40, 1.5, 1))), beam, grid_size=128, window_mm=0.8)
    assert len(actual["planes"]) == 4
    assert actual["planes"][-1]["label"] == "3: thick_lens"
    assert actual["planes"][-1]["z_mm"] == -8
    assert_allclose(actual["planes"][-1]["intensity"], expected["planes"][-1]["intensity"])


def test_diffraction_conserves_remaining_power_not_peak():
    result = cross_sections(OpticalSystem((Aperture(0.08), FreeSpace(20), Aperture(0.08), FreeSpace(20))), GaussianBeam(0.1, 500), grid_size=256)
    powers = [p["transmission"] for p in result["planes"]]
    assert powers[0] == 1
    assert 0 < powers[3] < powers[1] < 1
    assert_allclose([powers[2], powers[4]], [powers[1], powers[3]], atol=1e-14)
    assert not np.allclose(result["planes"][1]["intensity"], result["planes"][2]["intensity"])


@pytest.mark.parametrize("grid", [0, 32, 63, 65, 127, 1024, 128.0, True, "128", None])
def test_invalid_wave_grid(grid):
    with pytest.raises(ValueError):
        cross_sections(OpticalSystem(), GaussianBeam(0.1, 500), grid_size=grid)


@pytest.mark.parametrize("window", [0, -1, np.nan, np.inf, True, "1", 1j])
def test_invalid_wave_window(window):
    with pytest.raises(ValueError):
        cross_sections(OpticalSystem(), GaussianBeam(0.1, 500), window_mm=window)


def test_window_sampling_warnings_and_zero_transmission():
    beam = GaussianBeam(0.1, 500)
    auto = cross_sections(OpticalSystem((Aperture(0.1, 2, -3),)), beam, grid_size=64)
    assert auto["window_mm"] >= 2 * 3.1
    assert any("Sampling" in w for w in auto["warnings"])
    edge = cross_sections(OpticalSystem(), beam, window_mm=0.1, grid_size=64)
    assert any("edge" in w for w in edge["warnings"])
    blocked = cross_sections(OpticalSystem((Aperture(0.01, 2), FreeSpace(10))), beam, window_mm=0.6)
    assert blocked["planes"][-1]["transmission"] == 0
    assert np.count_nonzero(blocked["planes"][-1]["intensity"]) == 0
    json.dumps(blocked, allow_nan=False)


@pytest.mark.parametrize("grid", [64, 128, 256, 512, np.int64(64)])
def test_supported_grids(grid):
    result = cross_sections(OpticalSystem(), GaussianBeam(0.1, 500), grid_size=grid)
    assert np.shape(result["planes"][0]["intensity"]) == (grid, grid)
    assert result["planes"][0]["transmission"] == 1


def test_phase_sampling_warning():
    result = cross_sections(OpticalSystem((ThinLens(0.01),)), GaussianBeam(0.1, 500), grid_size=64)
    assert any("quadratic" in warning for warning in result["warnings"])
    json.dumps(result, allow_nan=False)


def test_wave_argument_types_and_extreme_range():
    beam = GaussianBeam(0.1, 500)
    for system, incoming in ((None, beam), (OpticalSystem(), None)):
        with pytest.raises(ValueError):
            cross_sections(system, incoming)
    with pytest.raises(ValueError):
        cross_sections(OpticalSystem(), beam, window_mm=1e308)


@pytest.mark.parametrize("samples", [3, 201, 4.0, True, "4", None])
def test_longitudinal_rejects_invalid_samples_per_gap(samples):
    with pytest.raises(ValueError):
        longitudinal_section(OpticalSystem(), GaussianBeam(0.1, 500), samples_per_gap=samples)


def test_longitudinal_aperture_is_immediate_and_diffraction_is_not_gaussian():
    beam = GaussianBeam(0.1, 500)
    radius = 0.06
    clipped = longitudinal_section(
        OpticalSystem((Aperture(radius), FreeSpace(20))), beam,
        grid_size=256, window_mm=0.8, samples_per_gap=8,
    )
    clear = longitudinal_section(
        OpticalSystem((FreeSpace(20),)), beam,
        grid_size=256, window_mm=0.8, samples_per_gap=8,
    )
    x = np.array(clipped["x_mm"])
    rows = np.array(clipped["intensity"])
    assert len(rows) == 10  # input + aperture surface + eight gap intervals
    assert clipped["z_mm"][:2] == [0, 0]
    assert clipped["path_mm"][:2] == [0, 0]
    assert np.count_nonzero(rows[1, np.abs(x) > radius]) == 0
    assert not np.allclose(rows[-1], np.array(clear["intensity"])[-1], rtol=0.03, atol=1e-4)
    json.dumps(clipped, allow_nan=False)


def test_longitudinal_clear_gap_matches_analytic_gaussian_slices():
    beam = GaussianBeam(0.1, 532)
    result = longitudinal_section(
        OpticalSystem((FreeSpace(40),)), beam,
        grid_size=256, window_mm=1.2, samples_per_gap=8,
    )
    x = np.array(result["x_mm"])
    for z, row in zip(result["path_mm"], result["intensity"]):
        radius = beam.waist_mm * np.sqrt(1 + (z / beam.rayleigh_range_mm) ** 2)
        expected = (beam.waist_mm / radius) ** 2 * np.exp(-2 * x**2 / radius**2)
        assert_allclose(row, expected, atol=2e-6, rtol=3e-4)


def test_longitudinal_lens_aperture_changes_focus_and_tracks_direction_and_glass():
    beam = GaussianBeam(0.12, 532)
    clear_system = OpticalSystem((ThinLens(30), FreeSpace(30)))
    clipped_system = OpticalSystem((Aperture(0.07), ThinLens(30), FreeSpace(30)))
    clear = longitudinal_section(clear_system, beam, grid_size=256, window_mm=1.2, samples_per_gap=12)
    clipped = longitudinal_section(clipped_system, beam, grid_size=256, window_mm=1.2, samples_per_gap=12)
    assert not np.allclose(clipped["intensity"][-1], clear["intensity"][-1], rtol=0.05, atol=1e-4)

    folded = longitudinal_section(
        OpticalSystem((Mirror(), FreeSpace(6), ThickLens(30, -40, 4, 1.5))), beam,
        grid_size=128, window_mm=1.2, samples_per_gap=4,
    )
    assert folded["z_mm"][-1] == -10
    assert folded["path_mm"][-1] == 10
    assert len(folded["intensity"]) == 1 + 1 + 4 + 1 + 4 + 1
    assert {marker["type"] for marker in folded["elements"]} >= {"mirror", "thick_lens"}
    json.dumps(folded, allow_nan=False)
