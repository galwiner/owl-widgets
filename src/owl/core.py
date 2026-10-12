"""ABCD optics with local ray coordinates (height_mm, angle_rad), input in air.

Matrices act on column vectors in encounter order; reverse encounters require
user-supplied surface signs and indices. Mirrors flip only the direction of z;
gaps advance along the positive optical path. Gaussian beams use local q with
w**2 = -(wavelength_mm / n) / (pi * imag(1/q)).
Serialization is JSON-compatible and rejects unknown or missing keys.
"""

from dataclasses import dataclass
from numbers import Real
from typing import Any

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "FreeSpace", "ThinLens", "Interface", "Mirror", "ThickLens", "GaussianBeam", "OpticalSystem",
    "RayTrace", "GaussianTrace", "Aperture",
]


def _finite(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real number") from exc
    if not np.isfinite(result):
        raise ValueError(f"{name} must be a finite real number")
    return result


def _radius(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a nonzero real radius (infinity for flat)")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"Invalid {name}") from exc
    if np.isnan(result) or result == 0:
        raise ValueError(f"{name} must be nonzero and not NaN (infinity for flat)")
    return result


def _schema(data: Any, keys: set[str], *, versioned: bool = False) -> None:
    if not isinstance(data, dict) or set(data) != keys:
        raise ValueError(f"Expected exactly these keys: {sorted(keys)}")
    if versioned and (type(data["schema_version"]) is not int or data["schema_version"] != 1):
        raise ValueError("Unsupported schema_version; expected integer 1")


def _readonly(value: Any, dtype: Any) -> NDArray:
    array = np.array(value, dtype=dtype, copy=True)
    if not np.all(np.isfinite(array)):
        raise ValueError("Propagation produced non-finite values")
    # Immutable bytes also prevent callers from re-enabling NumPy's write flag.
    return np.frombuffer(array.tobytes(), dtype=array.dtype).reshape(array.shape)


@dataclass(frozen=True)
class FreeSpace:
    distance_mm: float

    def __post_init__(self) -> None:
        value = _finite(self.distance_mm, "distance_mm")
        if value < 0:
            raise ValueError("distance_mm must be nonnegative")
        object.__setattr__(self, "distance_mm", value)

    def matrix(self) -> NDArray[np.float64]:
        return np.array([[1.0, self.distance_mm], [0.0, 1.0]])

    def to_dict(self) -> dict[str, Any]:
        return {"type": "free_space", "distance_mm": self.distance_mm}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FreeSpace":
        _schema(data, {"type", "distance_mm"})
        if data["type"] != "free_space":
            raise ValueError("Expected type free_space")
        return cls(data["distance_mm"])


@dataclass(frozen=True)
class Aperture:
    """Circular hard opening, including its boundary; coordinates are in mm."""

    radius_mm: float
    x_mm: float = 0.0
    y_mm: float = 0.0

    def __post_init__(self) -> None:
        for name in ("radius_mm", "x_mm", "y_mm"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.radius_mm <= 0:
            raise ValueError("radius_mm must be positive")

    def matrix(self) -> NDArray[np.float64]:
        return np.eye(2)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "aperture", "radius_mm": self.radius_mm, "x_mm": self.x_mm, "y_mm": self.y_mm}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Aperture":
        _schema(data, {"type", "radius_mm", "x_mm", "y_mm"})
        if data["type"] != "aperture":
            raise ValueError("Expected type aperture")
        return cls(data["radius_mm"], data["x_mm"], data["y_mm"])


@dataclass(frozen=True)
class ThinLens:
    focal_length_mm: float

    def __post_init__(self) -> None:
        value = _finite(self.focal_length_mm, "focal_length_mm")
        if value == 0:
            raise ValueError("focal_length_mm must be nonzero")
        object.__setattr__(self, "focal_length_mm", value)

    def matrix(self) -> NDArray[np.float64]:
        return np.array([[1.0, 0.0], [-1.0 / self.focal_length_mm, 1.0]])

    def to_dict(self) -> dict[str, Any]:
        return {"type": "thin_lens", "focal_length_mm": self.focal_length_mm}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThinLens":
        _schema(data, {"type", "focal_length_mm"})
        if data["type"] != "thin_lens":
            raise ValueError("Expected type thin_lens")
        return cls(data["focal_length_mm"])


@dataclass(frozen=True)
class Interface:
    radius_mm: float
    n1: float
    n2: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "radius_mm", _radius(self.radius_mm, "radius_mm"))
        object.__setattr__(self, "n1", _finite(self.n1, "n1"))
        object.__setattr__(self, "n2", _finite(self.n2, "n2"))
        if self.n1 <= 0 or self.n2 <= 0:
            raise ValueError("Refractive indices must be positive")

    def matrix(self) -> NDArray[np.float64]:
        # Refraction at a curved surface. R > 0 = center of curvature downstream.
        c = (self.n1 - self.n2) / self.n2 / self.radius_mm
        return np.array([[1.0, 0.0], [c, self.n1 / self.n2]])

    def to_dict(self) -> dict[str, Any]:
        return {"type": "interface", "radius_mm": self.radius_mm if np.isfinite(self.radius_mm) else None, "n1": self.n1, "n2": self.n2}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Interface":
        _schema(data, {"type", "radius_mm", "n1", "n2"})
        if data["type"] != "interface":
            raise ValueError("Expected type interface")
        return cls(np.inf if data["radius_mm"] is None else data["radius_mm"], data["n1"], data["n2"])


@dataclass(frozen=True)
class Mirror:
    radius_mm: float = np.inf

    def __post_init__(self) -> None:
        object.__setattr__(self, "radius_mm", _radius(self.radius_mm, "radius_mm"))

    def matrix(self) -> NDArray[np.float64]:
        # Mirror of radius R behaves like a lens of f=R/2. R > 0 is concave.
        c = -2.0 / self.radius_mm
        return np.array([[1.0, 0.0], [c, 1.0]])

    def to_dict(self) -> dict[str, Any]:
        return {"type": "mirror", "radius_mm": self.radius_mm if np.isfinite(self.radius_mm) else None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Mirror":
        _schema(data, {"type", "radius_mm"})
        if data["type"] != "mirror":
            raise ValueError("Expected type mirror")
        return cls(np.inf if data["radius_mm"] is None else data["radius_mm"])


@dataclass(frozen=True)
class ThickLens:
    radius1_mm: float
    radius2_mm: float
    thickness_mm: float
    n: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "radius1_mm", _radius(self.radius1_mm, "radius1_mm"))
        object.__setattr__(self, "radius2_mm", _radius(self.radius2_mm, "radius2_mm"))
        object.__setattr__(self, "thickness_mm", _finite(self.thickness_mm, "thickness_mm"))
        object.__setattr__(self, "n", _finite(self.n, "n"))
        if self.thickness_mm < 0:
            raise ValueError("thickness_mm must be nonnegative")
        if self.n <= 0:
            raise ValueError("n must be positive")

    def matrix(self) -> NDArray[np.float64]:
        # Composed matrix: exit interface (n -> 1) @ free gap (n) @ entry interface (1 -> n)
        m1 = Interface(self.radius1_mm, 1.0, self.n).matrix()
        m2 = FreeSpace(self.thickness_mm).matrix()
        m3 = Interface(self.radius2_mm, self.n, 1.0).matrix()
        return m3 @ m2 @ m1

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "thick_lens",
            "radius1_mm": self.radius1_mm if np.isfinite(self.radius1_mm) else None,
            "radius2_mm": self.radius2_mm if np.isfinite(self.radius2_mm) else None,
            "thickness_mm": self.thickness_mm,
            "n": self.n,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThickLens":
        _schema(data, {"type", "radius1_mm", "radius2_mm", "thickness_mm", "n"})
        if data["type"] != "thick_lens":
            raise ValueError("Expected type thick_lens")
        return cls(
            np.inf if data["radius1_mm"] is None else data["radius1_mm"],
            np.inf if data["radius2_mm"] is None else data["radius2_mm"],
            data["thickness_mm"], data["n"],
        )


@dataclass(frozen=True)
class GaussianBeam:
    """An M²=1 beam with its input waist at z=0 in air."""

    waist_mm: float
    wavelength_nm: float

    def __post_init__(self) -> None:
        for name in ("waist_mm", "wavelength_nm"):
            value = _finite(getattr(self, name), name)
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)

    @property
    def wavelength_mm(self) -> float:
        return self.wavelength_nm * 1e-6

    @property
    def rayleigh_range_mm(self) -> float:
        return float(np.pi * self.waist_mm * self.waist_mm / self.wavelength_mm)

    @property
    def q_mm(self) -> complex:
        return complex(0, self.rayleigh_range_mm)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "waist_mm": self.waist_mm, "wavelength_nm": self.wavelength_nm}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GaussianBeam":
        _schema(data, {"schema_version", "waist_mm", "wavelength_nm"}, versioned=True)
        return cls(data["waist_mm"], data["wavelength_nm"])


def _trace_medium(trace: Any) -> None:
    for name in ("n", "s"):
        value = getattr(trace, name)
        if value is None:
            value = np.ones(trace.z_mm.shape)
        incoming = np.asarray(value)
        if incoming.dtype.kind not in "iuf":
            raise ValueError(f"{name} must contain real numbers")
        array = _readonly(incoming, np.float64)
        if array.shape != trace.z_mm.shape:
            raise ValueError("n and s arrays must have the same shape as z_mm")
        if name == "n" and np.any(array <= 0):
            raise ValueError("n must be positive")
        if name == "s" and np.any((array != 1) & (array != -1)):
            raise ValueError("s must be +1 or -1")
        object.__setattr__(trace, name, array)


@dataclass(frozen=True, eq=False)
class RayTrace:
    """Interface samples: z_mm (S,), rays (S, 2, N), n/s (S,), alive (S, N).

        Dead rays retain finite geometric coordinates; alive defaults to all true.
        """

    z_mm: NDArray[np.float64]
    rays: NDArray[np.float64]
    n: NDArray[np.float64] | None = None
    s: NDArray[np.float64] | None = None
    alive: NDArray[np.bool_] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "z_mm", _readonly(self.z_mm, np.float64))
        object.__setattr__(self, "rays", _readonly(self.rays, np.float64))
        if self.z_mm.ndim != 1 or self.rays.ndim != 3 or self.rays.shape[:2] != (len(self.z_mm), 2):
            raise ValueError("Expected z_mm (S,) and rays (S, 2, N)")
        shape = (len(self.z_mm), self.rays.shape[2])
        alive = np.ones(shape, dtype=bool) if self.alive is None else np.asarray(self.alive)
        if alive.shape != shape or alive.dtype.kind != "b":
            raise ValueError("alive must be a boolean array of shape (S, N)")
        object.__setattr__(self, "alive", _readonly(alive, np.bool_))
        _trace_medium(self)


@dataclass(frozen=True, eq=False)
class GaussianTrace:
    """Sampled beam with both sides of surfaces and internal thick-lens gaps."""

    z_mm: NDArray[np.float64]
    radius_mm: NDArray[np.float64]
    q_mm: NDArray[np.complex128]
    n: NDArray[np.float64] | None = None
    s: NDArray[np.float64] | None = None

    def __post_init__(self) -> None:
        for name, dtype in (
            ("z_mm", np.float64),
            ("radius_mm", np.float64),
            ("q_mm", np.complex128),
        ):
            object.__setattr__(self, name, _readonly(getattr(self, name), dtype))
        if self.z_mm.ndim != 1 or self.radius_mm.shape != self.z_mm.shape or self.q_mm.shape != self.z_mm.shape:
            raise ValueError("Gaussian trace arrays must have the same one-dimensional shape")
        _trace_medium(self)
        if np.any(self.radius_mm <= 0) or np.any(self.q_mm.imag <= 0):
            raise ValueError("Gaussian radius and imaginary q must be positive")


@dataclass(frozen=True)
class OpticalSystem:
    elements: tuple[FreeSpace | ThinLens | Interface | Mirror | ThickLens | Aperture, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.elements, tuple):
            raise ValueError("elements must be a tuple")
        allowed = (FreeSpace, ThinLens, Interface, Mirror, ThickLens, Aperture)
        if any(type(element) not in allowed for element in self.elements):
            raise ValueError(f"elements must contain only {allowed}")
        _finite(self.length_mm, "length_mm")
        n = 1.0
        for element in self.elements:
            if isinstance(element, Interface):
                if not np.isclose(element.n1, n, rtol=1e-12, atol=1e-12):
                    raise ValueError(f"Interface n1={element.n1} does not match ambient n={n}")
                n = element.n2
            elif isinstance(element, ThickLens):
                if not np.isclose(n, 1.0, rtol=1e-12, atol=1e-12):
                    raise ValueError("ThickLens requires surrounding air (ambient n=1)")
                n = 1.0

    @property
    def length_mm(self) -> float:
        return sum(
            (
                element.distance_mm if isinstance(element, FreeSpace) else
                element.thickness_mm if isinstance(element, ThickLens) else 0.0
            )
            for element in self.elements
        )

    @property
    def output_z_mm(self) -> float:
        """Signed output position, unlike total traveled length_mm."""
        z, s = 0.0, 1
        for element in self.elements:
            if isinstance(element, Mirror):
                s = -s
            elif isinstance(element, FreeSpace):
                z += s * element.distance_mm
            elif isinstance(element, ThickLens):
                z += s * element.thickness_mm
        return z

    @property
    def output_n(self) -> float:
        n = 1.0
        for element in self.elements:
            if isinstance(element, Interface):
                n = element.n2
            elif isinstance(element, ThickLens):
                n = 1.0
        return n

    @property
    def output_direction(self) -> int:
        return (-1) ** sum(isinstance(element, Mirror) for element in self.elements)

    def _trace_elements(self):
        for element in self.elements:
            if isinstance(element, ThickLens):
                yield Interface(element.radius1_mm, 1.0, element.n)
                yield FreeSpace(element.thickness_mm)
                yield Interface(element.radius2_mm, element.n, 1.0)
            else:
                yield element

    def matrix(self) -> NDArray[np.float64]:
        result = np.eye(2)
        for element in self.elements:
            result = element.matrix() @ result
        if not np.all(np.isfinite(result)):
            raise ValueError("System matrix is not finite")
        return result

    def trace(self, rays: Any) -> RayTrace:
        """Record input and each exit, expanding thick lenses into entry/gap/exit.

                Apertures monotonically mask meridional rays at x=0, y=height.
                Blocked rays continue geometrically and are never replaced with NaNs.
                """
        try:
            incoming = np.asarray(rays)
            if incoming.dtype.kind not in "iuf":
                raise ValueError("rays must be real numbers")
            current = np.array(incoming, dtype=float, copy=True)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("rays must be a finite real array of shape (2, N)") from exc
        if current.ndim != 2 or current.shape[0] != 2 or not np.all(np.isfinite(current)):
            raise ValueError("rays must be a finite real array of shape (2, N)")
        z, n, s = [0.0], [1.0], [1.0]
        states = [current]
        alive = [np.ones(current.shape[1], dtype=bool)]
        for element in self._trace_elements():
            current = element.matrix() @ current
            dz = 0.0
            if isinstance(element, FreeSpace):
                dz = element.distance_mm

            z.append(z[-1] + s[-1] * dz)
            states.append(current)
            opening = np.ones(current.shape[1], dtype=bool)
            if isinstance(element, Aperture):
                opening = np.hypot(element.x_mm, current[0] - element.y_mm) <= element.radius_mm
            alive.append(alive[-1] & opening)

            # Update state for next element
            if isinstance(element, Interface):
                n.append(element.n2)

            else:
                n.append(n[-1])

            if isinstance(element, Mirror):
                s.append(-s[-1])
            else:
                s.append(s[-1])

        return RayTrace(np.asarray(z), np.asarray(states), np.asarray(n), np.asarray(s), np.asarray(alive))

    def gaussian(self, beam: GaussianBeam, samples_per_gap: int = 80) -> GaussianTrace:
        """Unclipped Gaussian reference: apertures do not modify q or radius.

                Sample each gap with this many intervals, plus its input endpoint.
                Use owl.wave.cross_sections for hard clipping and diffraction.
                """
        if not isinstance(beam, GaussianBeam):
            raise ValueError("beam must be a GaussianBeam")
        if isinstance(samples_per_gap, (bool, np.bool_)) or not isinstance(samples_per_gap, (int, np.integer)) or samples_per_gap < 1:
            raise ValueError("samples_per_gap must be a positive integer")
        z, n, s = [0.0], [1.0], [1.0]
        qs = [beam.q_mm]

        def record_gap(dist, local_n, local_s):
            offsets = np.linspace(0.0, dist, samples_per_gap + 1)[1:] if dist else [0.0]
            start_z, start_q = z[-1], qs[-1]
            z.extend(start_z + local_s * float(offset) for offset in offsets)
            qs.extend(start_q + float(offset) for offset in offsets)
            n.extend([local_n] * len(offsets))
            s.extend([local_s] * len(offsets))

        for element in self._trace_elements():
            if isinstance(element, FreeSpace):
                record_gap(element.distance_mm, n[-1], s[-1])
            else:
                m = element.matrix()
                qs.append((m[0, 0] * qs[-1] + m[0, 1]) / (m[1, 0] * qs[-1] + m[1, 1]))
                z.append(z[-1])
                if isinstance(element, Interface):
                    n.append(element.n2)
                else:
                    n.append(n[-1])
                if isinstance(element, Mirror):
                    s.append(-s[-1])
                else:
                    s.append(s[-1])

        q_array = np.asarray(qs, dtype=complex)
        n_array = np.asarray(n, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            # radius = sqrt( (lam/n) / (pi * Im(1/q)) )
            radius = np.sqrt(-(beam.wavelength_mm / n_array) / (np.pi * np.imag(1.0 / q_array)))
        return GaussianTrace(np.asarray(z), radius, q_array, n_array, np.asarray(s))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "elements": [element.to_dict() for element in self.elements]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OpticalSystem":
        _schema(data, {"schema_version", "elements"}, versioned=True)
        if not isinstance(data["elements"], list):
            raise ValueError("elements must be a list in serialized data")
        elements = []
        for item in data["elements"]:
            if not isinstance(item, dict):
                raise ValueError("Each element must be an object")
            t = item.get("type")
            if t == "free_space":
                elements.append(FreeSpace.from_dict(item))
            elif t == "thin_lens":
                elements.append(ThinLens.from_dict(item))
            elif t == "interface":
                elements.append(Interface.from_dict(item))
            elif t == "mirror":
                elements.append(Mirror.from_dict(item))
            elif t == "thick_lens":
                elements.append(ThickLens.from_dict(item))
            elif t == "aperture":
                elements.append(Aperture.from_dict(item))
            else:
                raise ValueError(f"Unknown element type: {t}")
        return cls(tuple(elements))
