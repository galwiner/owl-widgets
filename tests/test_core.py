import json
from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from numpy.testing import assert_allclose
from owl.core import Interface, Mirror, ThickLens
from owl import (
    FreeSpace,
    GaussianBeam,
    GaussianTrace,
    OpticalSystem,
    RayTrace,
    ThinLens,
)


def test_free_space_analytical():
    system = OpticalSystem((FreeSpace(100),))
    rays = np.array([[1, -2], [0.01, -0.02]])
    result = system.trace(rays)
    assert isinstance(result, RayTrace)
    assert_allclose(result.z_mm, [0, 100])
    assert_allclose(result.rays[-1], [[2, -4], [0.01, -0.02]])
    assert_allclose(rays, [[1, -2], [0.01, -0.02]])
    beam = GaussianBeam(0.1, 500)
    trace = system.gaussian(beam)
    assert isinstance(trace, GaussianTrace)
    assert trace.z_mm.size == 81
    assert_allclose(trace.q_mm, trace.z_mm + 1j * beam.rayleigh_range_mm)
    assert_allclose(trace.radius_mm, beam.waist_mm * np.sqrt(1 + (trace.z_mm / beam.rayleigh_range_mm) ** 2))
    assert system.length_mm == 100


def test_two_f_imaging_and_four_f_relay():
    f = 50
    imaging = OpticalSystem((FreeSpace(2*f), ThinLens(f), FreeSpace(2*f)))
    assert_allclose(imaging.matrix(), [[-1, 0], [-1/f, -1]], atol=1e-14)
    relay = OpticalSystem((FreeSpace(f), ThinLens(f), FreeSpace(2*f), ThinLens(f), FreeSpace(f)))
    assert_allclose(relay.matrix(), -np.eye(2), atol=1e-14)
    rays = np.array([[1, 2], [0.01, -0.01]])
    assert_allclose(relay.trace(rays).rays[-1], -rays)


def test_lens_waist_and_interfaces():
    beam = GaussianBeam(0.1, 500)
    f = 40
    zr = beam.rayleigh_range_mm
    waist_z = f * zr**2 / (f**2 + zr**2)
    system = OpticalSystem((ThinLens(f), FreeSpace(waist_z)))
    trace = system.gaussian(beam, samples_per_gap=4)
    assert_allclose(trace.z_mm[:2], [0, 0])
    assert_allclose(trace.radius_mm[:2], [beam.waist_mm, beam.waist_mm])
    assert_allclose(trace.q_mm[1], beam.q_mm / (1 - beam.q_mm / f))
    assert_allclose(trace.q_mm[-1].real, 0, atol=1e-14)
    assert_allclose(trace.radius_mm[-1], beam.waist_mm * f / np.sqrt(f*f + zr*zr))
    assert_allclose(system.trace([[1], [0]]).z_mm, [0, 0, waist_z])


def test_determinant_and_q_abcd_law():
    system = OpticalSystem((FreeSpace(15), ThinLens(-30), FreeSpace(70), ThinLens(100), FreeSpace(2)))
    matrix = system.matrix()
    assert_allclose(np.linalg.det(matrix), 1)
    beam = GaussianBeam(0.2, 1064)
    a, b, c, d = matrix.ravel()
    assert_allclose(system.gaussian(beam).q_mm[-1], (a*beam.q_mm+b)/(c*beam.q_mm+d))
    rays = np.array([[1, 2, 3], [0.1, 0.2, 0.3]])
    assert_allclose(system.trace(rays).rays[-1], matrix @ rays)


def test_empty_and_zero_length_systems():
    system = OpticalSystem()
    assert_allclose(system.matrix(), np.eye(2))
    assert system.length_mm == 0
    assert system.trace(np.empty((2, 0))).rays.shape == (1, 2, 0)
    beam = GaussianBeam(1, 500)
    assert_allclose(system.gaussian(beam).radius_mm, [1])
    zero = OpticalSystem((FreeSpace(0), ThinLens(-10), ThinLens(20)))
    assert_allclose(zero.gaussian(beam).z_mm, [0, 0, 0, 0])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "2", 1j, None])
def test_nonfinite_and_nonreal_parameters(value):
    for construct in (FreeSpace, ThinLens, lambda x: GaussianBeam(x, 500), lambda x: GaussianBeam(1, x)):
        with pytest.raises(ValueError):
            construct(value)


@pytest.mark.parametrize("construct", [lambda: FreeSpace(-1), lambda: ThinLens(0), lambda: GaussianBeam(0, 500), lambda: GaussianBeam(1, -1), lambda: OpticalSystem([]), lambda: OpticalSystem((object(),))])
def test_invalid_parameters(construct):
    with pytest.raises(ValueError):
        construct()


@pytest.mark.parametrize("rays", [[1, 2], [[1, 2]], [[1], [float("nan")]], [[1j], [0]], [[True], [False]], [["1"], ["0"]]])
def test_invalid_rays(rays):
    with pytest.raises(ValueError):
        OpticalSystem().trace(rays)


@pytest.mark.parametrize("samples", [0, -1, 1.5, True, "80"])
def test_invalid_sampling(samples):
    with pytest.raises(ValueError):
        OpticalSystem().gaussian(GaussianBeam(1, 500), samples)


def test_immutable_inputs_and_outputs():
    space = FreeSpace(10)
    with pytest.raises(FrozenInstanceError):
        space.distance_mm = 2
    system = OpticalSystem((space,))
    ray_trace = system.trace([[1], [0]])
    gaussian = system.gaussian(GaussianBeam(1, 500))
    for array in (ray_trace.z_mm, ray_trace.rays, gaussian.z_mm, gaussian.radius_mm, gaussian.q_mm):
        with pytest.raises(ValueError):
            array.flat[0] = 2
        with pytest.raises(ValueError):
            array.setflags(write=True)


def test_serialization_round_trip():
    system = OpticalSystem((FreeSpace(10), ThinLens(-20), FreeSpace(0)))
    data = json.loads(json.dumps(system.to_dict(), allow_nan=False))
    assert data == {"schema_version": 1, "elements": [{"type": "free_space", "distance_mm": 10}, {"type": "thin_lens", "focal_length_mm": -20}, {"type": "free_space", "distance_mm": 0}]}
    assert OpticalSystem.from_dict(data) == system
    beam = GaussianBeam(0.3, 532)
    assert GaussianBeam.from_dict(json.loads(json.dumps(beam.to_dict()))) == beam
    for element in system.elements:
        assert type(element).from_dict(element.to_dict()) == element


@pytest.mark.parametrize("data", [None, {}, {"schema_version": 2, "elements": []}, {"schema_version": True, "elements": []}, {"schema_version": 1.0, "elements": []}, {"schema_version": 1, "elements": [], "extra": 0}, {"schema_version": 1, "elements": ()}, {"schema_version": 1, "elements": [None]}, {"schema_version": 1, "elements": [{"type": "mirror"}]}, {"schema_version": 1, "elements": [{"type": "free_space"}]}, {"schema_version": 1, "elements": [{"type": "thin_lens", "focal_length_mm": 5, "extra": 0}]}])
def test_strict_system_schema(data):
    with pytest.raises(ValueError):
        OpticalSystem.from_dict(data)


def test_strict_beam_and_element_schema():
    with pytest.raises(ValueError):
        GaussianBeam.from_dict({"schema_version": 1, "waist_mm": 1, "wavelength_nm": 500, "extra": 0})
    with pytest.raises(ValueError):
        FreeSpace.from_dict({"type": "lens", "distance_mm": 10})
    with pytest.raises(ValueError):
        ThinLens.from_dict({"type": "space", "focal_length_mm": 10})


@pytest.mark.parametrize("radius", [np.inf, -np.inf])
def test_plane_surfaces_and_json(radius):
    interface = Interface(radius, 1, 1.5)
    assert_allclose(interface.matrix(), [[1, 0], [0, 2/3]])
    assert_allclose(Mirror(radius).matrix(), np.eye(2))
    assert_allclose(Mirror().matrix(), np.eye(2))
    slab = ThickLens(radius, radius, 9, 1.5)
    assert_allclose(slab.matrix(), [[1, 6], [0, 1]])
    system = OpticalSystem((slab, Mirror(radius), interface))
    data = json.loads(json.dumps(system.to_dict(), allow_nan=False))
    assert data["elements"][0]["radius1_mm"] is None
    assert data["elements"][0]["radius2_mm"] is None
    assert data["elements"][1]["radius_mm"] is None
    assert data["elements"][2]["radius_mm"] is None
    restored = OpticalSystem.from_dict(data)
    assert restored.elements[0].radius1_mm == np.inf
    assert restored.elements[1].radius_mm == np.inf
    assert_allclose(restored.matrix(), system.matrix())
    for element in restored.elements:
        assert type(element).from_dict(element.to_dict()) == element


@pytest.mark.parametrize("radius", [30, -30])
def test_curved_surface_math_and_beam_continuity(radius):
    interface = Interface(radius, 1, 1.5)
    assert_allclose(interface.matrix(), [[1, 0], [-0.5 / (1.5 * radius), 2/3]])
    assert_allclose(np.linalg.det(interface.matrix()), 2/3)
    assert_allclose(Mirror(radius).matrix(), ThinLens(radius / 2).matrix())
    system = OpticalSystem((FreeSpace(12), interface, FreeSpace(5), Mirror(radius)))
    beam = GaussianBeam(0.1, 532)
    trace = system.gaussian(beam, 2)
    assert_allclose(trace.radius_mm[2], trace.radius_mm[3])
    assert_allclose(trace.radius_mm[-2], trace.radius_mm[-1])
    assert_allclose(trace.radius_mm**2, -(beam.wavelength_mm / trace.n) / (np.pi * np.imag(1 / trace.q_mm)))
    a, b, c, d = system.matrix().ravel()
    assert_allclose(trace.q_mm[-1], (a * beam.q_mm + b) / (c * beam.q_mm + d))
    assert system.output_n == 1.5


@pytest.mark.parametrize("mirrors", [1, 2, 3])
def test_reflections_only_reverse_z(mirrors):
    elements = (FreeSpace(5),) + (Mirror(), FreeSpace(10)) * mirrors
    system = OpticalSystem(elements)
    expected_z = [0, 5]
    direction = 1
    for _ in range(mirrors):
        direction *= -1
        expected_z.extend([expected_z[-1], expected_z[-1] + direction * 10])
    rays = system.trace([[1], [0.02]])
    beam = GaussianBeam(0.1, 500)
    gaussian = system.gaussian(beam, 1)
    assert_allclose(rays.z_mm, expected_z)
    assert_allclose(gaussian.z_mm, expected_z)
    assert_allclose(rays.s, gaussian.s)
    assert_allclose(rays.rays[-1, :, 0], [1 + 0.02 * system.length_mm, 0.02])
    assert_allclose(gaussian.q_mm[-1], beam.q_mm + system.length_mm)
    assert system.length_mm == 5 + 10 * mirrors
    assert system.output_z_mm == expected_z[-1]
    assert system.output_direction == direction
    assert system.output_n == 1


def test_reverse_interfaces_are_explicit_encounters():
    system = OpticalSystem((
        Interface(40, 1, 1.5), FreeSpace(3), Interface(-60, 1.5, 1),
        Mirror(), Interface(60, 1, 1.5), FreeSpace(3), Interface(-40, 1.5, 1),
    ))
    rays = np.array([[1], [0.01]])
    assert_allclose(system.trace(rays).rays[-1], system.matrix() @ rays)
    assert system.output_z_mm == 0
    assert system.length_mm == 6
    assert_allclose(system.trace(rays).n, [1, 1.5, 1.5, 1, 1, 1.5, 1.5, 1])


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("thickness", [0, 8])
def test_thick_lens_expanded_traces(thickness, reverse):
    lens = ThickLens(40, -60, thickness, 1.5)
    prefix = (Mirror(),) if reverse else ()
    system = OpticalSystem(prefix + (lens,))
    composed = OpticalSystem(prefix + (Interface(40, 1, 1.5), FreeSpace(thickness), Interface(-60, 1.5, 1)))
    assert_allclose(system.matrix(), composed.matrix())
    rays = np.array([[1, -2], [0.01, -0.02]])
    actual, expected = system.trace(rays), composed.trace(rays)
    for name in ("z_mm", "rays", "n", "s"):
        assert_allclose(getattr(actual, name), getattr(expected, name))
    assert_allclose(actual.rays[-1], system.matrix() @ rays)
    assert_allclose(actual.rays[-2], FreeSpace(thickness).matrix() @ actual.rays[-3])
    assert_allclose(actual.n[-3:], [1.5, 1.5, 1])
    assert_allclose(actual.z_mm[-3:], [0, -thickness if reverse else thickness, -thickness if reverse else thickness])
    beam = GaussianBeam(0.1, 532)
    actual, expected = system.gaussian(beam, 4), composed.gaussian(beam, 4)
    for name in ("z_mm", "q_mm", "radius_mm", "n", "s"):
        assert_allclose(getattr(actual, name), getattr(expected, name))
    start = 2 if reverse else 1
    count = 4 if thickness else 1
    assert len(actual.z_mm) == start + count + 2
    assert_allclose(actual.q_mm[start:start + count + 1], actual.q_mm[start] + (np.linspace(0, thickness, 5) if thickness else [0, 0]))
    assert_allclose(actual.radius_mm[start - 1], actual.radius_mm[start])
    assert_allclose(actual.radius_mm[-2], actual.radius_mm[-1])
    assert system.output_z_mm == actual.z_mm[-1]


def test_thick_lens_limits():
    assert_allclose(ThickLens(20, -30, 7, 1).matrix(), FreeSpace(7).matrix())
    power = (1.5 - 1) * (1/20 - 1/-30)
    assert_allclose(ThickLens(20, -30, 0, 1.5).matrix(), ThinLens(1 / power).matrix())
    assert_allclose(Interface(20, 1, 1).matrix(), np.eye(2))


@pytest.mark.parametrize("value", [0, -0.0, np.nan, True, np.bool_(False), "inf", None, 1j])
def test_invalid_surface_radii(value):
    for construct in (Mirror, lambda r: Interface(r, 1, 1.5), lambda r: ThickLens(r, 20, 1, 1.5), lambda r: ThickLens(20, r, 1, 1.5)):
        with pytest.raises(ValueError):
            construct(value)


@pytest.mark.parametrize("value", [0, -1, np.inf, np.nan, True, "1.5", None, 1j])
def test_invalid_indices(value):
    for construct in (lambda: Interface(20, value, 1), lambda: Interface(20, 1, value), lambda: ThickLens(20, -20, 1, value)):
        with pytest.raises(ValueError):
            construct()


@pytest.mark.parametrize("value", [-1, np.inf, np.nan, True, None])
def test_invalid_thickness(value):
    with pytest.raises(ValueError):
        ThickLens(20, -20, value, 1.5)


@pytest.mark.parametrize("elements", [
    (Interface(np.inf, 1.5, 1),),
    (Interface(20, 1, 1.5), Interface(-20, 1.4, 1)),
    (Interface(20, 1, 1.5), ThickLens(20, -20, 1, 1.5)),
    (Interface(20, 1, 1.000001), ThickLens(20, -20, 1, 1.5)),
    (Interface(20, 1, 1.5), Mirror(), Interface(-20, 1, 1.5)),
])
def test_invalid_ambient_chain(elements):
    with pytest.raises(ValueError, match="ambient"):
        OpticalSystem(elements)
    with pytest.raises(ValueError, match="ambient"):
        OpticalSystem.from_dict({"schema_version": 1, "elements": [e.to_dict() for e in elements]})


def test_index_chain_tight_tolerance():
    assert OpticalSystem((Interface(20, 1 + 1e-13, 1.5),)).output_n == 1.5
    with pytest.raises(ValueError):
        OpticalSystem((Interface(20, 1 + 1e-8, 1.5),))


@pytest.mark.parametrize("element", [Interface(20, 1, 1.5), Mirror(30), ThickLens(20, -30, 4, 1.5)])
def test_new_element_strict_schema(element):
    data = element.to_dict()
    assert type(element).from_dict(data) == element
    for key in data:
        missing = dict(data)
        del missing[key]
        with pytest.raises(ValueError):
            type(element).from_dict(missing)
    for invalid in (None, {**data, "extra": 0}, {**data, "type": "wrong"}, {**data, "type": None}):
        with pytest.raises(ValueError):
            type(element).from_dict(invalid)


@pytest.mark.parametrize("kind", ["ray", "gaussian"])
def test_trace_backward_constructor_defaults(kind):
    trace = RayTrace([0], [[[1], [0]]]) if kind == "ray" else GaussianTrace([0], [1], [1j])
    assert_allclose(trace.n, [1])
    assert_allclose(trace.s, [1])
    for array in (trace.n, trace.s):
        with pytest.raises(ValueError):
            array.setflags(write=True)


@pytest.mark.parametrize("name,value", [
    ("n", [0]), ("n", [-1]), ("n", [np.inf]), ("n", [np.nan]),
    ("n", [True]), ("n", [1j]), ("n", ["1"]), ("n", [1, 1]),
    ("s", [0]), ("s", [2]), ("s", [np.nan]), ("s", [True]),
    ("s", [1j]), ("s", ["1"]), ("s", [[1]]),
])
def test_invalid_trace_medium(name, value):
    for construct in (lambda: RayTrace([0], [[[1], [0]]], **{name: value}), lambda: GaussianTrace([0], [1], [1j], **{name: value})):
        with pytest.raises(ValueError):
            construct()
