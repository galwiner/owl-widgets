"""Reusable numerical model for the aperture/field/vignetting stop study.

The public seam is deliberately small: validate/serialize a :class:`StopStudySpec`,
then pass it to :func:`calculate_stop_study`.  The returned dictionary contains
only finite JSON-compatible values and is sufficient to redraw the original
three ray panels, illumination panel, pupil maps, and stop-classification table.
All distances and heights are in millimetres.
"""

from dataclasses import dataclass, fields
from numbers import Integral, Real
from typing import Any

import numpy as np

__all__ = ["StopStudySpec", "calculate_stop_study"]


def _finite(value: Any, name: str, *, positive: bool = False, nonnegative: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real number") from exc
    if not np.isfinite(result):
        raise ValueError(f"{name} must be a finite real number")
    if positive and result <= 0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and result < 0:
        raise ValueError(f"{name} must be nonnegative")
    return result


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    result = int(value)
    if result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


def _heights(value: Any, name: str, *, minimum: int) -> tuple[float, ...]:
    if not isinstance(value, (tuple, list)) or len(value) < minimum:
        raise ValueError(f"{name} must be a sequence of at least {minimum} finite heights")
    result = tuple(_finite(item, f"{name}[{index}]") for index, item in enumerate(value))
    if any(right <= left for left, right in zip(result, result[1:])):
        raise ValueError(f"{name} must be strictly increasing")
    return result


@dataclass(frozen=True)
class StopStudySpec:
    """Inputs for a paraxial thin-lens stop study.

    ``pupil_count`` controls the Monte Carlo metrics. ``display_pupil_count``
    only caps points returned for plotting and therefore does not change those
    metrics. Height sequences must be finite and strictly increasing.
    """

    relay_distance_mm: float = 100.0
    focal_length_mm: float = 50.0
    pupil_sample_radius_mm: float = 0.9
    aperture_stop_z_mm: float = 100.0
    aperture_stop_radius_mm: float = 0.5
    field_stop_z_mm: float = 200.0
    field_stop_radius_mm: float = 1.2
    vignette_stop_z_mm: float = 150.0
    vignette_stop_radius_mm: float = 0.8
    diagram_field_heights_mm: tuple[float, ...] = (-2.0, -1.0, 0.0, 1.0, 2.0)
    diagram_pupil_heights_mm: tuple[float, ...] = tuple(np.linspace(-0.9, 0.9, 7))
    illumination_field_heights_mm: tuple[float, ...] = tuple(np.linspace(-2.4, 2.4, 49))
    pupil_map_field_heights_mm: tuple[float, ...] = (0.0, 1.4, 1.8, 2.05)
    pupil_count: int = 20_000
    seed: int = 1
    display_pupil_count: int = 4_000
    ray_z_count: int = 400

    def __post_init__(self) -> None:
        positive = (
            "relay_distance_mm", "pupil_sample_radius_mm", "aperture_stop_radius_mm",
            "field_stop_radius_mm", "vignette_stop_radius_mm",
        )
        for name in positive:
            object.__setattr__(self, name, _finite(getattr(self, name), name, positive=True))
        object.__setattr__(self, "focal_length_mm", _finite(self.focal_length_mm, "focal_length_mm"))
        if self.focal_length_mm == 0:
            raise ValueError("focal_length_mm must be nonzero")
        for name in ("aperture_stop_z_mm", "field_stop_z_mm", "vignette_stop_z_mm"):
            object.__setattr__(self, name, _finite(getattr(self, name), name, nonnegative=True))
        for name, minimum in (
            ("diagram_field_heights_mm", 1), ("diagram_pupil_heights_mm", 1),
            ("illumination_field_heights_mm", 2), ("pupil_map_field_heights_mm", 1),
        ):
            object.__setattr__(self, name, _heights(getattr(self, name), name, minimum=minimum))
        object.__setattr__(self, "pupil_count", _integer(self.pupil_count, "pupil_count", minimum=1))
        object.__setattr__(self, "seed", _integer(self.seed, "seed", minimum=0))
        object.__setattr__(self, "display_pupil_count", _integer(
            self.display_pupil_count, "display_pupil_count", minimum=1
        ))
        object.__setattr__(self, "ray_z_count", _integer(self.ray_z_count, "ray_z_count", minimum=2))
        if self.display_pupil_count > self.pupil_count:
            raise ValueError("display_pupil_count cannot exceed pupil_count")
        if 0.0 not in self.illumination_field_heights_mm:
            raise ValueError("illumination_field_heights_mm must contain 0")
        if 0.0 not in self.pupil_map_field_heights_mm:
            raise ValueError("pupil_map_field_heights_mm must contain 0")
        diagram_end = max(self.field_stop_z_mm, 2 * self.relay_distance_mm) + 40.0
        if max(self.aperture_stop_z_mm, self.field_stop_z_mm, self.vignette_stop_z_mm) > diagram_end:
            raise ValueError("all stops must lie within the ray diagram range")

    def to_dict(self) -> dict[str, Any]:
        """Return detached, JSON-compatible settings with an explicit schema version."""
        data: dict[str, Any] = {"schema_version": 1}
        for field in fields(self):
            value = getattr(self, field.name)
            data[field.name] = list(value) if isinstance(value, tuple) else value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StopStudySpec":
        """Restore settings, rejecting missing, unknown, or version-mismatched fields."""
        expected = {field.name for field in fields(cls)} | {"schema_version"}
        if not isinstance(data, dict) or set(data) != expected:
            raise ValueError(f"Expected exactly these keys: {sorted(expected)}")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError("Unsupported schema_version; expected integer 1")
        return cls(**{field.name: data[field.name] for field in fields(cls)})


def calculate_stop_study(spec: StopStudySpec = StopStudySpec()) -> dict[str, Any]:
    """Calculate ray diagrams, illumination, pupil maps, and stop taxonomy.

    The function is deterministic for a given spec. Illumination and pupil-map
    pass fractions use all ``pupil_count`` rays; pupil-map display arrays are a
    deterministic subset capped by ``display_pupil_count``.
    """
    if not isinstance(spec, StopStudySpec):
        raise ValueError("spec must be a StopStudySpec")

    d = spec.relay_distance_mm
    f = spec.focal_length_mm
    z_end = max(spec.field_stop_z_mm, 2 * d) + 40.0
    z_samples = np.linspace(0.0, z_end, spec.ray_z_count)

    stop_defs = {
        "aperture": (spec.aperture_stop_z_mm, spec.aperture_stop_radius_mm, "iris on the lens"),
        "field": (spec.field_stop_z_mm, spec.field_stop_radius_mm, "at the image plane"),
        "vignette": (spec.vignette_stop_z_mm, spec.vignette_stop_radius_mm, "halfway to the image"),
    }
    configs = (
        ("aperture_only", "aperture stop only — iris on the lens", ("aperture",)),
        ("field_stop", "+ field stop at the image plane", ("aperture", "field")),
        ("vignette_stop", "+ a stop halfway to the image", ("aperture", "vignette")),
    )

    def ray_y(z: Any, h: Any, t: Any) -> np.ndarray:
        z_array = np.asarray(z, dtype=float)
        h_array = np.asarray(h, dtype=float)
        t_array = np.asarray(t, dtype=float)
        at_lens = h_array + d * t_array
        after_angle = t_array - at_lens / f
        return np.where(z_array <= d, h_array + z_array * t_array, at_lens + (z_array - d) * after_angle)

    def coefficients(stop_id: str) -> tuple[float, float]:
        z, _, _ = stop_defs[stop_id]
        return float(ray_y(z, 0.0, 1.0 / d)), float(ray_y(z, 1.0, -1.0 / d))

    def stop_record(stop_id: str) -> dict[str, Any]:
        z, radius, label = stop_defs[stop_id]
        a, b = coefficients(stop_id)
        tolerance = 1e-12
        classification = "aperture" if abs(b) <= tolerance else "field" if abs(a) <= tolerance else "vignette"
        return {
            "id": stop_id, "label": label, "z_mm": z, "radius_mm": radius,
            "A_pupil": a, "B_field": b, "classification": classification,
        }

    table = [stop_record(stop_id) for stop_id in ("aperture", "field", "vignette")]
    records = {record["id"]: record for record in table}

    rng = np.random.default_rng(spec.seed)
    uniform = rng.random((2, spec.pupil_count))
    radii = spec.pupil_sample_radius_mm * np.sqrt(uniform[0])
    pupil_x = radii * np.cos(2 * np.pi * uniform[1])
    pupil_y = radii * np.sin(2 * np.pi * uniform[1])

    def pass_mask(stop_ids: tuple[str, ...], height: float) -> np.ndarray:
        x_angle = pupil_x / d
        y_angle = (pupil_y - height) / d
        result = np.ones(spec.pupil_count, dtype=bool)
        for stop_id in stop_ids:
            z, radius, _ = stop_defs[stop_id]
            x_at_stop = ray_y(z, 0.0, x_angle)
            y_at_stop = ray_y(z, height, y_angle)
            result &= np.hypot(x_at_stop, y_at_stop) <= radius
        return result

    diagrams = []
    for config_id, label, stop_ids in configs:
        paths = []
        for height in spec.diagram_field_heights_mm:
            for pupil_height in spec.diagram_pupil_heights_mm:
                angle = (pupil_height - height) / d
                blocked_id = None
                blocked_z = z_end
                for stop_id in stop_ids:
                    z, radius, _ = stop_defs[stop_id]
                    if abs(float(ray_y(z, height, angle))) > radius and z < blocked_z:
                        blocked_id, blocked_z = stop_id, z
                mask = z_samples <= blocked_z
                path_z = z_samples[mask]
                path_y = ray_y(path_z, height, angle)
                marker = None if blocked_id is None else {
                    "z_mm": blocked_z,
                    "y_mm": float(ray_y(blocked_z, height, angle)),
                    "stop_id": blocked_id,
                    "color": "#ff4d4d",
                }
                paths.append({
                    "field_height_mm": height, "pupil_height_mm": pupil_height,
                    "color_scalar": height, "z_mm": path_z.tolist(), "y_mm": path_y.tolist(),
                    "first_blocked": marker,
                })
        distinguished = []
        for kind, height, angle, line_style in (
            ("marginal", 0.0, spec.aperture_stop_radius_mm / d, "dotted"),
            ("chief", spec.diagram_field_heights_mm[-1], -spec.diagram_field_heights_mm[-1] / d, "dashed"),
        ):
            distinguished.append({
                "kind": kind, "line_style": line_style, "z_mm": z_samples.tolist(),
                "y_mm": ray_y(z_samples, height, angle).tolist(),
            })
        diagrams.append({
            "id": config_id, "label": label, "stops": [records[item] for item in stop_ids],
            "paths": paths, "distinguished_paths": distinguished,
        })

    illumination_heights = np.asarray(spec.illumination_field_heights_mm)
    illumination_curves = []
    for config_id, label, stop_ids in configs:
        raw = np.array([pass_mask(stop_ids, height).mean() for height in illumination_heights])
        center = raw[np.flatnonzero(illumination_heights == 0.0)[0]]
        if center == 0:
            raise ValueError(f"configuration {config_id} has zero on-axis transmission")
        illumination_curves.append({
            "id": config_id, "label": label, "transmission": raw.tolist(),
            "relative": (raw / center).tolist(),
        })

    display_indices = np.linspace(
        0, spec.pupil_count - 1, min(spec.display_pupil_count, spec.pupil_count), dtype=int
    )
    vignette_ids = ("aperture", "vignette")
    map_masks = {height: pass_mask(vignette_ids, height) for height in spec.pupil_map_field_heights_mm}
    on_axis_fraction = float(map_masks[0.0].mean())
    pupil_maps = []
    for height in spec.pupil_map_field_heights_mm:
        mask = map_masks[height]
        circles = []
        for stop_id in vignette_ids:
            record = records[stop_id]
            a, b = record["A_pupil"], record["B_field"]
            circles.append({
                "stop_id": stop_id, "center_x_mm": 0.0, "center_y_mm": -b * height / a,
                "radius_mm": record["radius_mm"] / abs(a),
            })
        pupil_maps.append({
            "field_height_mm": height,
            "sample": {
                "x_mm": pupil_x[display_indices].tolist(),
                "y_mm": pupil_y[display_indices].tolist(),
                "pass": mask[display_indices].tolist(),
            },
            "projected_stop_circles": circles,
            "pass_fraction": float(mask.mean()),
            "relative_pass": float(mask.mean() / on_axis_fraction),
            "metric_sample_count": spec.pupil_count,
            "display_sample_count": len(display_indices),
        })

    result = {
        "schema_version": 1,
        "spec": spec.to_dict(),
        "ray_diagrams": diagrams,
        "illumination": {"field_heights_mm": illumination_heights.tolist(), "curves": illumination_curves},
        "pupil_maps": pupil_maps,
        "stop_table": table,
        "plot": {"z_limits_mm": [0.0, z_end], "y_limits_mm": [-2.7, 2.7]},
    }
    # Guard the interface promise here rather than leaving callers to discover it.
    def ensure_finite(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values():
                ensure_finite(child)
        elif isinstance(value, list):
            for child in value:
                ensure_finite(child)
        elif isinstance(value, float) and not np.isfinite(value):
            raise ValueError("stop study produced non-finite output")
    ensure_finite(result)
    return result
