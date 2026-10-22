"""A linked cross-section display: the bench remains the experiment's owner."""

from copy import deepcopy
from pathlib import Path

import anywidget
import traitlets

from .bench import Bench


class CrossSection(anywidget.AnyWidget):
    """Display a Bench's wave planes without duplicating controls or calculations.

    Keep the same Bench instance in both views. Changes to its validated settings
    update this display automatically; plane selection is local to each view.
    Call close() when discarding a view to detach its observer.
    """

    _esm = Bench._esm
    _css = Path(__file__).parent / "static" / "bench.css"
    view_kind = traitlets.Unicode("cross_section").tag(sync=True)
    result = traitlets.Dict().tag(sync=True)
    error = traitlets.Unicode("").tag(sync=True)

    def __init__(self, bench: Bench):
        if not isinstance(bench, Bench):
            raise ValueError("CrossSection requires a Bench")
        self._bench = bench
        super().__init__(result=deepcopy(bench.result["cross_sections"]), error=bench.error)
        bench.observe(self._refresh, names=["result", "error"])

    def _refresh(self, change):
        with self.hold_sync():
            if change["name"] == "result":
                self.result = deepcopy(change["new"]["cross_sections"])
            self.error = self._bench.error

    def close(self):
        bench = getattr(self, "_bench", None)
        if bench is not None:
            bench.unobserve(self._refresh, names=["result", "error"])
            self._bench = None
        super().close()
