"""Flatland light-field model: a layered scene, ray space, and digital refocusing.

Geometry. A thin main lens of focal length ``focal_length_mm`` and semi-aperture
``aperture_radius_mm`` sits at z = 0; z increases toward the sensor. One
transverse axis is modelled, so the light field is two-dimensional and can be
displayed directly as an image. The two-plane parameterization uses ``u`` on the
lens plane and ``s`` on the reference image plane at z = ``image_distance_mm``.
A ray is the pair (u, s) and carries paraxial angle
theta = (s - u) / image_distance_mm.

Scene. The scene is a stack of fronto-parallel textured layers at object
distances in front of the lens. A layer at distance Z images to
v = 1 / (1/f - 1/Z); define beta = image_distance_mm / v. The ray (u, s) meets
that layer's image at x = (s - u * (1 - beta)) / beta, so the layer occupies a
line of slope (1 - beta) in ray space: in focus when beta = 1, sheared otherwise.
Layers are opaque over a finite lateral extent and composite front to back, so
occlusion is part of the model rather than assumed away.

Refocusing. A synthetic photograph on the plane at v = image_distance_mm / alpha
is the shear-then-integrate
I(x) = integral L(u, alpha * x + u * (1 - alpha)) du, so alpha = beta brings the
matching layer into focus. All lengths are in millimetres.
"""

import json
from dataclasses import dataclass, fields
from numbers import Integral, Real
from typing import Any

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "LightFieldLayer",
    "LightFieldSpec",
    "calculate_light_field",
    "layer_beta",
    "sample_radiance",
]


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


def _fraction(value: Any, name: str) -> float:
    result = _finite(value, name)
    if not 0.0 < result < 1.0:
        raise ValueError(f"{name} must lie strictly between 0 and 1")
    return result


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


_TEXTURES = ("random", "bars")

# Random textures repeat only after this many cells, which is far outside any
# field of view used here, so correspondence stays unambiguous.
_TEXTURE_TABLE_SIZE = 4096


@dataclass(frozen=True)
class LightFieldLayer:
    """One opaque fronto-parallel scene layer carrying a one-dimensional texture.

    The layer covers ``|x - center_mm| <= half_width_mm`` in object space and is
    fully opaque there, so its edges occlude anything behind it. ``period_mm`` is
    the texture cell size. ``"random"`` gives each cell a deterministic pseudo
    random brightness, which is what correspondence and depth estimation need;
    ``"bars"`` gives a periodic square wave, which is better for resolution
    demonstrations but ambiguous for matching. ``duty`` applies to ``"bars"`` only.
    """

    object_distance_mm: float = 2000.0
    half_width_mm: float = 400.0
    center_mm: float = 0.0
    period_mm: float = 120.0
    duty: float = 0.5
    brightness: float = 1.0
    contrast_floor: float = 0.15
    texture: str = "random"
    seed: int = 1
    label: str = "layer"

    def __post_init__(self) -> None:
        for name in ("object_distance_mm", "half_width_mm", "period_mm", "brightness"):
            object.__setattr__(self, name, _finite(getattr(self, name), name, positive=True))
        object.__setattr__(self, "center_mm", _finite(self.center_mm, "center_mm"))
        object.__setattr__(self, "duty", _fraction(self.duty, "duty"))
        object.__setattr__(
            self, "contrast_floor", _finite(self.contrast_floor, "contrast_floor", nonnegative=True)
        )
        if self.contrast_floor >= 1.0:
            raise ValueError("contrast_floor must be below 1")
        if self.texture not in _TEXTURES:
            raise ValueError(f"texture must be one of {_TEXTURES}")
        object.__setattr__(self, "seed", _integer(self.seed, "seed", minimum=0))
        object.__setattr__(self, "label", _text(self.label, "label"))

    def to_dict(self) -> dict[str, Any]:
        """Return detached, JSON-compatible layer settings."""
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LightFieldLayer":
        """Restore a layer, rejecting missing or unknown fields."""
        expected = {field.name for field in fields(cls)}
        if not isinstance(data, dict) or set(data) != expected:
            raise ValueError(f"Expected exactly these keys: {sorted(expected)}")
        return cls(**{field.name: data[field.name] for field in fields(cls)})


def layer_beta(layer: LightFieldLayer, focal_length_mm: float, image_distance_mm: float) -> float:
    """Return beta = image_distance_mm / v for ``layer``; beta = 1 means in focus."""
    if not isinstance(layer, LightFieldLayer):
        raise ValueError("layer must be a LightFieldLayer")
    focal = _finite(focal_length_mm, "focal_length_mm", positive=True)
    reference = _finite(image_distance_mm, "image_distance_mm", positive=True)
    # A layer at or inside the front focal point images to infinity or virtually.
    if layer.object_distance_mm <= focal * (1.0 + 1e-9):
        raise ValueError("object_distance_mm must exceed focal_length_mm to form a real image")
    image_v = 1.0 / (1.0 / focal - 1.0 / layer.object_distance_mm)
    return reference / image_v


def _layer_texture(layer: LightFieldLayer, x_mm: NDArray[np.float64]) -> NDArray[np.float64]:
    if layer.texture == "bars":
        phase = np.mod((x_mm - layer.center_mm) / layer.period_mm, 1.0)
        return layer.brightness * np.where(phase < layer.duty, 1.0, layer.contrast_floor)
    # A fixed lookup table keeps the pattern vectorized, deterministic, and free of
    # integer-overflow concerns while staying aperiodic over any realistic field.
    table = np.random.default_rng(layer.seed).uniform(
        layer.contrast_floor, 1.0, size=_TEXTURE_TABLE_SIZE
    )
    cells = np.floor((x_mm - layer.center_mm) / layer.period_mm).astype(np.int64)
    return layer.brightness * table[np.mod(cells, _TEXTURE_TABLE_SIZE)]


def _composite(
    u_mm: Any,
    s_mm: Any,
    *,
    layers: tuple[LightFieldLayer, ...],
    focal_length_mm: float,
    image_distance_mm: float,
    background: float,
) -> tuple[NDArray[np.float64], NDArray[np.int_]]:
    u_array, s_array = np.broadcast_arrays(
        np.asarray(u_mm, dtype=np.float64), np.asarray(s_mm, dtype=np.float64)
    )
    radiance = np.full(u_array.shape, background, dtype=np.float64)
    # -1 marks rays that reach the background without meeting any layer.
    visible = np.full(u_array.shape, -1, dtype=np.int_)
    filled = np.zeros(u_array.shape, dtype=bool)
    betas = [layer_beta(layer, focal_length_mm, image_distance_mm) for layer in layers]
    # Nearer objects image farther back, so ascending beta is front-to-back order.
    for index in np.argsort(betas):
        layer = layers[index]
        beta = betas[index]
        # Transverse magnification of this layer: m = -v/Z = -f/(Z - f).
        magnification = -focal_length_mm / (layer.object_distance_mm - focal_length_mm)
        # Ray (u, s) crosses this layer's image plane at x_image; undo the
        # magnification to read the object-space texture coordinate.
        x_image = (s_array - u_array * (1.0 - beta)) / beta
        x_object = x_image / magnification
        covered = np.abs(x_object - layer.center_mm) <= layer.half_width_mm
        paint = covered & ~filled
        radiance = np.where(paint, _layer_texture(layer, x_object), radiance)
        visible = np.where(paint, int(index), visible)
        filled = filled | covered
    return radiance, visible


def sample_radiance(
    u_mm: Any,
    s_mm: Any,
    *,
    layers: tuple[LightFieldLayer, ...],
    focal_length_mm: float,
    image_distance_mm: float,
    background: float = 0.0,
) -> NDArray[np.float64]:
    """Evaluate the scene light field L(u, s) with front-to-back occlusion.

    ``u_mm`` and ``s_mm`` are broadcast against each other. Rays that miss every
    layer return ``background``. This is the single radiance sampler shared by
    the ray-space study and by the plenoptic camera model.
    """
    if not isinstance(layers, tuple) or not layers:
        raise ValueError("layers must be a non-empty tuple of LightFieldLayer")
    radiance, _visible = _composite(
        u_mm, s_mm, layers=layers,
        focal_length_mm=_finite(focal_length_mm, "focal_length_mm", positive=True),
        image_distance_mm=_finite(image_distance_mm, "image_distance_mm", positive=True),
        background=_finite(background, "background", nonnegative=True),
    )
    return radiance


@dataclass(frozen=True)
class LightFieldSpec:
    """Inputs for the flatland light-field study.

    The ray-space grid spans the full aperture in ``u`` and
    ``+/- field_half_width_mm`` in ``s``. The refocus sweep brackets the layer
    betas by ``refocus_margin_ratio`` so every layer passes through focus.
    """

    focal_length_mm: float = 50.0
    aperture_radius_mm: float = 6.0
    image_distance_mm: float = 52.0
    field_half_width_mm: float = 3.0
    layers: tuple[LightFieldLayer, ...] = (
        LightFieldLayer(
            object_distance_mm=1050.0, half_width_mm=24.0, center_mm=20.0,
            period_mm=1.0, brightness=1.0, seed=11, label="near texture",
        ),
        LightFieldLayer(
            object_distance_mm=1300.0, half_width_mm=32.5, center_mm=-27.5,
            period_mm=1.25, brightness=0.8, seed=22, label="focus target",
        ),
        LightFieldLayer(
            object_distance_mm=2600.0, half_width_mm=400.0, center_mm=0.0,
            period_mm=5.1, brightness=0.5, seed=33, label="far backdrop",
        ),
    )
    u_count: int = 129
    s_count: int = 513
    view_count: int = 5
    refocus_count: int = 41
    refocus_margin_ratio: float = 0.25
    integration_count: int = 97

    def __post_init__(self) -> None:
        for name in (
            "focal_length_mm", "aperture_radius_mm", "image_distance_mm", "field_half_width_mm",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name, positive=True))
        object.__setattr__(
            self, "refocus_margin_ratio",
            _finite(self.refocus_margin_ratio, "refocus_margin_ratio", positive=True),
        )
        for name, minimum in (
            ("u_count", 3), ("s_count", 3), ("view_count", 2),
            ("refocus_count", 3), ("integration_count", 3),
        ):
            object.__setattr__(self, name, _integer(getattr(self, name), name, minimum=minimum))
        if not isinstance(self.layers, (tuple, list)) or not self.layers:
            raise ValueError("layers must be a non-empty sequence of LightFieldLayer")
        layers = tuple(self.layers)
        if any(not isinstance(layer, LightFieldLayer) for layer in layers):
            raise ValueError("layers must contain only LightFieldLayer instances")
        object.__setattr__(self, "layers", layers)
        if self.image_distance_mm <= self.focal_length_mm:
            raise ValueError("image_distance_mm must exceed focal_length_mm")
        if self.view_count > self.u_count:
            raise ValueError("view_count cannot exceed u_count")
        # Validates every layer forms a real image in front of the sensor.
        for layer in layers:
            layer_beta(layer, self.focal_length_mm, self.image_distance_mm)

    @property
    def focus_distance_mm(self) -> float:
        """Object distance imaged sharply onto the reference plane."""
        return 1.0 / (1.0 / self.focal_length_mm - 1.0 / self.image_distance_mm)

    def to_dict(self) -> dict[str, Any]:
        """Return detached, JSON-compatible settings with an explicit schema version."""
        data: dict[str, Any] = {"schema_version": 1}
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name == "layers":
                data[field.name] = [layer.to_dict() for layer in value]
            else:
                data[field.name] = list(value) if isinstance(value, tuple) else value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LightFieldSpec":
        """Restore settings, rejecting missing, unknown, or version-mismatched fields."""
        expected = {field.name for field in fields(cls)} | {"schema_version"}
        if not isinstance(data, dict) or set(data) != expected:
            raise ValueError(f"Expected exactly these keys: {sorted(expected)}")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError("Unsupported schema_version; expected integer 1")
        if not isinstance(data["layers"], list):
            raise ValueError("layers must be a list in serialized data")
        values = {field.name: data[field.name] for field in fields(cls)}
        values["layers"] = tuple(LightFieldLayer.from_dict(item) for item in data["layers"])
        return cls(**values)


def _focus_distance(focal_mm: float, reference_mm: float, alpha: float) -> float | None:
    curvature = 1.0 / focal_mm - alpha / reference_mm
    if abs(curvature) < 1e-12:
        return None
    distance = 1.0 / curvature
    return float(distance) if np.isfinite(distance) and distance > 0 else None


def _erode(mask: NDArray[np.bool_], width: int) -> NDArray[np.bool_]:
    """Shrink a 1-D boolean region by ``width`` samples on both sides."""
    if width <= 0:
        return mask
    result = mask.copy()
    for offset in range(1, width + 1):
        pad = np.zeros(offset, dtype=bool)
        result &= np.concatenate([mask[offset:], pad])
        result &= np.concatenate([pad, mask[:-offset]])
    return result


def calculate_light_field(spec: LightFieldSpec = LightFieldSpec()) -> dict[str, Any]:
    """Calculate ray space, sub-aperture views, and a digital refocus sweep.

    The result is deterministic and contains only finite JSON-compatible values.
    Array index order is declared in the returned ``coordinates`` block.
    """
    if not isinstance(spec, LightFieldSpec):
        raise ValueError("spec must be a LightFieldSpec")

    focal = spec.focal_length_mm
    reference = spec.image_distance_mm
    u_grid = np.linspace(-spec.aperture_radius_mm, spec.aperture_radius_mm, spec.u_count)
    s_grid = np.linspace(-spec.field_half_width_mm, spec.field_half_width_mm, spec.s_count)

    def radiance(u_values: NDArray[np.float64], s_values: NDArray[np.float64]) -> NDArray[np.float64]:
        return sample_radiance(
            u_values, s_values, layers=spec.layers,
            focal_length_mm=focal, image_distance_mm=reference,
        )

    ray_space = radiance(u_grid[:, None], s_grid[None, :])

    betas = [layer_beta(layer, focal, reference) for layer in spec.layers]
    layer_rows = [
        {
            "label": layer.label,
            "object_distance_mm": float(layer.object_distance_mm),
            "image_distance_mm": float(reference / beta),
            "beta": float(beta),
            "ray_space_slope": float(1.0 - beta),
            # Shift of this layer between the two extreme sub-aperture views.
            "view_disparity_mm": float((1.0 - beta) * 2.0 * spec.aperture_radius_mm),
            "in_focus": bool(abs(beta - 1.0) < 1e-9),
        }
        for layer, beta in zip(spec.layers, betas)
    ]

    view_u = np.linspace(-spec.aperture_radius_mm, spec.aperture_radius_mm, spec.view_count)
    sub_aperture = radiance(view_u[:, None], s_grid[None, :])

    span = max(1e-9, max(betas) - min(betas))
    margin = spec.refocus_margin_ratio * span
    alphas = np.linspace(min(betas) - margin, max(betas) + margin, spec.refocus_count)
    if np.any(alphas <= 0):
        raise ValueError("refocus sweep produced a non-positive alpha; reduce refocus_margin_ratio")
    aperture_u = np.linspace(
        -spec.aperture_radius_mm, spec.aperture_radius_mm, spec.integration_count
    )
    # Shear then integrate over the aperture: s = alpha * x + u * (1 - alpha).
    sheared_s = (
        alphas[:, None, None] * s_grid[None, None, :]
        + aperture_u[None, :, None] * (1.0 - alphas[:, None, None])
    )
    photos = radiance(aperture_u[None, :, None], sheared_s).mean(axis=1)
    gradients = np.gradient(photos, s_grid, axis=1)
    sharpness = np.mean(gradients**2, axis=1)
    peak = float(sharpness.max())
    normalized = sharpness / peak if peak > 0 else np.zeros_like(sharpness)

    # Depth from focus: restrict the sharpness metric to the field region where
    # each layer is the front-most visible surface, seen from the aperture centre.
    _central, visible = _composite(
        np.zeros_like(s_grid), s_grid, layers=spec.layers,
        focal_length_mm=focal, image_distance_mm=reference, background=0.0,
    )
    regions = []
    sample_step = float(s_grid[1] - s_grid[0])
    for index, (layer, beta) in enumerate(zip(spec.layers, betas)):
        mask = visible == index
        if not bool(mask.any()):
            continue
        # An occlusion edge looks sharpest when the occluder, not the background,
        # is in focus. Pulling the region back by the widest defocus blur keeps
        # borrowed edges out of a layer's own sharpness measurement.
        blur_samples = int(np.ceil(
            max(abs(1.0 - value) for value in betas)
            * 2.0 * spec.aperture_radius_mm / sample_step
        ))
        interior = _erode(mask, blur_samples)
        edge_limited = not bool(interior.any())
        if edge_limited:
            interior = mask
        region_sharpness = np.mean(gradients[:, interior] ** 2, axis=1)
        region_peak = float(region_sharpness.max())
        recovered = float(alphas[int(np.argmax(region_sharpness))])
        regions.append({
            "label": layer.label,
            "beta": float(beta),
            "visible_fraction": float(mask.mean()),
            "interior_fraction": float(interior.mean()),
            # True when erosion removed the whole region, so the estimate below is
            # taken on edge-contaminated samples and should not be trusted.
            "edge_limited": edge_limited,
            "sharpness": region_sharpness.tolist(),
            "sharpness_normalized": (
                (region_sharpness / region_peak).tolist()
                if region_peak > 0 else np.zeros_like(region_sharpness).tolist()
            ),
            "recovered_alpha": recovered,
            "recovered_distance_mm": _focus_distance(focal, reference, recovered),
            "alpha_error": float(recovered - beta),
        })

    result: dict[str, Any] = {
        "schema_version": 1,
        "spec": spec.to_dict(),
        "coordinates": {
            "units": {"length": "mm", "angle": "rad"},
            "array_order": {
                "ray_space_radiance": "[u,s]",
                "sub_aperture_images": "[view,s]",
                "refocus_photos": "[alpha,s]",
            },
            "origin": "main lens plane at z=0; s measured on the reference image plane",
        },
        "geometry": {
            "focal_length_mm": float(focal),
            "image_distance_mm": float(reference),
            "aperture_radius_mm": float(spec.aperture_radius_mm),
            "focus_distance_mm": float(spec.focus_distance_mm),
            "working_f_number": float(reference / (2.0 * spec.aperture_radius_mm)),
        },
        "ray_space": {
            "u_mm": u_grid.tolist(),
            "s_mm": s_grid.tolist(),
            "radiance": ray_space.tolist(),
        },
        "layers": layer_rows,
        "sub_aperture": {
            "u_mm": view_u.tolist(),
            "s_mm": s_grid.tolist(),
            "images": sub_aperture.tolist(),
        },
        "refocus": {
            "alpha": alphas.tolist(),
            "focus_distance_mm": [_focus_distance(focal, reference, float(a)) for a in alphas],
            "s_mm": s_grid.tolist(),
            "photos": photos.tolist(),
            "sharpness": sharpness.tolist(),
            "sharpness_normalized": normalized.tolist(),
            "sharpest_alpha": float(alphas[int(np.argmax(sharpness))]),
            "regions": regions,
        },
    }
    # Catch accidental NumPy scalars, NaN, or infinity before crossing the seam.
    json.dumps(result, allow_nan=False)
    return result
