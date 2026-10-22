"""Self-contained browser bundle shared by the notebook widgets."""

from pathlib import Path

_STATIC = Path(__file__).parent / "static"
_WIDGET_ESM = "\n".join(
    (_STATIC / name).read_text(encoding="utf-8")
    for name in ("plotly.min.js", "plotly_views.js", "bench.js")
)
