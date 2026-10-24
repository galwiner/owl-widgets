import json

import numpy as np
import pytest

from owl import FreeSpace, GaussianBeam, OpticalSystem, ThinLens
from owl import _array_backend
from owl.aperture_study import ApertureStudySpec, calculate_aperture_study
from owl.wave import benchmark_backends, cross_sections, longitudinal_section


@pytest.fixture
def optical_case():
    return (
        OpticalSystem((FreeSpace(10), ThinLens(20), FreeSpace(15))),
        GaussianBeam(0.25, 633),
    )


def test_cpu_is_lazy_and_default_contract_is_unchanged(monkeypatch, optical_case):
    def reject_import(name):
        raise AssertionError(f"unexpected optional import: {name}")

    monkeypatch.setattr(_array_backend, "import_module", reject_import)
    system, beam = optical_case
    default_cross = cross_sections(system, beam, grid_size=64, window_mm=3)
    cpu_cross = cross_sections(system, beam, grid_size=64, window_mm=3, backend="cpu")
    default_long = longitudinal_section(
        system, beam, grid_size=64, window_mm=3, samples_per_gap=4
    )
    cpu_long = longitudinal_section(
        system, beam, grid_size=64, window_mm=3, samples_per_gap=4, backend="cpu"
    )
    assert default_cross == cpu_cross
    assert default_long == cpu_long
    json.dumps(default_cross, allow_nan=False)
    json.dumps(default_long, allow_nan=False)


def test_auto_falls_back_and_explicit_gpu_has_clear_error(monkeypatch):
    def unavailable(name):
        raise ImportError("CuPy is not installed")

    monkeypatch.setattr(_array_backend, "import_module", unavailable)
    assert _array_backend.resolve_backend("auto").name == "cpu"
    with pytest.raises(RuntimeError, match="GPU backend unavailable.*CuPy is not installed"):
        _array_backend.resolve_backend("gpu")
    with pytest.raises(ValueError, match="auto.*cpu.*gpu"):
        _array_backend.resolve_backend("cuda")


def test_aperture_cpu_preserves_schema_and_seeded_rays(monkeypatch):
    monkeypatch.setattr(
        _array_backend, "import_module",
        lambda name: (_ for _ in ()).throw(AssertionError("CuPy imported on CPU")),
    )
    spec = ApertureStudySpec(
        grid_size=64, longitudinal_samples=16, ray_count=200, seed=17,
        aperture_diameter_ratios=(None, 1.0),
    )
    default = calculate_aperture_study(spec)
    explicit = calculate_aperture_study(spec, backend="cpu")
    assert default == explicit
    assert [item["passing_ray_count"] for item in default["image_plane_comparison"]["scenarios"]] == [
        item["passing_ray_count"] for item in explicit["image_plane_comparison"]["scenarios"]
    ]
    json.dumps(default, allow_nan=False)


def test_benchmark_reports_unavailable_without_failing(monkeypatch, optical_case):
    import owl.wave as wave

    monkeypatch.setattr(
        wave, "resolve_backend",
        lambda name: (_ for _ in ()).throw(RuntimeError("no test GPU")),
    )
    report = benchmark_backends(*optical_case, grid_size=64, window_mm=3)
    assert report["status"] == "unavailable"
    assert "no test GPU" in report["reason"]
    assert set(report) == {
        "status", "device", "cpu_seconds", "gpu_seconds", "speedup",
        "peak_normalized_max_absolute_difference", "reason",
    }
    json.dumps(report, allow_nan=False)


def _usable_gpu():
    try:
        return _array_backend.resolve_backend("gpu")
    except RuntimeError as exc:
        pytest.skip(str(exc))


def test_real_cupy_wave_parity(optical_case):
    _usable_gpu()
    system, beam = optical_case
    cpu_cross = cross_sections(system, beam, grid_size=64, window_mm=3, backend="cpu")
    gpu_cross = cross_sections(system, beam, grid_size=64, window_mm=3, backend="gpu")
    cpu_long = longitudinal_section(
        system, beam, grid_size=64, window_mm=3, samples_per_gap=4, backend="cpu"
    )
    gpu_long = longitudinal_section(
        system, beam, grid_size=64, window_mm=3, samples_per_gap=4, backend="gpu"
    )
    assert [p["label"] for p in cpu_cross["planes"]] == [p["label"] for p in gpu_cross["planes"]]
    np.testing.assert_allclose(
        [p["intensity"] for p in gpu_cross["planes"]],
        [p["intensity"] for p in cpu_cross["planes"]], rtol=2e-10, atol=2e-12,
    )
    np.testing.assert_allclose(gpu_long["intensity"], cpu_long["intensity"], rtol=2e-10, atol=2e-12)


def test_real_cupy_aperture_parity_and_seeded_rays():
    _usable_gpu()
    spec = ApertureStudySpec(
        grid_size=64, longitudinal_samples=16, ray_count=200, seed=23,
        aperture_diameter_ratios=(None, 1.0),
    )
    cpu = calculate_aperture_study(spec, backend="cpu")
    gpu = calculate_aperture_study(spec, backend="gpu")
    assert cpu["ray_fan"] == gpu["ray_fan"]
    for cpu_item, gpu_item in zip(
        cpu["image_plane_comparison"]["scenarios"],
        gpu["image_plane_comparison"]["scenarios"],
    ):
        assert cpu_item["passing_ray_count"] == gpu_item["passing_ray_count"]
        assert cpu_item["ray_histogram"] == gpu_item["ray_histogram"]
        np.testing.assert_allclose(gpu_item["wave_intensity"], cpu_item["wave_intensity"], rtol=2e-10, atol=2e-12)
    json.dumps(gpu, allow_nan=False)
