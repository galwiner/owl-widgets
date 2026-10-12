# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo==0.24.0", "owl-widgets==0.1.0", "numpy>=2", "matplotlib>=3.9"]
# [tool.uv.sources]
# owl-widgets = { path = "..", editable = true }
# ///

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import matplotlib.pyplot as plt
    import numpy as np
    from owl import (
        Bench,
        FreeSpace,
        GaussianBeam,
        Interface,
        Mirror,
        OpticalSystem,
        ThickLens,
        ThinLens,
    )

    return Bench, FreeSpace, GaussianBeam, Interface, Mirror, OpticalSystem, ThickLens, ThinLens, mo, np, plt


@app.cell
def _(mo):
    mo.md(r"""
    # Optics basics

    Independent paraxial experiments · mm, nm, rad · input Gaussian waist at $z=0$ · $M^2=1$.
    Each bench starts in air. Ray angles are small-angle slopes; beam radius is the $1/e^2$ intensity radius.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Free propagation

    $y(z)=y_0+z\theta_0$, $q(z)=z+i z_R$,
    $z_R=\pi w_0^2/\lambda$, $w(z)=w_0\sqrt{1+(z/z_R)^2}$.
    Use mm for $\lambda$ in these equations.
    """)
    return


@app.cell
def _(Bench, FreeSpace, GaussianBeam, OpticalSystem, mo):
    propagation = mo.ui.anywidget(Bench(
        OpticalSystem((FreeSpace(150),)),
        beam=GaussianBeam(0.1, 550),
        ray_span_mm=0.1,
        ray_count=9,
    ))
    propagation
    return (propagation,)


@app.cell
def _(mo):
    mo.md(r"""
    ## Thin lens · ray focus and Gaussian waist

    $\theta_{out}=\theta_{in}-y/f$, $1/q_{out}=1/q_{in}-1/f$.
    The geometric ray focus and Gaussian minimum need not be at the same plane.
    """)
    return


@app.cell
def _(Bench, FreeSpace, GaussianBeam, OpticalSystem, ThinLens, mo):
    focus = mo.ui.anywidget(Bench(
        OpticalSystem((FreeSpace(30), ThinLens(100), FreeSpace(20))),
        beam=GaussianBeam(0.12, 633),
        ray_span_mm=0.25,
        ray_count=11,
    ))
    focus
    return (focus,)


@app.cell
def _(GaussianBeam, OpticalSystem, focus, mo, np):
    _settings = focus.value["settings"]
    _system = OpticalSystem.from_dict(_settings["system"])
    _beam = GaussianBeam.from_dict(_settings["beam"])
    _q = complex(_system.gaussian(_beam).q_mm[-1])
    _lambda_local = _beam.wavelength_mm / _system.output_n
    _a, _c = _system.matrix()[:, 0]
    _waist_distance = -_q.real
    _waist_radius = np.sqrt(_lambda_local * _q.imag / np.pi)
    if _settings["ray_count"] == 1 or _settings["ray_span_mm"] == 0:
        _ray_focus = "Undefined for the displayed on-axis-only rays."
    elif _c == 0:
        _ray_focus = "No finite focus: output rays are parallel."
    else:
        _distance = float(-_a / _c)
        _where = "downstream" if _distance >= 0 else "backward extrapolation"
        _ray_focus = f"{_distance:.4g} mm ({_where})"
    mo.md(f"""
    | Quantity | Current value |
    |:--|--:|
    | Output plane | {_system.output_z_mm:.4g} mm |
    | Output medium | n = {_system.output_n:.4g} |
    | Ray focus from output | {_ray_focus} |
    | Signed Gaussian waist distance | {_waist_distance:.4g} mm |
    | Free-continuation waist z | {_system.output_z_mm + _system.output_direction * _waist_distance:.4g} mm |
    | Free-continuation waist radius | {_waist_radius:.4g} mm |
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Wavelength tuning

    Fixed system, varying $\lambda$. An ideal thin lens has no dispersion.
    """)
    return


@app.cell
def _(FreeSpace, GaussianBeam, OpticalSystem, ThinLens, np, plt):
    _system = OpticalSystem((FreeSpace(25), ThinLens(75), FreeSpace(100)))
    _waist = 0.15
    _wavelengths = np.linspace(400, 800, 81)
    _radii = [_system.gaussian(GaussianBeam(_waist, float(_lam))).radius_mm[-1] for _lam in _wavelengths]
    _fig, _ax = plt.subplots(figsize=(7, 3.5), layout="constrained")
    _ax.plot(_wavelengths, _radii)
    _ax.set(xlabel="Wavelength (nm)", ylabel="Output Gaussian radius (mm)", title="w₀ = 0.15 mm · gaps = 25, 100 mm · f = 75 mm")
    _ax.grid(alpha=0.25)
    plt.close(_fig)
    _fig
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Mirrors

    A mirror reverses propagation. Gaps are positive traveled distances, not signed $z$ steps.
    Compare flat and curved surfaces; list every return-path element explicitly.
    """)
    return


@app.cell
def _(Bench, FreeSpace, GaussianBeam, Mirror, OpticalSystem, mo):
    mirrors = mo.vstack([
        mo.ui.anywidget(Bench(OpticalSystem((FreeSpace(60), Mirror(), FreeSpace(40))), GaussianBeam(0.1, 633), ray_span_mm=0.2)),
        mo.ui.anywidget(Bench(OpticalSystem((FreeSpace(60), Mirror(100), FreeSpace(80))), GaussianBeam(0.1, 633), ray_span_mm=0.2)),
    ])
    mirrors
    return (mirrors,)


@app.cell
def _(mo):
    mo.md(r"""
    ## Interfaces

    Enter glass with `Interface(np.inf, 1, 1.5)`, propagate inside it, then exit to air.
    Keep adjacent refractive indices consistent.
    """)
    return


@app.cell
def _(Bench, FreeSpace, GaussianBeam, Interface, OpticalSystem, mo, np):
    interfaces = mo.ui.anywidget(Bench(
        OpticalSystem((FreeSpace(30), Interface(np.inf, 1, 1.5), FreeSpace(40), Interface(np.inf, 1.5, 1), FreeSpace(60))),
        GaussianBeam(0.1, 633),
        ray_span_mm=0.2,
    ))
    interfaces
    return (interfaces,)


@app.cell
def _(mo):
    mo.md(r"""
    ## Thick lens

    Compare `ThickLens(60, -60, 10, 1.5)` with explicit entrance interface, glass propagation, and exit interface.
    The benches are independent; `ThickLens` requires air on both sides.
    """)
    return


@app.cell
def _(Bench, FreeSpace, GaussianBeam, Interface, OpticalSystem, ThickLens, mo):
    thick_lenses = mo.vstack([
        mo.ui.anywidget(Bench(OpticalSystem((FreeSpace(30), ThickLens(60, -60, 10, 1.5), FreeSpace(100))), GaussianBeam(0.1, 633), ray_span_mm=0.2)),
        mo.ui.anywidget(Bench(OpticalSystem((FreeSpace(30), Interface(60, 1, 1.5), FreeSpace(10), Interface(-60, 1.5, 1), FreeSpace(100))), GaussianBeam(0.1, 633), ray_span_mm=0.2)),
    ])
    thick_lenses
    return (thick_lenses,)


@app.cell
def _(mo):
    mo.md(r"""
    ## Conventions

    - Flat radii: `np.inf` in Python, `null` in JSON; zero radius is invalid.
    - Interface radius is positive when its center of curvature lies along the incident direction.
    - Systems are listed in encounter order. A mirror does not automatically retrace earlier elements.
    - Reverse an interface as `Interface(-R, n2, n1)`; reverse a thick lens by swapping and negating its radii.
    - `length_mm` is total traveled length. Use `output_z_mm`, `output_n`, and `output_direction` for the output state.
    """)
    return


if __name__ == "__main__":
    app.run()
