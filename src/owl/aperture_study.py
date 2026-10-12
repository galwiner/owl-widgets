"""Reusable numerical study of a Gaussian beam clipped at a thin lens.

Coordinates are millimetres and radians. ``z_mm=0`` is the input waist, the
lens/aperture is at ``distance_mm``, and positive z follows propagation. 2-D
arrays are indexed ``[y, x]``; longitudinal arrays are indexed ``[x, z]``.
The sole public calculation returns only finite, strict-JSON-compatible data.
"""

from dataclasses import dataclass
from numbers import Integral, Real
from typing import Any

import numpy as np

__all__ = ["ApertureStudySpec", "calculate_aperture_study"]


@dataclass(frozen=True)
class ApertureStudySpec:
    waist_mm: float = 0.25
    wavelength_nm: float = 1000.0
    distance_mm: float = 100.0
    focal_length_mm: float = 50.0
    aperture_diameter_ratios: tuple[float | None, ...] = (None, 2.0, 1.0, 0.5)
    grid_size: int = 256
    window_mm: float = 8.0
    longitudinal_samples: int = 180
    ray_count: int = 100_000
    seed: int = 0

    def __post_init__(self) -> None:
        for name in ("waist_mm", "wavelength_nm", "distance_mm", "focal_length_mm", "window_mm"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
                raise ValueError(f"{name} must be a finite real number")
            value = float(value)
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        if (isinstance(self.grid_size, (bool, np.bool_)) or not isinstance(self.grid_size, Integral)
                or self.grid_size < 64 or self.grid_size > 1024
                or self.grid_size & (self.grid_size - 1)):
            raise ValueError("grid_size must be a power of two from 64 through 1024")
        object.__setattr__(self, "grid_size", int(self.grid_size))
        for name, lower in (("longitudinal_samples", 16), ("ray_count", 1)):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < lower:
                raise ValueError(f"{name} must be an integer >= {lower}")
            object.__setattr__(self, name, int(value))
        if isinstance(self.seed, (bool, np.bool_)) or not isinstance(self.seed, Integral) or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        object.__setattr__(self, "seed", int(self.seed))
        if not isinstance(self.aperture_diameter_ratios, tuple) or not self.aperture_diameter_ratios:
            raise ValueError("aperture_diameter_ratios must be a nonempty tuple")
        ratios: list[float | None] = []
        for ratio in self.aperture_diameter_ratios:
            if ratio is None:
                ratios.append(None)
            elif (isinstance(ratio, (bool, np.bool_)) or not isinstance(ratio, Real)
                  or not np.isfinite(ratio) or ratio <= 0):
                raise ValueError("aperture diameter ratios must be positive finite numbers or None")
            else:
                ratios.append(float(ratio))
        if len(set(ratios)) != len(ratios):
            raise ValueError("aperture diameter ratios must be unique")
        object.__setattr__(self, "aperture_diameter_ratios", tuple(ratios))


def calculate_aperture_study(spec: ApertureStudySpec) -> dict[str, Any]:
    """Calculate the complete aperture comparison as a finite JSON dictionary.

    ``None`` denotes the unclipped control. Intensities in ``scenarios`` share
    the unclipped true-waist peak; ray and wave image-plane arrays each share
    their own unclipped image-plane peak. Encircled fractions use incident
    power/ray count as denominator, so they include aperture loss.
    """
    if not isinstance(spec, ApertureStudySpec):
        raise ValueError("spec must be an ApertureStudySpec")

    n, width = spec.grid_size, spec.window_mm
    w0, lam, d, focal = spec.waist_mm, spec.wavelength_nm * 1e-6, spec.distance_mm, spec.focal_length_mm
    if d <= focal:
        raise ValueError("distance_mm must exceed focal_length_mm for a finite real geometric image")
    dx = width / n
    x = (np.arange(n) - n // 2) * dx
    xx, yy = np.meshgrid(x, x)
    r2, radius = xx * xx + yy * yy, np.hypot(xx, yy)
    freq = np.fft.fftfreq(n, d=dx)
    f2 = freq[:, None] ** 2 + freq[None, :] ** 2

    def propagate(field: np.ndarray, distance: float) -> np.ndarray:
        return np.fft.ifft2(np.fft.fft2(field) * np.exp(-1j * np.pi * lam * distance * f2))

    def slices(field: np.ndarray, distances: np.ndarray) -> np.ndarray:
        spectrum = np.fft.fft2(field)
        return np.asarray([
            np.abs(np.fft.ifft2(spectrum * np.exp(-1j * np.pi * lam * z * f2))[n // 2]) ** 2
            for z in distances
        ]).T

    z_rayleigh = np.pi * w0**2 / lam
    lens_radius = w0 * np.sqrt(1 + (d / z_rayleigh) ** 2)
    q_lens = complex(d, z_rayleigh)
    q_out = q_lens / (1 - q_lens / focal)
    waist_after_lens = -q_out.real
    true_waist_radius = np.sqrt(-lam / (np.pi * np.imag(1 / (q_out + waist_after_lens))))
    geometric_image_after_lens = 1 / (1 / focal - 1 / d)
    geometric_image_z = d + geometric_image_after_lens
    image_radius = np.sqrt(-lam / (np.pi * np.imag(1 / (q_out + geometric_image_after_lens))))
    z_end = geometric_image_z + 0.1 * geometric_image_after_lens

    field0 = np.exp(-r2 / w0**2).astype(complex)
    field_lens = propagate(field0, d) * np.exp(-1j * np.pi * r2 / (lam * focal))
    incident_power = float(np.sum(np.abs(field_lens) ** 2))
    reference_peak = float(np.max(np.abs(propagate(field_lens, waist_after_lens)) ** 2))
    z_grid = np.linspace(0, z_end, spec.longitudinal_samples)
    before = z_grid <= d
    pre_slice = slices(field0, z_grid[before])
    post_distances = z_grid[~before] - d

    def mask_for(ratio: float | None) -> tuple[np.ndarray, float | None]:
        if ratio is None:
            return np.ones_like(radius), None
        aperture_radius = ratio * lens_radius / 2
        # Interpret the one-pixel ramp as covered pixel area. Its square root is
        # the field multiplier, preserving that fractional area in optical power.
        coverage = np.clip((aperture_radius - radius) / dx + 0.5, 0, 1)
        return np.sqrt(coverage), aperture_radius

    scenario_work: list[dict[str, Any]] = []
    fields: list[np.ndarray] = []
    for ratio in spec.aperture_diameter_ratios:
        mask, aperture_radius = mask_for(ratio)
        clipped = field_lens * mask
        post_slice = slices(clipped, post_distances)
        center = post_slice[n // 2]
        peak_index = int(np.argmax(center))
        peak_distance = float(post_distances[peak_index])
        spot = np.abs(propagate(clipped, peak_distance)) ** 2
        sampled_transmission = float(np.sum(np.abs(clipped) ** 2) / incident_power)
        analytic_transmission = 1.0 if ratio is None else float(1 - np.exp(-(ratio**2) / 2))
        brightest_z = d + peak_distance
        scenario_work.append({
            "diameter_ratio": ratio,
            "aperture_radius_mm": aperture_radius,
            "analytic_transmission": analytic_transmission,
            "sampled_transmission": sampled_transmission,
            "fresnel_number": None if aperture_radius is None else aperture_radius**2 / (lam * focal),
            "brightest_z_mm": brightest_z,
            "focal_shift_mm": brightest_z - (d + waist_after_lens),
            "peak_ratio": float(np.max(spot) / reference_peak),
            "longitudinal_intensity": (np.hstack((pre_slice, post_slice)) / reference_peak).tolist(),
            "brightest_spot_intensity": (spot / reference_peak).tolist(),
        })
        fields.append(clipped)

    # Statistical rays sample the same Gaussian phase space used by the notebook.
    rng = np.random.default_rng(spec.seed)
    positions = rng.normal(0, w0 / 2, (2, spec.ray_count))
    angles = rng.normal(0, lam / (2 * np.pi * w0), (2, spec.ray_count))
    lens_positions = positions + d * angles
    lens_radius_rays = np.hypot(lens_positions[0], lens_positions[1])
    output_angles = angles - lens_positions / focal
    image_positions = lens_positions + geometric_image_after_lens * output_angles
    edge_limit = 0.6
    histogram_edges = np.arange(-edge_limit, edge_limit + 2 * dx, 2 * dx)
    if histogram_edges[-1] < edge_limit:
        histogram_edges = np.append(histogram_edges, edge_limit)

    image_wave_intensities = [np.abs(propagate(field, geometric_image_after_lens)) ** 2 for field in fields]
    wave_normalization = float(np.max(np.abs(propagate(field_lens, geometric_image_after_lens)) ** 2))
    all_ray_histograms: list[np.ndarray] = []
    comparison_work: list[dict[str, Any]] = []
    circle = radius < image_radius
    for ratio, aperture_radius, field, wave_image in zip(
            spec.aperture_diameter_ratios,
            [item["aperture_radius_mm"] for item in scenario_work], fields, image_wave_intensities):
        keep = np.ones(spec.ray_count, dtype=bool) if ratio is None else lens_radius_rays <= aperture_radius
        hist, _, _ = np.histogram2d(image_positions[0, keep], image_positions[1, keep], bins=(histogram_edges, histogram_edges))
        hist = hist.T
        all_ray_histograms.append(hist)
        comparison_work.append({
            "diameter_ratio": ratio,
            "passing_ray_count": int(np.count_nonzero(keep)),
            "ray_encircled_incident_fraction": float(np.count_nonzero(keep & (np.hypot(image_positions[0], image_positions[1]) < image_radius)) / spec.ray_count),
            "wave_encircled_incident_fraction": float(np.sum(wave_image[circle]) / incident_power),
            "ray_histogram": None,
            "wave_intensity": (wave_image / wave_normalization).tolist(),
        })
    control_histogram, _, _ = np.histogram2d(
        image_positions[0], image_positions[1], bins=(histogram_edges, histogram_edges)
    )
    ray_normalization = float(np.max(control_histogram))
    for item, histogram in zip(comparison_work, all_ray_histograms):
        item["ray_histogram"] = (histogram / ray_normalization).tolist()

    fan_heights = np.linspace(-w0, w0, 5)
    fan_angles = np.linspace(-lam / (np.pi * w0), lam / (np.pi * w0), 11)
    fan_rays: list[dict[str, Any]] = []
    for color_scalar, y0 in enumerate(fan_heights):
        for theta0 in fan_angles:
            y_lens = float(y0 + d * theta0)
            theta_after = float(theta0 - y_lens / focal)
            y_image = float(y_lens + geometric_image_after_lens * theta_after)
            y_end = float(y_lens + (z_end - d) * theta_after)
            fan_rays.append({
                "launch_height_mm": float(y0),
                "launch_angle_rad": float(theta0),
                "color_scalar": color_scalar / 4,
                "unclipped_path": {"z_mm": [0.0, d, geometric_image_z, z_end], "y_mm": [float(y0), y_lens, y_image, y_end]},
            })

    fan_scenarios = []
    for ratio, scenario in zip(spec.aperture_diameter_ratios, scenario_work):
        aperture_radius = scenario["aperture_radius_mm"]
        paths = []
        passing = 0
        for ray in fan_rays:
            blocked = aperture_radius is not None and abs(ray["unclipped_path"]["y_mm"][1]) > aperture_radius
            passing += not blocked
            path = ray["unclipped_path"]
            paths.append({
                "launch_height_mm": ray["launch_height_mm"], "launch_angle_rad": ray["launch_angle_rad"],
                "color_scalar": ray["color_scalar"], "blocked": bool(blocked),
                "z_mm": path["z_mm"][:2] if blocked else path["z_mm"],
                "y_mm": path["y_mm"][:2] if blocked else path["y_mm"],
            })
        fan_scenarios.append({"diameter_ratio": ratio, "passing_count": passing, "paths": paths})

    w_reference = np.empty_like(z_grid)
    w_reference[before] = w0 * np.sqrt(1 + (z_grid[before] / z_rayleigh) ** 2)
    for index in np.flatnonzero(~before):
        q = q_out + (z_grid[index] - d)
        w_reference[index] = np.sqrt(-lam / (np.pi * np.imag(1 / q)))

    result = {
        "schema_version": 1,
        "coordinates": {"units": {"length": "mm", "angle": "rad"}, "array_order": {"longitudinal_intensity": "[x,z]", "spots_and_histograms": "[y,x]"}, "origin": "input_waist"},
        "spec": {"waist_mm": w0, "wavelength_nm": spec.wavelength_nm, "distance_mm": d, "focal_length_mm": focal, "aperture_diameter_ratios": list(spec.aperture_diameter_ratios), "grid_size": n, "window_mm": width, "longitudinal_samples": spec.longitudinal_samples, "ray_count": spec.ray_count, "seed": spec.seed},
        "grids": {"x_mm": x.tolist(), "z_mm": z_grid.tolist(), "image_histogram_edges_mm": histogram_edges.tolist()},
        "normalization": {"longitudinal_and_brightest_spots": "unclipped_true_waist_peak", "unclipped_true_waist_peak": reference_peak, "image_plane_wave_peak": wave_normalization, "image_plane_ray_histogram_peak": ray_normalization},
        "gaussian_reference": {"rayleigh_range_mm": z_rayleigh, "lens_radius_mm": lens_radius, "radius_by_z_mm": w_reference.tolist(), "geometric_image_z_mm": geometric_image_z, "geometric_image_radius_mm": image_radius, "true_waist_z_mm": d + waist_after_lens, "true_waist_radius_mm": true_waist_radius, "magnification": -geometric_image_after_lens / d},
        "scenarios": scenario_work,
        "ray_fan": {"launch_heights_mm": fan_heights.tolist(), "launch_angles_rad": fan_angles.tolist(), "scenarios": fan_scenarios},
        "image_plane_comparison": {"z_mm": geometric_image_z, "reference_circle_radius_mm": image_radius, "scenarios": comparison_work},
    }
    # Catch accidental NumPy scalars, NaN, or infinity before crossing the seam.
    import json
    json.dumps(result, allow_nan=False)
    return result
