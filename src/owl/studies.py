"""AnyWidget adapters for the reusable numerical optics studies."""

from copy import deepcopy
from dataclasses import fields
from pathlib import Path
from typing import Any, ClassVar, Generic, TypeVar, cast

import anywidget
import numpy as np
import traitlets

from .aperture_study import ApertureStudySpec, calculate_aperture_study
from .stop_study import StopStudySpec, calculate_stop_study

__all__ = [
    "ApertureFocusStudy",
    "ApertureStudy",
    "PupilMapStudy",
    "RayWaveStudy",
    "StopRayStudy",
    "StopStudy",
]


SpecT = TypeVar("SpecT", ApertureStudySpec, StopStudySpec)


class _Study(anywidget.AnyWidget, Generic[SpecT]):
    """Shared atomic state management for a calculated study widget."""

    _esm = Path(__file__).parent / "static" / "studies.js"
    _css = Path(__file__).parent / "static" / "studies.css"

    view_kind = traitlets.Unicode().tag(sync=True)
    section = traitlets.Unicode("all").tag(sync=True)
    settings = traitlets.Dict().tag(sync=True)
    result = traitlets.Dict().tag(sync=True)
    error = traitlets.Unicode("").tag(sync=True)

    _spec_type: ClassVar[type[Any]]
    _calculate: ClassVar[Any]
    _default_section: ClassVar[str] = "all"
    _valid_sections: ClassVar[frozenset[str]]

    def __init__(self, spec: SpecT | None = None, *, section: str | None = None) -> None:
        if spec is None:
            spec = self._spec_type()
        if not isinstance(spec, self._spec_type):
            raise ValueError(f"spec must be a {self._spec_type.__name__}")
        if section is None:
            section = self._default_section
        settings, result = self._derive(self._spec_to_dict(cast(SpecT, spec)))
        self._updating = True
        self._valid_settings = deepcopy(settings)
        super().__init__(settings=settings, result=result, section=section)
        self._updating = False

    @traitlets.validate("section")
    def _validate_section(self, proposal: dict[str, Any]) -> str:
        section = proposal["value"]
        if section not in self._valid_sections:
            choices = ", ".join(sorted(self._valid_sections))
            raise ValueError(f"section must be one of: {choices}")
        return section

    @classmethod
    def _spec_to_dict(cls, spec: SpecT) -> dict[str, Any]:
        if isinstance(spec, StopStudySpec):
            return spec.to_dict()
        data: dict[str, Any] = {"schema_version": 1}
        for field in fields(spec):
            value = getattr(spec, field.name)
            data[field.name] = list(value) if isinstance(value, tuple) else value
        return data

    @classmethod
    def _spec_from_dict(cls, data: dict[str, Any]) -> SpecT:
        if cls._spec_type is StopStudySpec:
            return StopStudySpec.from_dict(data)  # type: ignore[return-value]
        expected = {field.name for field in fields(ApertureStudySpec)} | {"schema_version"}
        if not isinstance(data, dict) or set(data) != expected:
            raise ValueError(f"Expected exactly these keys: {sorted(expected)}")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError("Unsupported schema_version; expected integer 1")
        values = {field.name: data[field.name] for field in fields(ApertureStudySpec)}
        ratios = values["aperture_diameter_ratios"]
        if not isinstance(ratios, (list, tuple)):
            raise ValueError("aperture_diameter_ratios must be a sequence")
        values["aperture_diameter_ratios"] = tuple(ratios)
        return ApertureStudySpec(**values)  # type: ignore[return-value]

    @classmethod
    def _derive(cls, data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            spec = cls._spec_from_dict(data)
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                result = cls._calculate(spec)
        except ValueError:
            raise
        except (TypeError, ArithmeticError) as exc:
            raise ValueError(f"Invalid numerical study parameters: {exc}") from exc
        return cls._spec_to_dict(spec), result

    @traitlets.validate("settings")
    def _validate_settings(self, proposal: dict[str, Any]) -> dict[str, Any]:
        if self._updating:
            return proposal["value"]
        try:
            settings, result = self._derive(proposal["value"])
        except ValueError as exc:
            self.error = str(exc) or "Study calculation failed"
            return deepcopy(self._valid_settings)
        self._valid_settings = deepcopy(settings)
        with self.hold_sync():
            self.result = result
            self.error = ""
        return settings

    @property
    def spec(self) -> SpecT:
        """Return the last successfully validated immutable study specification."""
        return self._spec_from_dict(deepcopy(self._valid_settings))

    def to_dict(self) -> dict[str, Any]:
        """Return detached, strict-JSON-compatible settings."""
        return deepcopy(self._valid_settings)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_Study[SpecT]":
        """Restore a widget from complete settings, rejecting partial data."""
        settings, _ = cls._derive(data)
        return cls(cls._spec_from_dict(settings))


def _calculate_aperture_study_auto(spec: ApertureStudySpec) -> dict[str, Any]:
    return calculate_aperture_study(spec, backend="auto")


class ApertureStudy(_Study[ApertureStudySpec]):
    """Interactive view of :func:`calculate_aperture_study`."""

    view_kind = traitlets.Unicode("aperture_study").tag(sync=True)
    _valid_sections = frozenset({"all", "focus", "comparison"})
    _spec_type = ApertureStudySpec
    _calculate = staticmethod(_calculate_aperture_study_auto)


class ApertureFocusStudy(ApertureStudy):
    """Aperture study presenting only the Fresnel focus sweep."""

    _default_section = "focus"
    _valid_sections = frozenset({"focus"})


class RayWaveStudy(ApertureStudy):
    """Aperture study presenting only the ray and wave comparison."""

    _default_section = "comparison"
    _valid_sections = frozenset({"comparison"})


class StopStudy(_Study[StopStudySpec]):
    """Interactive view of :func:`calculate_stop_study`."""

    view_kind = traitlets.Unicode("stop_study").tag(sync=True)
    _valid_sections = frozenset({"all", "rays", "pupils"})
    _spec_type = StopStudySpec
    _calculate = staticmethod(calculate_stop_study)


class StopRayStudy(StopStudy):
    """Stop study presenting only stop geometry and ray fans."""

    _default_section = "rays"
    _valid_sections = frozenset({"rays"})


class PupilMapStudy(StopStudy):
    """Stop study presenting only exit-pupil maps."""

    _default_section = "pupils"
    _valid_sections = frozenset({"pupils"})
