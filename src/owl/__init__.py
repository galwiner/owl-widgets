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
from .lightfield import (
    LightFieldLayer,
    LightFieldSpec,
    calculate_light_field,
    layer_beta,
    sample_radiance,
)
from .plenoptic import PlenopticSpec, calculate_plenoptic, microlens_geometry
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
    "layer_beta",
    "LightFieldLayer",
    "LightFieldSpec",
    "calculate_light_field",
    "microlens_geometry",
    "Mirror",
    "PlenopticSpec",
    "calculate_plenoptic",
    "ThickLens",
    "OpticalSystem",
    "PupilMapStudy",
    "RayTrace",
    "RayWaveStudy",
    "sample_radiance",
    "StopRayStudy",
    "StopStudy",
    "StopStudySpec",
    "calculate_stop_study",
    "ThinLens",
]

__version__ = "0.1.0"
