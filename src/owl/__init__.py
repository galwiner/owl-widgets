"""Paraxial optics core; lengths are in millimetres unless otherwise named."""

from .aperture_study import ApertureStudySpec, calculate_aperture_study
from .bench import Bench
from .core import (
    Aperture,
    FreeSpace,
    GaussianBeam,
    GaussianTrace,
    Interface,
    Mirror,
    OpticalSystem,
    RayTrace,
    ThickLens,
    ThinLens,
)
from .cross_section import CrossSection
from .stop_study import StopStudySpec, calculate_stop_study
from .studies import (
    ApertureFocusStudy,
    ApertureStudy,
    PupilMapStudy,
    RayWaveStudy,
    StopRayStudy,
    StopStudy,
)
from .wave import cross_sections, longitudinal_section

__all__ = [
    "Aperture",
    "ApertureFocusStudy",
    "ApertureStudy",
    "ApertureStudySpec",
    "calculate_aperture_study",
    "Bench",
    "CrossSection",
    "cross_sections",
    "longitudinal_section",
    "FreeSpace",
    "GaussianBeam",
    "GaussianTrace",
    "Interface",

    "Mirror",

    "ThickLens",
    "OpticalSystem",
    "PupilMapStudy",
    "RayTrace",
    "RayWaveStudy",

    "StopRayStudy",
    "StopStudy",
    "StopStudySpec",
    "calculate_stop_study",
    "ThinLens",
]

__version__ = "0.1.0"
