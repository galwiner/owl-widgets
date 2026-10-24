# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo==0.24.0", "owl-widgets[gpu]==0.1.4", "numpy>=2", "matplotlib>=3.9", "wigglystuff>=0.1.0,<=0.2.22"]
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import matplotlib.pyplot as plt
    import numpy as np
    from owl import Bench, FreeSpace, GaussianBeam, OpticalSystem, ThinLens
    from wigglystuff import TangleSlider

    return (
        Bench,
        FreeSpace,
        GaussianBeam,
        OpticalSystem,
        TangleSlider,
        ThinLens,
        mo,
        np,
        plt,
    )


@app.cell
def _(Bench, FreeSpace, GaussianBeam, OpticalSystem, ThinLens, mo):
    @mo.lru_cache(maxsize=32, pin_modules=True)
    def compute_bench(f_obj, f_eye, spacing, waist_mm, wavelength_nm):
        system = OpticalSystem((
            FreeSpace(50),
            ThinLens(f_obj),
            FreeSpace(spacing),
            ThinLens(f_eye),
            FreeSpace(100),
        ))
        return Bench._derive({
            "system": system.to_dict(),
            "beam": GaussianBeam(waist_mm, wavelength_nm).to_dict(),
            "ray_span_mm": waist_mm,
            "ray_count": 9,
            "wave": {"grid_size": 256, "window_mm": 2},
        }, "auto")

    return (compute_bench,)


@app.cell
def _(mo):
    mo.md(r"""
    # Keplerian telescope · ray or Gaussian design?

    Two positive lenses form an inverted, afocal telescope in ray optics.

    Tune the objective, eyepiece, wavelength, and input waist. Compare the ray-optical afocal spacing with the spacing that minimizes Gaussian-beam divergence.
    """)
    return


@app.cell
def _(TangleSlider, mo):
    objective = mo.ui.anywidget(TangleSlider(amount=200, min_value=100, max_value=300, step=25, prefix="Objective focal length: ", suffix=" mm", digits=0))
    eyepiece = mo.ui.anywidget(TangleSlider(amount=20, min_value=10, max_value=50, step=5, prefix="Eyepiece focal length: ", suffix=" mm", digits=0))
    wavelength = mo.ui.anywidget(TangleSlider(amount=633, min_value=450, max_value=700, step=25, prefix="Wavelength: ", suffix=" nm", digits=0))
    waist = mo.ui.anywidget(TangleSlider(amount=0.4, min_value=0.2, max_value=0.5, step=0.05, prefix="Input waist: ", suffix=" mm", digits=2))
    mo.md(f"""
    Adjust the design parameters inline:

    - {objective}
    - {eyepiece}
    - {wavelength}
    - {waist}
    """)
    return eyepiece, objective, waist, wavelength


@app.cell
def _(GaussianBeam, eyepiece, np, objective, waist, wavelength):
    f_obj = float(objective.value["amount"])
    f_eye = float(eyepiece.value["amount"])
    beam = GaussianBeam(
        float(waist.value["amount"]),
        float(wavelength.value["amount"]),
    )
    entrance_gap = 50.0
    ray_spacing = f_obj + f_eye


    # Vectorized q propagation: gap, objective, candidate gap, eyepiece.
    candidates = np.linspace(max(0.0, ray_spacing - 4 * f_eye), ray_spacing + 4 * f_eye, 1601)
    q_in = 1j * np.pi * beam.waist_mm**2 / beam.wavelength_mm
    q_at_objective = q_in + entrance_gap
    q_after_objective = 1 / (1 / q_at_objective - 1 / f_obj)
    q_at_eyepiece = q_after_objective + candidates
    q_out = 1 / (1 / q_at_eyepiece - 1 / f_eye)
    best = int(np.argmax(q_out.imag))
    gaussian_spacing = float(candidates[best])
    gaussian_rayleigh_range = float(q_out.imag[best])
    ray_total_length = entrance_gap + ray_spacing + 100
    gaussian_total_length = entrance_gap + gaussian_spacing + 100
    return (
        beam,
        f_eye,
        f_obj,
        gaussian_rayleigh_range,
        gaussian_spacing,
        gaussian_total_length,
        ray_spacing,
        ray_total_length,
    )


@app.cell
def _(
    Bench,
    beam,
    compute_bench,
    f_eye,
    f_obj,
    gaussian_rayleigh_range,
    gaussian_spacing,
    gaussian_total_length,
    mo,
    ray_spacing,
    ray_total_length,
):
    def make_bench(spacing):
        settings, result = compute_bench(
            f_obj, f_eye, spacing, beam.waist_mm, beam.wavelength_nm
        )
        return Bench._from_derived(settings, result, backend="auto")

    ray_bench = mo.ui.anywidget(make_bench(ray_spacing))
    gaussian_bench = mo.ui.anywidget(make_bench(gaussian_spacing))
    ray_calculation = mo.md(rf"""
    ### Ray-optical spacing

    For two positive thin lenses separated by $d$,

    $$C = \frac{{d-f_{{obj}}-f_{{eye}}}}{{f_{{obj}}f_{{eye}}}}.$$

    Afocal output requires $C=0$:

    $$d_{{ray}}=f_{{obj}}+f_{{eye}}={f_obj:.0f}+{f_eye:.0f}=\mathbf{{{ray_spacing:.2f}\,\mathrm{{mm}}}}.$$

    Angular magnification: $-f_{{obj}}/f_{{eye}}={-f_obj / f_eye:.2f}$.

    Total displayed instrument length:

    $$L_{{ray}}=50+d_{{ray}}+100=\mathbf{{{ray_total_length:.2f}\,\mathrm{{mm}}}}.$$
    """)
    gaussian_calculation = mo.md(rf"""
    ### Gaussian spacing

    Start with $q_{{in}}=i z_R$, where

    $$z_R=\frac{{\pi w_0^2}}{{\lambda}}.$$

    For each spacing $d$, apply the telescope matrix:

    $$q_{{out}}(d)=\frac{{A(d)q_{{in}}+B(d)}}{{C(d)q_{{in}}+D(d)}}.$$

    Choose $d$ that maximizes $\operatorname{{Im}}q_{{out}}$ and therefore minimizes far-field divergence:

    $$d_{{G}}=\mathbf{{{gaussian_spacing:.2f}\,\mathrm{{mm}}}},\qquad z_{{R,\mathrm{{out}}}}={gaussian_rayleigh_range:.2f}\,\mathrm{{mm}}.$$

    Total displayed instrument length:

    $$L_{{G}}=50+d_{{G}}+100=\mathbf{{{gaussian_total_length:.2f}\,\mathrm{{mm}}}}.$$
    """)
    ray_column = mo.vstack([ray_calculation, ray_bench])
    gaussian_column = mo.vstack([gaussian_calculation, gaussian_bench])
    divided_gaussian_column = mo.Html(f"""
    <div style="border-left: 1px solid var(--slate-5); padding-left: 24px; min-height: 100%;">
      {gaussian_column}
    </div>
    """)
    mo.hstack([ray_column, divided_gaussian_column], widths="equal", align="stretch")
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## How Gaussian design changes instrument length

    Fixed prescription: $f_{obj}=200\,\mathrm{mm}$, $f_{eye}=20\,\mathrm{mm}$, with the same 50 mm entrance and 100 mm output gaps. The dashed reference is the ray-optical length. A curve stops when its optimum reaches the spacing search boundary.
    """)
    return


@app.cell
def _(mo, np):
    @mo.cache(pin_modules=True)
    def length_sweep():
        f_obj = 200.0
        f_eye = 20.0
        ray_spacing = f_obj + f_eye
        ray_length = 50 + ray_spacing + 100
        candidates = np.linspace(ray_spacing - 4 * f_eye, ray_spacing + 4 * f_eye, 1601)

        def gaussian_length(waist_mm, wavelength_nm):
            q_in = 1j * np.pi * waist_mm**2 / (wavelength_nm * 1e-6)
            q_at_objective = q_in + 50
            q_after_objective = 1 / (1 / q_at_objective - 1 / f_obj)
            q_at_eyepiece = q_after_objective + candidates
            q_out = 1 / (1 / q_at_eyepiece - 1 / f_eye)
            best = int(np.argmax(q_out.imag))
            if best in (0, len(candidates) - 1):
                return np.nan
            spacing = candidates[best]
            return 50 + spacing + 100

        diameters = np.linspace(0.4, 1.0, 61)
        wavelengths = np.linspace(450, 700, 101)
        wavelength_curves = {
            wavelength: np.array([
                gaussian_length(diameter / 2, wavelength)
                for diameter in diameters
            ])
            for wavelength in (450, 550, 633, 700)
        }
        diameter_curves = {
            diameter: np.array([
                gaussian_length(diameter / 2, wavelength)
                for wavelength in wavelengths
            ])
            for diameter in (0.4, 0.6, 0.8, 1.0)
        }
        return {
            "diameters": diameters,
            "wavelengths": wavelengths,
            "wavelength_curves": wavelength_curves,
            "diameter_curves": diameter_curves,
            "ray_length": ray_length,
        }

    return (length_sweep,)


@app.cell
def _(length_sweep, plt):
    _data = length_sweep()
    _fig, (_diameter_ax, _wavelength_ax) = plt.subplots(
        1, 2, figsize=(10, 4), layout="constrained"
    )
    for _wavelength, _lengths in _data["wavelength_curves"].items():
        _diameter_ax.plot(
            _data["diameters"], _lengths, label=f"{_wavelength:.0f} nm"
        )
    _diameter_ax.axhline(
        _data["ray_length"], color="black", linestyle="--", label="Ray design"
    )
    _diameter_ax.set(
        xlabel="Input beam diameter (mm)",
        ylabel="Total instrument length (mm)",
        title="Length versus beam diameter",
    )
    _diameter_ax.legend()
    _diameter_ax.grid(alpha=0.25)

    for _diameter, _lengths in _data["diameter_curves"].items():
        _wavelength_ax.plot(
            _data["wavelengths"], _lengths, label=f"{_diameter:.1f} mm beam"
        )
    _wavelength_ax.axhline(
        _data["ray_length"], color="black", linestyle="--", label="Ray design"
    )
    _wavelength_ax.set(
        xlabel="Wavelength (nm)",
        ylabel="Total instrument length (mm)",
        title="Length versus wavelength",
    )
    _wavelength_ax.legend()
    _wavelength_ax.grid(alpha=0.25)
    plt.close(_fig)
    _fig
    return


if __name__ == "__main__":
    app.run()
