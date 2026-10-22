"""Notebook optical bench; Python owns validation and all propagation."""

import pickle
from copy import deepcopy
from functools import lru_cache
from numbers import Real
from pathlib import Path
from typing import Any

import anywidget
import numpy as np
import traitlets

from .core import Aperture, FreeSpace, GaussianBeam, Interface, Mirror, OpticalSystem, ThickLens, ThinLens
from .frontend import _WIDGET_ESM
from .wave import cross_sections, longitudinal_section


_GAUSSIAN_SAMPLES_PER_GAP = 80


@lru_cache(maxsize=64)
def _cached_calculate(payload: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    return Bench._calculate(pickle.loads(payload))


class Bench(anywidget.AnyWidget):
    """Edit a sequential optical system in a notebook.

    ``ray_span_mm`` is the launch half-span of parallel rays. A single ray is
    launched on axis. The default Gaussian input waist is 0.1 mm at 550 nm.
    Assign a complete new ``settings`` dictionary to update the bench (nested
    in-place dict edits do not emit trait notifications). Invalid updates restore
    the last valid settings and leave ``result`` unchanged, with details in
    ``error``. Invalid constructor/from_dict arguments raise ValueError.

    Results contain interface-sampled rays (y_mm indexed by sample, then ray),
    a sampled Gaussian radius, element positions, and output-plane metrics.
    Both traces use the core's physical millimetre coordinates. Apertures mask
    rays; the Gaussian envelope remains an unclipped reference. Cross sections
    use scalar Fresnel FFT propagation with explicit grid/window controls and
    sampling warnings. Saved settings include the wave sampling configuration.
    """

    _esm = _WIDGET_ESM
    _css = Path(__file__).parent / "static" / "bench.css"

    view_kind = traitlets.Unicode("bench").tag(sync=True)
    settings = traitlets.Dict().tag(sync=True)
    result = traitlets.Dict().tag(sync=True)
    error = traitlets.Unicode("").tag(sync=True)

    def __init__(
        self,
        system: OpticalSystem,
        beam: GaussianBeam = GaussianBeam(waist_mm=0.1, wavelength_nm=550),
        ray_span_mm: float = 0.25,
        ray_count: int = 11,
        *,
        grid_size: int = 128,
        window_mm: float | None = None,
    ) -> None:
        if not isinstance(system, OpticalSystem) or not isinstance(beam, GaussianBeam):
            raise ValueError("Expected an OpticalSystem and a GaussianBeam")
        settings, result = self._derive({
            "system": system.to_dict(),
            "beam": beam.to_dict(),
            "ray_span_mm": ray_span_mm,
            "ray_count": ray_count,
            "wave": {"grid_size": grid_size, "window_mm": window_mm},
        })
        self._updating = True
        self._valid_settings = deepcopy(settings)
        super().__init__(settings=settings, result=result)
        self._updating = False

    @classmethod
    def _from_derived(
        cls, settings: dict[str, Any], result: dict[str, Any]
    ) -> "Bench":
        """Create a fresh widget model from trusted, precomputed data."""
        widget = cls.__new__(cls)
        widget._updating = True
        widget._valid_settings = deepcopy(settings)
        anywidget.AnyWidget.__init__(
            widget, settings=deepcopy(settings), result=deepcopy(result)
        )
        widget._updating = False
        return widget

    @staticmethod
    def _derive(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                return deepcopy(_cached_calculate(pickle.dumps(data)))
        except (TypeError, ArithmeticError) as exc:
            raise ValueError(f"Invalid optical parameters: {exc}") from exc

    @staticmethod
    def _calculate(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        keys = {"system", "beam", "ray_span_mm", "ray_count"}
        if not isinstance(data, dict) or set(data) not in (keys, keys | {"wave"}):
            raise ValueError(f"Expected settings keys {sorted(keys)} and optional wave")
        wave = data.get("wave", {"grid_size": 128, "window_mm": None})
        if not isinstance(wave, dict) or set(wave) != {"grid_size", "window_mm"}:
            raise ValueError("wave requires grid_size and window_mm")
        system = OpticalSystem.from_dict(data["system"])
        beam = GaussianBeam.from_dict(data["beam"])
        # Match the widget's nm/µm controls before propagation, not only on save.
        beam = GaussianBeam(
            waist_mm=round(float(beam.waist_mm), 3),
            wavelength_nm=round(float(beam.wavelength_nm)),
        )
        span = data["ray_span_mm"]
        if isinstance(span, (bool, np.bool_)) or not isinstance(span, Real):
            raise ValueError("ray_span_mm must be a finite nonnegative number")
        try:
            span = float(span)
        except OverflowError as exc:
            raise ValueError("ray_span_mm must be a finite nonnegative number") from exc
        if not np.isfinite(span) or span < 0:
            raise ValueError("ray_span_mm must be a finite nonnegative number")
        count = data["ray_count"]
        if isinstance(count, (bool, np.bool_)) or not isinstance(count, (int, np.integer)) or count < 1:
            raise ValueError("ray_count must be a positive integer")
        count = int(count)
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                # Scale a unit fan instead of subtracting potentially huge endpoints.
                heights = np.linspace(-1.0, 1.0, count) * span if count > 1 else np.zeros(1)
                rays = system.trace(np.vstack((heights, np.zeros(count))))
                gaussian = system.gaussian(beam, samples_per_gap=_GAUSSIAN_SAMPLES_PER_GAP)
        except ArithmeticError as exc:
            raise ValueError("Propagation failed; check the optical parameters") from exc
        elements = []
        sample = 0
        gaussian_sample = 0
        aperture_stop_index = None
        for index, element in enumerate(system.elements, start=1):
            start_z = float(rays.z_mm[sample])
            # A thick lens contributes entry, internal gap, and exit samples.
            sample += 3 if isinstance(element, ThickLens) else 1
            if isinstance(element, FreeSpace):
                label = f"Gap {index}: {element.distance_mm:g} mm"
            elif isinstance(element, ThinLens):
                label = f"Thin lens {index}: f = {element.focal_length_mm:g} mm"
            elif isinstance(element, Mirror):
                label = f"Mirror {index}: R = {element.radius_mm:g} mm"
            elif isinstance(element, Aperture):
                label = f"Aperture {index}: radius = {element.radius_mm:g} mm"
            elif isinstance(element, Interface):
                label = f"Interface {index}: R = {element.radius_mm:g} mm, n = {element.n1:g} → {element.n2:g}"
            else:
                label = f"Thick lens {index}: R₁ = {element.radius1_mm:g}, R₂ = {element.radius2_mm:g}, t = {element.thickness_mm:g} mm, n = {element.n:g}"
            elements.append({
                **element.to_dict(), "start_z_mm": start_z,
                "z_mm": float(rays.z_mm[sample]), "label": label,
            })
            if isinstance(element, Aperture) and aperture_stop_index is None:
                aperture_stop_index = gaussian_sample + 1
            if isinstance(element, FreeSpace):
                gaussian_sample += _GAUSSIAN_SAMPLES_PER_GAP if element.distance_mm else 1
            elif isinstance(element, ThickLens):
                gaussian_sample += (_GAUSSIAN_SAMPLES_PER_GAP + 2) if element.thickness_mm else 3
            else:
                gaussian_sample += 1
        settings = {
            "system": system.to_dict(),
            "beam": beam.to_dict(),
            "ray_span_mm": span,
            "ray_count": count,
            "wave": deepcopy(wave),
        }
        sections = cross_sections(system, beam, **wave)
        longitudinal = longitudinal_section(system, beam, **wave)
        settings["wave"] = {
            "grid_size": len(sections["x_mm"]),
            "window_mm": None if wave["window_mm"] is None else sections["window_mm"],
        }
        for plane, element in zip(sections["planes"][1:], elements):
            plane["label"] = element["label"]
        alive = rays.alive
        assert alive is not None  # RayTrace materializes the default mask in __post_init__.
        live_heights = rays.rays[-1, 0, alive[-1]]
        result = {
            "cross_sections": sections,
            "longitudinal": longitudinal,
            "rays": {"z_mm": rays.z_mm.tolist(), "y_mm": rays.rays[:, 0, :].tolist(), "alive": alive.tolist()},
            "gaussian": {
                "z_mm": gaussian.z_mm.tolist(),
                "radius_mm": gaussian.radius_mm.tolist(),
                "aperture_stop_index": aperture_stop_index,
            },
            "elements": elements,
            "metrics": {
                "length_mm": float(system.length_mm),
                "output_z_mm": system.output_z_mm,
                "output_n": system.output_n,
                "output_direction": system.output_direction,
                "output_radius_mm": float(gaussian.radius_mm[-1]),
                "output_ray_half_span_mm": float(np.max(np.abs(live_heights))) if live_heights.size else 0.0,
                "output_ray_count": int(live_heights.size),
                "transmission": sections["planes"][-1]["transmission"],
            },
        }
        return settings, result

    @traitlets.validate("settings")
    def _validate_settings(self, proposal: dict[str, Any]) -> dict[str, Any]:
        # Validation precedes traitlets' equality check (True == 1), and also
        # lets reassigning the last valid settings clear an earlier error.
        if self._updating:
            return proposal["value"]
        try:
            settings, result = self._derive(proposal["value"])
        except ValueError as exc:
            self.error = str(exc) or "Propagation failed; check the optical parameters"
            return deepcopy(self._valid_settings)
        self._valid_settings = deepcopy(settings)
        with self.hold_sync():
            self.result = result
            self.error = ""
        return settings

    @property
    def system(self) -> OpticalSystem:
        """The last successfully validated numerical system."""
        return OpticalSystem.from_dict(self._valid_settings["system"])

    @property
    def beam(self) -> GaussianBeam:
        """The last successfully validated numerical input beam."""
        return GaussianBeam.from_dict(self._valid_settings["beam"])

    def to_dict(self) -> dict[str, Any]:
        """Return detached, JSON-compatible full settings (not UI/trace state)."""
        return deepcopy(self._valid_settings)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Bench":
        """Restore full settings, rejecting invalid or unknown fields."""
        settings, _ = cls._derive(data)
        return cls(
            OpticalSystem.from_dict(settings["system"]),
            GaussianBeam.from_dict(settings["beam"]),
            settings["ray_span_mm"], settings["ray_count"],
            **settings["wave"],
        )
