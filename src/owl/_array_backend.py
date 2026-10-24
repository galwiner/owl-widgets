"""Lazy selection of the NumPy or optional CuPy array backend."""

from dataclasses import dataclass
from importlib import import_module
from typing import Any

import numpy as np

_BACKEND_NAMES = frozenset(("auto", "cpu", "gpu"))


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
        # Force context creation and a tiny operation; an installed CuPy package
        # alone does not imply a usable driver/device.
        cupy.zeros(1).sum()
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
