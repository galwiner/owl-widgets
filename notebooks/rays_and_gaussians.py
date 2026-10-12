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
    from owl import Bench, FreeSpace, GaussianBeam, OpticalSystem, ThinLens

    return Bench, FreeSpace, GaussianBeam, OpticalSystem, ThinLens, mo, np, plt


@app.cell
def _(mo):
    mo.md(r"""
    # Rays and Gaussian beams

    Initial benches use air and ideal thin lenses; no apertures, $M^2=1$.
    Lengths and beam radii are in mm, wavelength in nm, ray angles in rad.
    Each bench starts independently with parallel rays and a Gaussian waist at $z=0$.
    The Gaussian radius $w$ is the $1/e^2$ intensity radius.
    """)
    return


@app.cell
def _(mo):/
    mo.md(r"""
    ## Free propagation

    $y(z)=y_0+z\theta_0$, $q(z)=z+i z_R$,
    $z_R=\pi w_0^2/\lambda$, $w(z)=w_0\sqrt{1+(z/z_R)^2}$.
    Use mm for $\lambda$ in these equations. Vary the gap and input waist.
    """)
    return


@app.cell
def _(Bench, FreeSpace, GaussianBeam, OpticalSystem, mo):
    propagation_widget = Bench(
        OpticalSystem((FreeSpace(150),)),
        beam=GaussianBeam(waist_mm=0.1, wavelength_nm=550),
        ray_span_mm=0.1,
        ray_count=9,
    )
    propagation_bench = mo.ui.anywidget(propagation_widget)
    propagation_bench
    return


@app.cell
def _(mo):
    mo.md("""
    ### Free propagation notes
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Thin lens

    $\theta_{\rm out}=\theta_{\rm in}-y/f$,
    $1/q_{\rm out}=1/q_{\rm in}-1/f$.
    Vary the focal length and gaps; compare ray heights and beam radii across the lens.
    """)
    return


@app.cell
def _(Bench, FreeSpace, GaussianBeam, OpticalSystem, ThinLens, mo):
    lens_widget = Bench(
        OpticalSystem((FreeSpace(40), ThinLens(80), FreeSpace(160))),
        beam=GaussianBeam(waist_mm=0.2, wavelength_nm=550),
        ray_span_mm=0.3,
        ray_count=11,
    )
    lens_bench = mo.ui.anywidget(lens_widget)
    lens_bench
    return


@app.cell
def _(mo):
    mo.md("""
    ### Thin lens notes
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Ray focus versus Gaussian waist

    Edit this independent bench. For its complete matrix $\begin{pmatrix}A&B\\C&D\end{pmatrix}$,
    a parallel input fan has signed focus distance $d_{\rm ray}=-A/C$ from the output plane.
    In free continuation, $q(d)=q_{\rm out}+d$, so
    $d_w=-\operatorname{Re}q_{\rm out}$ and
    $w_* = \sqrt{\lambda_{\rm local}\operatorname{Im}q_{\rm out}/\pi}$.
    Here $\lambda_{\rm local}=\lambda_0/n_{\rm out}$ in mm. Distances follow the outgoing direction;
    $z(d)=z_{\rm out}+s_{\rm out}d$. Continue in the output medium with no further elements.
    Negative distances are backward extrapolations of the output field, not predictions through earlier lenses.
    """)
    return


@app.cell
def _(Bench, FreeSpace, GaussianBeam, OpticalSystem, ThinLens, mo):
    focus_widget = Bench(
        OpticalSystem((FreeSpace(30), ThinLens(100), FreeSpace(20))),
        beam=GaussianBeam(waist_mm=0.12, wavelength_nm=633),
        ray_span_mm=0.25,
        ray_count=11,
    )
    focus_bench = mo.ui.anywidget(focus_widget)
    focus_bench
    return (focus_bench,)


@app.cell
def _(GaussianBeam, OpticalSystem, focus_bench, mo, np):
    _settings = focus_bench.value["settings"]
    _system = OpticalSystem.from_dict(_settings["system"])
    _beam = GaussianBeam.from_dict(_settings["beam"])
    _q = complex(_system.gaussian(_beam).q_mm[-1])
    _local_wavelength = _beam.wavelength_mm / _system.output_n
    _a, _c = _system.matrix()[:, 0]
    _waist_distance = -_q.real
    _waist_radius = np.sqrt(_local_wavelength * _q.imag / np.pi)
    _downstream_distance = max(0.0, _waist_distance)
    _downstream_q = _q + _downstream_distance
    _downstream_radius = np.sqrt(
        -_local_wavelength / (np.pi * (1.0 / _downstream_q).imag)
    )
    if _settings["ray_count"] == 1 or _settings["ray_span_mm"] == 0:
        _ray_description = "Undefined for the displayed on-axis-only rays."
    elif _c == 0:
        _ray_description = "No finite focus: the output rays are parallel."
    else:
        _ray_distance = float(-_a / _c)
        _location = "downstream" if _ray_distance >= 0 else "backward extrapolation"
        _ray_description = f"{_ray_distance:.6g} mm ({_location})"
    mo.md(f"""
    | Quantity | Current value |
    | :-- | --: |
    | Output plane z | {_system.output_z_mm:.6g} mm |
    | Output refractive index | {_system.output_n:.6g} |
    | Outgoing direction s | {_system.output_direction:+d} |
    | Ray focus distance from output | {_ray_description} |
    | Signed Gaussian waist distance from output | {_waist_distance:.6g} mm |
    | Free-continuation waist z | {_system.output_z_mm + _system.output_direction * _waist_distance:.6g} mm |
    | Free-continuation waist radius | {_waist_radius:.6g} mm |
    | Minimum-radius location restricted to d ≥ 0 | {_downstream_distance:.6g} mm |
    | Minimum radius restricted to d ≥ 0 | {_downstream_radius:.6g} mm |
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ### Ray focus versus Gaussian waist notes
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Wavelength sweep

    Independent Python-core experiment: fixed input waist, gaps, focal length, and observation plane.
    Sweep only $\lambda$; the ideal lens has no dispersion.
    """)
    return


@app.cell
def _(FreeSpace, GaussianBeam, OpticalSystem, ThinLens, np, plt):
    _system = OpticalSystem((FreeSpace(25), ThinLens(75), FreeSpace(100)))
    _waist_mm = 0.15
    _wavelengths_nm = np.linspace(400, 800, 81)
    _output_radii_mm = [
        _system.gaussian(GaussianBeam(_waist_mm, float(_wavelength))).radius_mm[-1]
        for _wavelength in _wavelengths_nm
    ]
    _fig, _ax = plt.subplots(figsize=(7, 3.5), layout="constrained")
    _ax.plot(_wavelengths_nm, _output_radii_mm)
    _ax.set(
        xlabel="Wavelength (nm)",
        ylabel="Output Gaussian radius (mm)",
        title="w₀ = 0.15 mm · gaps = 25, 100 mm · f = 75 mm",
    )
    _ax.grid(alpha=0.25)
    plt.close(_fig)
    _fig
    return


@app.cell
def _(mo):
    mo.md("""
    ### Wavelength sweep notes
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Experiment settings

    Current **Ray focus versus Gaussian waist** bench settings, including edits.
    Restore a saved JSON object with:

    ```python
    import json
    from owl import Bench

    restored = Bench.from_dict(json.loads(settings_json))
    mo.ui.anywidget(restored)
    ```
    """)
    return


@app.cell
def _(focus_bench, mo):
    mo.json(focus_bench.value["settings"])
    return


if __name__ == "__main__":
    app.run()
