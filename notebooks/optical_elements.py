# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo==0.24.0", "owl-widgets==0.1.0", "numpy>=2"]
# [tool.uv.sources]
# owl-widgets = { path = "..", editable = true }
# ///

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import numpy as np
    from owl import (
        Bench,
        FreeSpace,
        GaussianBeam,
        Interface,
        Mirror,
        OpticalSystem,
        ThickLens,
    )

    return Bench, FreeSpace, GaussianBeam, Interface, Mirror, OpticalSystem, ThickLens, mo, np


@app.cell
def _(mo):
    mo.md("""
    # Optical elements

    Independent paraxial sandboxes; mm, nm, rad. Each starts in air with a Gaussian waist
    and parallel rays. Edit one bench at a time; keep your observations in the notes.
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Flat mirror

    `Mirror()` reverses propagation. Gaps are positive traveled distances, not signed z steps.
    """)
    return


@app.cell
def _(Bench, FreeSpace, GaussianBeam, Mirror, OpticalSystem, mo):
    flat_bench = mo.ui.anywidget(Bench(
        OpticalSystem((FreeSpace(60), Mirror(), FreeSpace(40))),
        beam=GaussianBeam(0.1, 633),
        ray_span_mm=0.2,
    ))
    flat_bench
    return (flat_bench,)


@app.cell
def _(mo):
    mo.md("""
    ### Flat mirror notes
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Curved mirror

    Start with `Mirror(100)`. Positive radius is concave; compare with the flat mirror.
    """)
    return


@app.cell
def _(Bench, FreeSpace, GaussianBeam, Mirror, OpticalSystem, mo):
    curved_bench = mo.ui.anywidget(Bench(
        OpticalSystem((FreeSpace(60), Mirror(100), FreeSpace(80))),
        beam=GaussianBeam(0.1, 633),
        ray_span_mm=0.2,
    ))
    curved_bench
    return (curved_bench,)


@app.cell
def _(mo):
    mo.md("""
    ### Curved mirror notes
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Flat interfaces

    Enter glass with `Interface(np.inf, 1, 1.5)`, propagate inside it, then exit to air.
    Keep adjacent refractive indices consistent when editing.
    """)
    return


@app.cell
def _(Bench, FreeSpace, GaussianBeam, Interface, OpticalSystem, mo, np):
    interface_bench = mo.ui.anywidget(Bench(
        OpticalSystem((
            FreeSpace(30), Interface(np.inf, 1, 1.5), FreeSpace(40),
            Interface(np.inf, 1.5, 1), FreeSpace(60),
        )),
        beam=GaussianBeam(0.1, 633),
        ray_span_mm=0.2,
    ))
    interface_bench
    return (interface_bench,)


@app.cell
def _(mo):
    mo.md("""
    ### Interface notes
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Thick lens

    Compare `ThickLens(60, -60, 10, 1.5)` with the explicit entry, glass gap, and exit below.
    These benches are independent; edits are not linked. `ThickLens` requires air on both sides.
    """)
    return


@app.cell
def _(Bench, FreeSpace, GaussianBeam, OpticalSystem, ThickLens, mo):
    thick_bench = mo.ui.anywidget(Bench(
        OpticalSystem((FreeSpace(30), ThickLens(60, -60, 10, 1.5), FreeSpace(100))),
        beam=GaussianBeam(0.1, 633),
        ray_span_mm=0.2,
    ))
    thick_bench
    return (thick_bench,)


@app.cell
def _(Bench, FreeSpace, GaussianBeam, Interface, OpticalSystem, mo):
    explicit_bench = mo.ui.anywidget(Bench(
        OpticalSystem((
            FreeSpace(30), Interface(60, 1, 1.5), FreeSpace(10),
            Interface(-60, 1.5, 1), FreeSpace(100),
        )),
        beam=GaussianBeam(0.1, 633),
        ray_span_mm=0.2,
    ))
    explicit_bench
    return (explicit_bench,)


@app.cell
def _(mo):
    mo.md("""
    ### Thick lens notes
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Conventions for further experiments

    - Flat radii: Python `np.inf`, serialized JSON `null`; zero radii are invalid.
    - Interface radii are positive when their centers of curvature lie along the incident direction.
    - List every encounter, including return paths. A mirror does not automatically retrace earlier elements.
      Reverse an interface as `Interface(-R, n2, n1)`; reverse a thick lens by swapping and negating
      its radii: `ThickLens(-R2, -R1, thickness, n)`.
    - Trace arrays `n` and `s` record refractive index and direction (+1/-1) per sample.
      `length_mm` is total traveled length; use `output_z_mm`, `output_n`, and `output_direction`
      for the output state. In free continuation, `z = output_z_mm + output_direction * d`.
    """)
    return


if __name__ == "__main__":
    app.run()
