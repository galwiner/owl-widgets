"""Unified flatland model of plenoptic 1.0 and 2.0 (focused plenoptic) cameras.

One geometry covers both designs. A thin main lens of focal length
``focal_length_mm`` and semi-aperture ``aperture_radius_mm`` sits at z = 0 and
images the in-focus object plane to z = ``image_distance_mm`` (written v0 below).
A microlens array of pitch d and focal length f_mu sits at z_mu, with the sensor
a distance b behind it. Every microlens obeys the thin-lens law 1/a + 1/b = 1/f_mu
for a conjugate plane a distance ``a`` in front of the array; the two camera
families differ only in which plane that is:

* ``"plenoptic_1"`` puts the array **on** the image plane (z_mu = v0) and focuses
  each microlens on the **main lens aperture** (a = v0). Each microimage is then
  a picture of the aperture, so position within a microimage is an angle and the
  microlens index is the only spatial coordinate.
* ``"keplerian"`` puts the array a distance ``microlens_offset_mm`` **behind**
  the image plane (a = +offset) and focuses each microlens on the **image**
  itself. Microimages are small inverted real pictures of a scene patch.
* ``"galilean"`` puts the array **in front of** the image plane (a = -offset),
  so the image is virtual and microimages are erect.

Sampling. A sensor pixel is integrated by tracing rays backwards through its own
microlens: for a position x_mu on that microlens the post-lens angle is
theta' = (p - x_mu) / b, so the pre-lens angle is
theta = theta' + (x_mu - s_k) / f_mu, giving u = x_mu - theta * z_mu and
s = u + theta * v0. Rays needing |u| > aperture_radius_mm are vignetted by the
main lens. This single trace stays well conditioned for every mode, and the set
of (u, s) it reaches is the pixel's sampling tile in ray space: axis aligned for
plenoptic 1.0 and sheared for the focused designs.

Rendering. Full-resolution rendering crops ``patch_pixels`` pixels from the
centre of each microimage and tiles the crops. Adjacent microimages view the
same conjugate point displaced by d * b / a, so the matched crop is
patch_pixels = pixels_per_lens * b / a and equals the microimage-to-microimage
disparity. Choosing a different crop renders a different plane: a crop of
mu' pixels tiles the plane at a' = d * b / mu' in front of the array, which is
how patch size doubles as both the refocus and the depth parameter.
All lengths are in millimetres.
"""

import json
from dataclasses import dataclass, fields
from numbers import Integral, Real
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .lightfield import LightFieldLayer, LightFieldSpec, layer_beta, sample_radiance

__all__ = ["PlenopticSpec", "calculate_plenoptic", "microlens_geometry"]

_MODES = ("plenoptic_1", "keplerian", "galilean")


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


def microlens_geometry(
    mode: str,
    *,
    image_distance_mm: float,
    microlens_focal_length_mm: float,
    microlens_offset_mm: float,
) -> dict[str, float]:
    """Return the microlens conjugate distance ``a``, gap ``b``, and array position.

    ``a`` is signed: positive means the conjugate plane lies in front of the
    array (a real object for the microlens), negative means behind it (virtual).
    """
    if mode not in _MODES:
        raise ValueError(f"mode must be one of {_MODES}")
    reference = _finite(image_distance_mm, "image_distance_mm", positive=True)
    focal = _finite(microlens_focal_length_mm, "microlens_focal_length_mm", positive=True)
    offset = _finite(microlens_offset_mm, "microlens_offset_mm", nonnegative=True)
    if mode == "plenoptic_1":
        # Array on the image plane, each microlens focused on the aperture plane.
        array_z = reference
        conjugate_a = reference
    elif mode == "keplerian":
        # Array behind the image plane; the microlens relays a real image.
        if offset <= focal:
            raise ValueError("microlens_offset_mm must exceed microlens_focal_length_mm (keplerian)")
        array_z = reference + offset
        conjugate_a = offset
    else:
        # Array in front of the image plane; the microlens sees a virtual object.
        if offset <= 0:
            raise ValueError("microlens_offset_mm must be positive (galilean)")
        array_z = reference - offset
        conjugate_a = -offset
    if array_z <= 0:
        raise ValueError("microlens array must sit at a positive z; reduce microlens_offset_mm")
    if abs(conjugate_a - focal) < 1e-12:
        raise ValueError("microlens conjugate is degenerate; change microlens_offset_mm")
    gap_b = focal * conjugate_a / (conjugate_a - focal)
    if not np.isfinite(gap_b) or gap_b <= 0:
        raise ValueError("microlens geometry gives a non-physical sensor gap")
    return {
        "conjugate_a_mm": float(conjugate_a),
        "gap_b_mm": float(gap_b),
        "array_z_mm": float(array_z),
        "magnification": float(gap_b / abs(conjugate_a)),
    }


@dataclass(frozen=True)
class PlenopticSpec:
    """Inputs for the plenoptic camera study.

    The default scene is the shared :class:`LightFieldSpec` layer stack, so the
    ray-space study and this camera see the same three depths. ``pixels_per_lens``
    fixes the sensor pitch at ``microlens_pitch_mm / pixels_per_lens``, which
    keeps microimages exactly tiled on the pixel grid.
    """

    mode: str = "keplerian"
    focal_length_mm: float = 50.0
    aperture_radius_mm: float = 6.0
    image_distance_mm: float = 52.0
    microlens_pitch_mm: float = 0.131
    microlens_focal_length_mm: float = 0.5
    microlens_offset_mm: float = 3.0
    lenslet_count: int = 41
    pixels_per_lens: int = 60
    layers: tuple[LightFieldLayer, ...] = LightFieldSpec().layers
    lenslet_sample_count: int = 25
    pixel_sample_count: int = 3
    patch_sweep_max: int = 24
    depth_min_overlap_pixels: int = 12
    depth_baseline_count: int = 4
    depth_shift_step_pixels: float = 0.5
    depth_min_correlation: float = 0.6
    depth_min_peak_ratio: float = 1.1

    def __post_init__(self) -> None:
        if self.mode not in _MODES:
            raise ValueError(f"mode must be one of {_MODES}")
        for name in (
            "focal_length_mm", "aperture_radius_mm", "image_distance_mm",
            "microlens_pitch_mm", "microlens_focal_length_mm",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name, positive=True))
        object.__setattr__(
            self, "microlens_offset_mm",
            _finite(self.microlens_offset_mm, "microlens_offset_mm", nonnegative=True),
        )
        object.__setattr__(
            self, "depth_min_correlation",
            _finite(self.depth_min_correlation, "depth_min_correlation", nonnegative=True),
        )
        object.__setattr__(
            self, "depth_min_peak_ratio",
            _finite(self.depth_min_peak_ratio, "depth_min_peak_ratio", positive=True),
        )
        for name, minimum in (
            ("lenslet_count", 3), ("pixels_per_lens", 2),
            ("lenslet_sample_count", 3), ("pixel_sample_count", 1), ("patch_sweep_max", 2),
            ("depth_min_overlap_pixels", 2), ("depth_baseline_count", 1),
        ):
            object.__setattr__(self, name, _integer(getattr(self, name), name, minimum=minimum))
        object.__setattr__(
            self, "depth_shift_step_pixels",
            _finite(self.depth_shift_step_pixels, "depth_shift_step_pixels", positive=True),
        )
        if not isinstance(self.layers, (tuple, list)) or not self.layers:
            raise ValueError("layers must be a non-empty sequence of LightFieldLayer")
        layers = tuple(self.layers)
        if any(not isinstance(layer, LightFieldLayer) for layer in layers):
            raise ValueError("layers must contain only LightFieldLayer instances")
        object.__setattr__(self, "layers", layers)
        if self.image_distance_mm <= self.focal_length_mm:
            raise ValueError("image_distance_mm must exceed focal_length_mm")
        if self.patch_sweep_max > self.pixels_per_lens:
            raise ValueError("patch_sweep_max cannot exceed pixels_per_lens")
        if self.depth_min_overlap_pixels >= self.pixels_per_lens:
            raise ValueError("depth_min_overlap_pixels must be below pixels_per_lens")
        # Raises when the requested array placement is not physically realizable.
        microlens_geometry(
            self.mode,
            image_distance_mm=self.image_distance_mm,
            microlens_focal_length_mm=self.microlens_focal_length_mm,
            microlens_offset_mm=self.microlens_offset_mm,
        )
        for layer in layers:
            layer_beta(layer, self.focal_length_mm, self.image_distance_mm)

    @property
    def pixel_pitch_mm(self) -> float:
        """Sensor pitch implied by an exact number of pixels per microlens."""
        return self.microlens_pitch_mm / self.pixels_per_lens

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
    def from_dict(cls, data: dict[str, Any]) -> "PlenopticSpec":
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


def _object_distance(focal_mm: float, image_v_mm: float) -> float | None:
    curvature = 1.0 / focal_mm - 1.0 / image_v_mm
    if curvature <= 1e-12:
        return None
    return float(1.0 / curvature)


def calculate_plenoptic(spec: PlenopticSpec = PlenopticSpec()) -> dict[str, Any]:
    """Simulate the raw sensor image and render it at both resolutions.

    The result is deterministic and contains only finite JSON-compatible values.
    Array index order is declared in the returned ``coordinates`` block.
    """
    if not isinstance(spec, PlenopticSpec):
        raise ValueError("spec must be a PlenopticSpec")

    focal = spec.focal_length_mm
    reference = spec.image_distance_mm
    pitch = spec.microlens_pitch_mm
    micro_focal = spec.microlens_focal_length_mm
    geometry = microlens_geometry(
        spec.mode,
        image_distance_mm=reference,
        microlens_focal_length_mm=micro_focal,
        microlens_offset_mm=spec.microlens_offset_mm,
    )
    conjugate_a = geometry["conjugate_a_mm"]
    gap_b = geometry["gap_b_mm"]
    array_z = geometry["array_z_mm"]
    pixel_pitch = spec.pixel_pitch_mm

    centers = (np.arange(spec.lenslet_count) - (spec.lenslet_count - 1) / 2.0) * pitch
    pixel_offsets = (np.arange(spec.pixels_per_lens) - (spec.pixels_per_lens - 1) / 2.0) * pixel_pitch

    # Integrate each pixel over its own width and over its microlens aperture.
    sub_pixel = np.linspace(-0.5, 0.5, spec.pixel_sample_count) * pixel_pitch
    lens_samples = np.linspace(-0.5, 0.5, spec.lenslet_sample_count) * pitch
    sensor_p = centers[:, None, None, None] + pixel_offsets[None, :, None, None] + sub_pixel[None, None, :, None]
    x_micro = centers[:, None, None, None] + lens_samples[None, None, None, :]
    theta_out = (sensor_p - x_micro) / gap_b
    theta_in = theta_out + (x_micro - centers[:, None, None, None]) / micro_focal
    u_mm = x_micro - theta_in * array_z
    s_mm = u_mm + theta_in * reference
    radiance = sample_radiance(
        u_mm, s_mm, layers=spec.layers,
        focal_length_mm=focal, image_distance_mm=reference,
    )
    # Rays outside the main aperture are blocked, which produces the real
    # microimage falloff rather than a flat, artificially uniform microimage.
    inside = np.abs(u_mm) <= spec.aperture_radius_mm
    raw = np.where(inside, radiance, 0.0).mean(axis=(2, 3))
    aperture_fill = inside.mean(axis=(2, 3))

    # Ray-space sampling tiles: corners of the (u, s) parallelogram per pixel.
    corner_p = np.array([-0.5, -0.5, 0.5, 0.5]) * pixel_pitch
    corner_x = np.array([-0.5, 0.5, 0.5, -0.5]) * pitch
    tile_p = centers[:, None, None] + pixel_offsets[None, :, None] + corner_p[None, None, :]
    tile_x = centers[:, None, None] + corner_x[None, None, :]
    tile_theta = (tile_p - tile_x) / gap_b + (tile_x - centers[:, None, None]) / micro_focal
    tile_u = tile_x - tile_theta * array_z
    tile_s = tile_u + tile_theta * reference

    microimage_width = 2.0 * spec.aperture_radius_mm * gap_b / array_z
    matched_patch = spec.pixels_per_lens * gap_b / abs(conjugate_a)

    def render(patch_pixels: int) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        start = (spec.pixels_per_lens - patch_pixels) // 2
        patch = raw[:, start:start + patch_pixels]
        # Keplerian and plenoptic-1 microimages are inverted; Galilean are erect.
        if conjugate_a > 0:
            patch = patch[:, ::-1]
        sample_step = pitch / patch_pixels
        index_offsets = np.arange(patch_pixels, dtype=np.float64) - (patch_pixels - 1) / 2.0
        positions = centers[:, None] + index_offsets[None, :] * sample_step
        return patch.reshape(-1), positions.reshape(-1)

    sweep = []
    best_patch_pixels = 1
    best_seam_ratio = np.inf
    for patch_pixels in range(1, spec.patch_sweep_max + 1):
        image, positions = render(patch_pixels)
        blocks = image.reshape(spec.lenslet_count, patch_pixels)
        conjugate = pitch * gap_b / (patch_pixels * pixel_pitch)
        plane_z = array_z - conjugate
        # A correct patch size joins neighbouring crops seamlessly, so compare the
        # jump across each seam with the ordinary sample-to-sample step inside a
        # crop. The ratio is free of sampling scale; a wrong size shows a fence.
        seam_step = blocks[:-1, -1] - blocks[1:, 0]
        interior = np.diff(blocks, axis=1)
        interior_scale = float(np.mean(interior**2)) if patch_pixels > 1 else 0.0
        seam_scale = float(np.mean(seam_step**2))
        seam_ratio = seam_scale / interior_scale if interior_scale > 1e-15 else None
        if seam_ratio is not None and seam_ratio < best_seam_ratio:
            best_seam_ratio, best_patch_pixels = seam_ratio, patch_pixels
        sweep.append({
            "patch_pixels": int(patch_pixels),
            "rendered_pixel_count": int(image.size),
            "conjugate_a_mm": float(conjugate),
            "plane_z_mm": float(plane_z),
            "object_distance_mm": _object_distance(focal, plane_z) if plane_z > focal else None,
            "seam_ratio": seam_ratio,
            "image": image.tolist(),
            "position_mm": positions.tolist(),
        })

    # Plenoptic 2.0 depth: neighbouring microimages view the same conjugate point
    # displaced by d * b / a per unit of lenslet spacing, so the shift that aligns
    # them measures depth. A single pair is ambiguous on repetitive or weakly
    # textured content, but the array supplies many baselines at once: microlens
    # k against k+n must agree at n times the disparity. Scoring all baselines
    # together suppresses the false peaks that defeat a single pair.
    # Overlaps must also stay wide: mean-centred correlation of two samples is
    # exactly +/-1 for any pair, which would peg the search at the extreme shifts.
    per_lens = spec.pixels_per_lens
    positions = np.arange(per_lens, dtype=np.float64)
    max_shift = per_lens - spec.depth_min_overlap_pixels
    step = spec.depth_shift_step_pixels
    candidates = np.concatenate([
        -np.arange(1.0, max_shift + step, step)[::-1],
        np.arange(1.0, max_shift + step, step),
    ])

    def pair_score(left: NDArray[np.float64], right: NDArray[np.float64], shift: float) -> float:
        """Normalized correlation of two microimages at a fractional pixel shift."""
        target = positions + shift
        inside = (target >= 0.0) & (target <= per_lens - 1.0)
        if int(inside.sum()) < spec.depth_min_overlap_pixels:
            return float("nan")
        a_part = left[inside]
        b_part = np.interp(target[inside], positions, right)
        a_centered = a_part - a_part.mean()
        b_centered = b_part - b_part.mean()
        norm = float(np.sqrt(np.sum(a_centered**2) * np.sum(b_centered**2)))
        return float(np.sum(a_centered * b_centered) / norm) if norm > 1e-12 else float("nan")

    depth_map = []
    for index in range(spec.lenslet_count - 1):
        available = [
            offset for offset in range(1, spec.depth_baseline_count + 1)
            if index + offset < spec.lenslet_count
        ]
        # A baseline is only usable while n * shift still leaves enough overlap, so
        # the count of usable baselines is itself bounded by a / b, the angular
        # sampling. Require at least two whenever two exist, so that no candidate
        # can win on a single easy short-baseline match.
        required = min(2, len(available))
        scores = np.full(candidates.size, np.nan)
        used = np.zeros(candidates.size, dtype=np.int_)
        for position, shift in enumerate(candidates):
            values = [
                value for offset in available
                if np.isfinite(value := pair_score(raw[index], raw[index + offset], float(shift) * offset))
            ]
            if len(values) >= required:
                scores[position] = float(np.mean(values))
                used[position] = len(values)
        if not bool(np.any(np.isfinite(scores))):
            depth_map.append({
                "center_mm": float(centers[index]),
                "baselines_used": 0,
                "best_shift_pixels": None, "correlation": None, "peak_ratio": None,
                "confident": False, "conjugate_a_mm": None, "object_distance_mm": None,
            })
            continue
        best = int(np.nanargmax(scores))
        shift = float(candidates[best])
        conjugate = pitch * gap_b / (shift * pixel_pitch) if abs(shift) > 1e-9 else None
        plane_z = array_z - conjugate if conjugate is not None else None
        # Confidence: how far the winning peak stands above the best rival peak
        # at least two pixels away. Ambiguous or untextured regions score near 1.
        rivals = scores[np.abs(candidates - shift) >= 2.0]
        rivals = rivals[np.isfinite(rivals)]
        runner_up = float(rivals.max()) if rivals.size else 0.0
        correlation = float(scores[best])
        peak_ratio = correlation / runner_up if runner_up > 1e-6 else float("inf")
        depth_map.append({
            "center_mm": float(centers[index]),
            "baselines_used": int(used[best]),
            "best_shift_pixels": shift,
            "correlation": correlation,
            "peak_ratio": peak_ratio if np.isfinite(peak_ratio) else None,
            "confident": bool(
                correlation >= spec.depth_min_correlation
                and peak_ratio >= spec.depth_min_peak_ratio
            ),
            "conjugate_a_mm": float(conjugate) if conjugate is not None else None,
            "object_distance_mm": (
                _object_distance(focal, plane_z)
                if plane_z is not None and plane_z > focal else None
            ),
        })

    layer_rows = []
    for layer in spec.layers:
        beta = layer_beta(layer, focal, reference)
        image_v = reference / beta
        conjugate = array_z - image_v
        # a = 0 puts the layer image on the array itself: infinite disparity, so the
        # microimages carry only angular information about it.
        shift = (
            float(spec.pixels_per_lens * gap_b / conjugate) if abs(conjugate) > 1e-9 else None
        )
        # Microimage depth of field: this layer focuses at b' behind the microlens,
        # so a sensor at b records a blur of d * |b - b'| / b'. Once that blur
        # exceeds the texture detail inside the microimage, correspondence for this
        # depth fails no matter how many baselines are combined.
        images_it = bool(conjugate > micro_focal or conjugate < 0.0)
        blur_pixels = None
        cell_pixels = None
        if images_it and abs(conjugate - micro_focal) > 1e-12:
            focused_b = micro_focal * conjugate / (conjugate - micro_focal)
            if abs(focused_b) > 1e-12:
                blur_pixels = float(pitch * abs(gap_b - focused_b) / abs(focused_b) / pixel_pitch)
        if abs(conjugate) > 1e-9:
            # Texture cell as it lands inside a microimage, for comparison with blur.
            image_period = layer.period_mm * focal / (layer.object_distance_mm - focal)
            cell_pixels = float(image_period * gap_b / abs(conjugate) / pixel_pitch)
        layer_rows.append({
            "label": layer.label,
            "object_distance_mm": float(layer.object_distance_mm),
            "image_z_mm": float(image_v),
            "conjugate_a_mm": float(conjugate),
            # Signed disparity between neighbouring microimages for this depth.
            "expected_shift_pixels": shift,
            "microimage_blur_pixels": blur_pixels,
            "texture_cell_pixels": cell_pixels,
            "microimage_detail_resolved": bool(
                blur_pixels is not None and cell_pixels is not None and blur_pixels < cell_pixels
            ),
            # A microlens forms a usable image only for a real object beyond its
            # focal length, or for a virtual object behind the array.
            "microlens_images_it": images_it,
            "disparity_resolvable": bool(
                shift is not None and 1.0 <= abs(shift) < spec.pixels_per_lens
            ),
        })

    result: dict[str, Any] = {
        "schema_version": 1,
        "spec": spec.to_dict(),
        "coordinates": {
            "units": {"length": "mm", "angle": "rad"},
            "array_order": {
                "raw_sensor": "[lenslet,pixel]",
                "aperture_fill": "[lenslet,pixel]",
                "tile_u_mm": "[lenslet,pixel,corner]",
                "sub_aperture_images": "[pixel,lenslet]",
            },
            "origin": "main lens plane at z=0; u on the lens plane, s on the image plane",
        },
        "geometry": {
            "mode": spec.mode,
            "focal_length_mm": float(focal),
            "aperture_radius_mm": float(spec.aperture_radius_mm),
            "image_distance_mm": float(reference),
            "array_z_mm": float(array_z),
            "conjugate_a_mm": float(conjugate_a),
            "gap_b_mm": float(gap_b),
            "microlens_magnification": float(geometry["magnification"]),
            "microlens_pitch_mm": float(pitch),
            "pixel_pitch_mm": float(pixel_pitch),
            "main_f_number": float(reference / (2.0 * spec.aperture_radius_mm)),
            "microlens_f_number": float(gap_b / pitch),
            "microimage_width_mm": float(microimage_width),
            "microimage_fill_ratio": float(microimage_width / pitch),
            # Pitch that would make microimages exactly abut for this geometry.
            "matched_pitch_mm": float(2.0 * spec.aperture_radius_mm * gap_b / array_z),
            "matched_patch_pixels": float(matched_patch),
            "total_pixel_count": int(spec.lenslet_count * spec.pixels_per_lens),
            "spatial_samples_plenoptic_1": int(spec.lenslet_count),
            "angular_samples_plenoptic_1": int(spec.pixels_per_lens),
            "spatial_samples_matched": float(spec.lenslet_count * matched_patch),
            "angular_samples_matched": (
                float(spec.pixels_per_lens / matched_patch) if matched_patch > 0 else None
            ),
        },
        "raw_sensor": {
            "lenslet_center_mm": centers.tolist(),
            "pixel_offset_mm": pixel_offsets.tolist(),
            "values": raw.tolist(),
            "aperture_fill": aperture_fill.tolist(),
        },
        "sampling_tiles": {
            "tile_u_mm": tile_u.tolist(),
            "tile_s_mm": tile_s.tolist(),
        },
        "sub_aperture": {
            "pixel_offset_mm": pixel_offsets.tolist(),
            "lenslet_center_mm": centers.tolist(),
            "images": raw.T.tolist(),
        },
        "layers": layer_rows,
        "render": {
            "matched_patch_pixels": int(max(1, round(matched_patch))),
            "best_seam_patch_pixels": int(best_patch_pixels),
            "sweep": sweep,
        },
        "depth": {
            "shift_candidates_pixels": candidates.tolist(),
            "baseline_count": int(spec.depth_baseline_count),
            "estimates": depth_map,
        },
    }
    # Catch accidental NumPy scalars, NaN, or infinity before crossing the seam.
    json.dumps(result, allow_nan=False)
    return result
