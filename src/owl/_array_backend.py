"""Lazy selection of the NumPy or optional CuPy array backend."""

import ctypes
import sys
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any

import numpy as np

_BACKEND_NAMES = frozenset(("auto", "cpu", "gpu"))


def _preload_wheel_cufft() -> None:
    """Expose cuFFT installed by NVIDIA's component wheel to CuPy.

    Some sandboxed Linux environments do not add the component wheel's library
    directory to the dynamic loader path. Loading its soname by absolute path
    lets CuPy's subsequent lazy import resolve the already-loaded library.
    """
    if sys.platform != "linux":
        return
    try:
        dist = distribution("nvidia-cufft-cu12")
    except PackageNotFoundError:
        return

    candidates = sorted(
        Path(str(dist.locate_file(file)))
        for file in dist.files or ()
        if Path(str(file)).name == "libcufft.so.11"
    )
    if candidates:
        ctypes.CDLL(str(candidates[0]), mode=ctypes.RTLD_GLOBAL)


@dataclass(frozen=True)
class ArrayBackend:
    """Resolved numerical array backend."""

    name: str
    xp: Any
    device: str
    fallback_reason: str | None = None

    def to_numpy(self, value: Any) -> np.ndarray:
        if self.name == "gpu":
            return self.xp.asnumpy(value)
        return np.asarray(value)

    def scalar(self, value: Any) -> Any:
        return self.to_numpy(value).item()

    def synchronize(self) -> None:
        if self.name == "gpu":
            self.xp.cuda.Stream.null.synchronize()


def resolve_backend(name: str = "cpu") -> ArrayBackend:
    """Resolve ``cpu``, ``gpu``, or ``auto`` without importing CuPy for CPU.

    ``auto`` falls back to NumPy if CuPy cannot be imported or no CUDA device is
    usable. An explicit ``gpu`` request raises ``RuntimeError`` in that case.
    """
    if not isinstance(name, str) or name not in _BACKEND_NAMES:
        raise ValueError("backend must be one of 'auto', 'cpu', or 'gpu'")
    if name == "cpu":
        return ArrayBackend("cpu", np, "cpu")

    try:
        cupy = import_module("cupy")
        count = int(cupy.cuda.runtime.getDeviceCount())
        if count < 1:
            raise RuntimeError("no CUDA devices were detected")
        # Force context creation and a real FFT. CuPy imports cuFFT lazily, so a
        # simple allocation can succeed even when the runtime lacks libcufft.
        _preload_wheel_cufft()
        probe = cupy.zeros((2, 2), dtype=cupy.complex128)
        cupy.fft.fft2(probe)
        cupy.cuda.Stream.null.synchronize()
        device_id = int(cupy.cuda.runtime.getDevice())
        properties = cupy.cuda.runtime.getDeviceProperties(device_id)
        raw_name = properties.get("name", f"CUDA device {device_id}")
        device_name = raw_name.decode() if isinstance(raw_name, bytes) else str(raw_name)
        return ArrayBackend("gpu", cupy, device_name)
    except Exception as exc:
        if name == "auto":
            return ArrayBackend("cpu", np, "cpu", f"GPU unavailable: {exc}")
        raise RuntimeError(f"GPU backend unavailable: {exc}") from exc
