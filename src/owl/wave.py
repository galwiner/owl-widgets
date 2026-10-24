"""Scalar, paraxial wave sampling on a fixed, periodic FFT grid.

Fields are power-normalized envelopes. Intensities from both public samplers are
normalized to the input peak. Global carrier phase is omitted.
"""

from statistics import median
from time import perf_counter
from typing import Any

import numpy as np

from ._array_backend import ArrayBackend, resolve_backend

from .core import (
    Aperture, FreeSpace, GaussianBeam, Interface, Mirror, OpticalSystem,
    ThickLens, ThinLens, _finite,
)

__all__ = ["benchmark_backends", "cross_sections", "longitudinal_section"]


def _validate_inputs(
    system: OpticalSystem,
    beam: GaussianBeam,
    grid_size: int,
    window_mm: float | None,
) -> tuple[int, float, list[Aperture]]:
    if not isinstance(system, OpticalSystem) or not isinstance(beam, GaussianBeam):
        raise ValueError("Expected an OpticalSystem and GaussianBeam")
    if (isinstance(grid_size, (bool, np.bool_))
            or not isinstance(grid_size, (int, np.integer))
            or grid_size < 64 or grid_size > 512 or grid_size & (grid_size - 1)):
        raise ValueError("grid_size must be a power of two from 64 through 512")
    grid_size = int(grid_size)
    apertures = [e for e in system.elements if isinstance(e, Aperture)]
    if window_mm is None:
        reference = system.gaussian(beam)
        half_width = 4 * float(np.max(reference.radius_mm))
        for aperture in apertures:
            extent = max(abs(aperture.x_mm), abs(aperture.y_mm)) + aperture.radius_mm
            half_width = max(half_width, 1.2 * extent)
        window_mm = 2 * half_width
    window_mm = _finite(window_mm, "window_mm")
    if window_mm <= 0:
        raise ValueError("window_mm must be positive")
    return grid_size, window_mm, apertures


class _WaveSimulation:
    def __init__(self, system: OpticalSystem, beam: GaussianBeam, grid_size: int,
                 window_mm: float, apertures: list[Aperture], backend: ArrayBackend) -> None:
        self.backend = backend
        self.xp = backend.xp
        self.beam = beam
        self.grid_size = grid_size
        self.window_mm = window_mm
        self.dx = window_mm / grid_size
        if self.dx <= 0 or not np.isfinite(beam.wavelength_mm) or beam.wavelength_mm <= 0:
            raise ValueError("Window or wavelength is outside numerical range")
        self.warnings: list[str] = []
        reference = system.gaussian(beam)
        if float(np.min(reference.radius_mm)) < 4 * self.dx:
            self.warn("Sampling: the unclipped Gaussian radius spans fewer than four pixels; increase grid_size or reduce window_mm.")
        for aperture in apertures:
            if aperture.radius_mm < 4 * self.dx:
                self.warn("Sampling: an aperture radius spans fewer than four pixels; hard-edge throughput may be inaccurate.")
            if max(abs(aperture.x_mm), abs(aperture.y_mm)) + aperture.radius_mm >= window_mm / 2:
                self.warn("Window: an aperture extends to or beyond the grid edge.")

        xp = self.xp
        self.x = (xp.arange(grid_size) - grid_size // 2) * self.dx
        self.xx, self.yy = xp.meshgrid(self.x, self.x)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            self.field = xp.exp(-((self.xx / beam.waist_mm) ** 2
                                  + (self.yy / beam.waist_mm) ** 2)).astype(complex)
            self.r2 = self.xx * self.xx + self.yy * self.yy
            self.freq = xp.fft.fftfreq(grid_size, d=self.dx)
            self.f2 = self.freq[:, None] ** 2 + self.freq[None, :] ** 2
        if not all(bool(self.backend.scalar(xp.all(xp.isfinite(a))))
                   for a in (self.field, self.r2, self.f2)):
            raise ValueError("Grid is outside numerical range")
        self.input_power = float(self.backend.scalar(xp.sum(xp.abs(self.field) ** 2)))
        self.z = 0.0
        self.path = 0.0
        self.n = 1.0
        self.direction = 1
        border = max(1, grid_size // 20)
        self.edge = xp.ones((grid_size, grid_size), dtype=bool)
        self.edge[border:-border, border:-border] = False

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def intensity(self, label: str) -> tuple[Any, float]:
        xp = self.xp
        with np.errstate(over="ignore", invalid="ignore"):
            intensity = xp.abs(self.field) ** 2
            power = float(self.backend.scalar(xp.sum(intensity)))
        finite = bool(self.backend.scalar(xp.all(xp.isfinite(intensity))))
        if (not finite or not np.isfinite(power)
                or not np.isfinite(self.z) or not np.isfinite(self.path)):
            raise ValueError("Wave propagation produced non-finite values")
        edge_power = float(self.backend.scalar(xp.sum(intensity[self.edge])))
        if power and edge_power / power > 1e-4:
            self.warn(f"Window: appreciable power near the grid edge at {label}; increase window_mm to check FFT wraparound.")
        return intensity, power

    def _phase_factor(self, phase: Any) -> Any:
        if not bool(self.backend.scalar(self.xp.all(self.xp.isfinite(phase)))):
            raise ValueError("Wave phase is outside numerical range")
        return self.xp.exp(1j * phase)

    def propagate(self, distance_mm: float) -> None:
        xp = self.xp
        spectrum = xp.fft.fft2(self.field)
        spectral_power = xp.abs(spectrum) ** 2
        limit = 0.8 * float(self.backend.scalar(xp.max(xp.abs(self.freq))))
        high = ((xp.abs(self.freq[:, None]) > limit)
                | (xp.abs(self.freq[None, :]) > limit))
        total = float(self.backend.scalar(spectral_power.sum()))
        high_power = float(self.backend.scalar(spectral_power[high].sum()))
        if total and high_power / total > 1e-4:
            self.warn("Sampling: appreciable power near the Nyquist limit; increase grid_size to check diffraction accuracy.")
        with np.errstate(over="ignore", invalid="ignore"):
            phase = -np.pi * (self.beam.wavelength_mm / self.n) * distance_mm * self.f2
        self.field = xp.fft.ifft2(spectrum * self._phase_factor(phase))
        self.z += self.direction * distance_mm
        self.path += distance_mm

    def surface(self, element: Any) -> None:
        if isinstance(element, Aperture):
            self.field *= self.xp.hypot(self.xx - element.x_mm,
                                        self.yy - element.y_mm) <= element.radius_mm
            return
        if isinstance(element, Interface):
            coefficient = (np.pi / self.beam.wavelength_mm
                           * (element.n1 - element.n2) / element.radius_mm)
            self.n = element.n2
        elif isinstance(element, ThinLens):
            coefficient = -np.pi * self.n / self.beam.wavelength_mm / element.focal_length_mm
        elif isinstance(element, Mirror):
            coefficient = -2 * np.pi * self.n / self.beam.wavelength_mm / element.radius_mm
            self.direction = -self.direction
        else:
            raise TypeError(f"Unsupported optical surface: {type(element).__name__}")
        xp = self.xp
        field_peak = float(self.backend.scalar(xp.max(xp.abs(self.field))))
        illuminated = xp.abs(self.field) > 1e-3 * field_peak
        any_illuminated = bool(self.backend.scalar(xp.any(illuminated)))
        illuminated_radius = (float(self.backend.scalar(xp.max(xp.hypot(
            self.xx[illuminated], self.yy[illuminated])))) if any_illuminated else 0.0)
        if (any_illuminated
                and 2 * abs(coefficient) * illuminated_radius * self.dx > np.pi):
            self.warn("Sampling: a quadratic optical phase exceeds the spatial Nyquist limit in the illuminated region.")
        with np.errstate(over="ignore", invalid="ignore"):
            phase = coefficient * self.r2
        self.field *= self._phase_factor(phase)


def _expanded(element: Any) -> tuple[Any, ...]:
    if isinstance(element, ThickLens):
        return (Interface(element.radius1_mm, 1.0, element.n),
                FreeSpace(element.thickness_mm),
                Interface(element.radius2_mm, element.n, 1.0))
    return (element,)


def cross_sections(
    system: OpticalSystem,
    beam: GaussianBeam,
    *,
    grid_size: int = 128,
    window_mm: float | None = None,
    backend: str | ArrayBackend = "cpu",
) -> dict[str, Any]:
    """Return input and one plane after each original element."""
    grid_size, window_mm, apertures = _validate_inputs(system, beam, grid_size, window_mm)
    resolved = backend if isinstance(backend, ArrayBackend) else resolve_backend(backend)
    sim = _WaveSimulation(system, beam, grid_size, window_mm, apertures, resolved)
    planes: list[dict[str, Any]] = []

    def record(label: str) -> None:
        intensity, power = sim.intensity(label)
        planes.append({"label": label, "z_mm": float(sim.z),
                       "intensity": sim.backend.to_numpy(intensity).tolist(),
                       "transmission": power / sim.input_power})

    record("input")
    for index, original in enumerate(system.elements, 1):
        for element in _expanded(original):
            if isinstance(element, FreeSpace):
                sim.propagate(element.distance_mm)
            else:
                sim.surface(element)
        record(f"{index}: {original.to_dict()['type']}")
    return {"planes": planes, "x_mm": sim.backend.to_numpy(sim.x).tolist(), "window_mm": window_mm,
            "warnings": sim.warnings}


def longitudinal_section(
    system: OpticalSystem,
    beam: GaussianBeam,
    *,
    grid_size: int = 128,
    window_mm: float | None = None,
    samples_per_gap: int = 60,
    backend: str | ArrayBackend = "cpu",
) -> dict[str, Any]:
    """Return center-line intensity sampled along the optical path.

    Every free-space gap contributes ``samples_per_gap`` equal propagation
    intervals (including its endpoint). Non-gap surfaces contribute a row at
    their exact position, so an aperture's clipping is visible immediately.
    Thick-lens glass is treated as an internal gap and sampled the same way.
    ``z_mm`` follows lab direction while ``path_mm`` always increases.
    """
    if (isinstance(samples_per_gap, (bool, np.bool_))
            or not isinstance(samples_per_gap, (int, np.integer))
            or samples_per_gap < 4 or samples_per_gap > 200):
        raise ValueError("samples_per_gap must be an integer from 4 through 200")
    samples_per_gap = int(samples_per_gap)
    grid_size, window_mm, apertures = _validate_inputs(system, beam, grid_size, window_mm)
    resolved = backend if isinstance(backend, ArrayBackend) else resolve_backend(backend)
    sim = _WaveSimulation(system, beam, grid_size, window_mm, apertures, resolved)
    z_values: list[float] = []
    path_values: list[float] = []
    rows: list[list[float]] = []
    markers: list[dict[str, Any]] = []

    def record(label: str) -> None:
        intensity, _ = sim.intensity(label)
        z_values.append(float(sim.z))
        path_values.append(float(sim.path))
        rows.append(sim.backend.to_numpy(intensity[grid_size // 2]).tolist())

    def marker(kind: str, label: str) -> None:
        markers.append({"type": kind, "z_mm": float(sim.z),
                        "path_mm": float(sim.path), "label": label})

    record("input")
    for index, original in enumerate(system.elements, 1):
        original_type = original.to_dict()["type"]
        label = f"{index}: {original_type}"
        if isinstance(original, ThickLens):
            entry, glass, exit_surface = _expanded(original)
            sim.surface(entry)
            record(f"{label} front")
            marker(original_type, f"{label} front")
            step = glass.distance_mm / samples_per_gap
            for _ in range(samples_per_gap):
                sim.propagate(step)
                record(f"{label} glass")
            sim.surface(exit_surface)
            record(f"{label} back")
            marker(original_type, f"{label} back")
        elif isinstance(original, FreeSpace):
            step = original.distance_mm / samples_per_gap
            for _ in range(samples_per_gap):
                sim.propagate(step)
                record(label)
            marker(original_type, label)
        else:
            sim.surface(original)
            record(label)
            marker(original_type, label)

    return {"z_mm": z_values, "path_mm": path_values,
            "x_mm": sim.backend.to_numpy(sim.x).tolist(),
            "intensity": rows, "elements": markers, "window_mm": window_mm,
            "warnings": sim.warnings}


def benchmark_backends(
    system: OpticalSystem,
    beam: GaussianBeam,
    grid_size: int,
    window_mm: float,
    *,
    repeats: int = 3,
) -> dict[str, Any]:
    """Benchmark complete wave samplers on CPU and GPU on demand.

    CuPy is imported and CUDA initialized only when this function is called.
    The returned dictionary consists solely of strict JSON-native values.
    """
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 5:
        raise ValueError("repeats must be an integer from 1 through 5")
    try:
        gpu = resolve_backend("gpu")
    except (RuntimeError, ValueError) as exc:
        return {"status": "unavailable", "device": None, "cpu_seconds": None,
                "gpu_seconds": None, "speedup": None,
                "peak_normalized_max_absolute_difference": None, "reason": str(exc)}
    cpu = resolve_backend("cpu")

    def run(backend: ArrayBackend) -> tuple[dict[str, Any], dict[str, Any]]:
        return (
            cross_sections(system, beam, grid_size=grid_size,
                           window_mm=window_mm, backend=backend),
            longitudinal_section(system, beam, grid_size=grid_size,
                                 window_mm=window_mm, backend=backend),
        )

    # Warm up FFT machinery, kernels, and the CUDA context outside the timed region.
    run(cpu)
    run(gpu)
    gpu.synchronize()
    cpu_times: list[float] = []
    gpu_times: list[float] = []
    cpu_result: tuple[dict[str, Any], dict[str, Any]] | None = None
    gpu_result: tuple[dict[str, Any], dict[str, Any]] | None = None
    for _ in range(repeats):
        start = perf_counter()
        cpu_result = run(cpu)
        cpu_times.append(perf_counter() - start)
        gpu.synchronize()
        start = perf_counter()
        gpu_result = run(gpu)
        gpu.synchronize()
        gpu_times.append(perf_counter() - start)
    assert cpu_result is not None and gpu_result is not None
    cpu_seconds = median(cpu_times)
    gpu_seconds = median(gpu_times)

    cpu_values = np.concatenate((
        np.asarray([plane["intensity"] for plane in cpu_result[0]["planes"]]).ravel(),
        np.asarray(cpu_result[1]["intensity"]).ravel(),
    ))
    gpu_values = np.concatenate((
        np.asarray([plane["intensity"] for plane in gpu_result[0]["planes"]]).ravel(),
        np.asarray(gpu_result[1]["intensity"]).ravel(),
    ))
    scale = max(float(np.max(np.abs(cpu_values))), np.finfo(float).eps)
    difference = float(np.max(np.abs(cpu_values - gpu_values)) / scale)
    speedup = float(cpu_seconds / gpu_seconds) if gpu_seconds > 0 else 0.0
    report = {"status": "available", "device": gpu.device,
              "cpu_seconds": float(cpu_seconds), "gpu_seconds": float(gpu_seconds),
              "speedup": speedup,
              "peak_normalized_max_absolute_difference": difference,
              "reason": None}
    if not all(np.isfinite(value) for value in
               (cpu_seconds, gpu_seconds, speedup, difference)):
        raise RuntimeError("Backend benchmark produced non-finite results")
    return report
