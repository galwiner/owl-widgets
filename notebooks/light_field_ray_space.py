# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo==0.24.0",
#     "owl-widgets",
#     "numpy>=2",
#     "matplotlib>=3.9",
# ]
#
# [tool.uv.sources]
# owl-widgets = { path = "../" }
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
        LightFieldLayer,
        LightFieldSpec,
        calculate_light_field,
        sample_radiance,
    )

    return (
        LightFieldLayer,
        LightFieldSpec,
        calculate_light_field,
        mo,
        np,
        plt,
        sample_radiance,
    )


@app.cell
def _(mo):
    mo.md(r"""
    # Ray space: what a light field actually is

    A ray needs four numbers, not two. Pick two reference planes and record where the ray
    crosses each: \(u\) on the **main lens**, \(s\) on the **reference image plane**. The
    light field is \(L(u,s)\), the radiance of that one ray.

    Everything here uses **one transverse axis**, so \(L(u,s)\) is a 2D array you can look
    at directly. A real camera's light field is 4D; the second axis behaves identically.

    A conventional photograph throws the structure away by summing over the aperture:

    $$I(s) = \int L(u,s)\,\mathrm{d}u$$

    Once summed, it cannot be undone. Everything below is about what you can do if you
    keep \(u\) and \(s\) apart instead.

    Companion notes: `docs/lightfield/01-ray-space.md`.
    """)
    return


@app.cell
def _(mo):
    focus_slider = mo.ui.slider(
        start=50.5, stop=54.0, step=0.1, value=52.0,
        label="image distance $v_0$ (mm)", show_value=True,
    )
    aperture_slider = mo.ui.slider(
        start=2.0, stop=10.0, step=0.5, value=6.0,
        label="semi-aperture $A$ (mm)", show_value=True,
    )
    mo.hstack([focus_slider, aperture_slider], justify="start", gap=2)
    return aperture_slider, focus_slider


@app.cell
def _(LightFieldSpec, aperture_slider, calculate_light_field, focus_slider):
    spec = LightFieldSpec(
        image_distance_mm=focus_slider.value,
        aperture_radius_mm=aperture_slider.value,
    )
    result = calculate_light_field(spec)
    return result, spec


@app.cell
def _(mo, result):
    _geometry = result["geometry"]
    _rows = "\n".join(
        f"| {_row['label']} | {_row['object_distance_mm']:.0f} | {_row['beta']:.5f} "
        f"| {_row['ray_space_slope']:+.5f} | {_row['view_disparity_mm']:+.4f} |"
        for _row in result["layers"]
    )
    mo.md(f"""
    ## The scene

    Three opaque textured layers. The camera focuses at
    **{_geometry['focus_distance_mm']:.0f} mm** at **f/{_geometry['working_f_number']:.2f}**.

    For a layer imaged at \\(v\\), define \\(\\beta = v_0/v\\). Then that layer occupies a
    **straight line of slope \\(1-\\beta\\)** in ray space, and shifts by
    \\((1-\\beta)\\cdot 2A\\) between the two edges of the aperture.

    | layer | distance (mm) | \\(\\beta\\) | ray-space slope | disparity (mm) |
    | --- | --- | --- | --- | --- |
    {_rows}

    \\(\\beta = 1\\) is exactly in focus: slope zero, zero disparity. **Depth is slope.**
    """)
    return


@app.cell
def _(np, plt, result):
    _radiance = np.array(result["ray_space"]["radiance"])
    _u = np.array(result["ray_space"]["u_mm"])
    _s = np.array(result["ray_space"]["s_mm"])

    _figure, _axes = plt.subplots(figsize=(9.5, 4.2))
    _axes.imshow(
        _radiance, origin="lower", aspect="auto", cmap="inferno",
        extent=(float(_s[0]), float(_s[-1]), float(_u[0]), float(_u[-1])),
    )
    # Overlay the predicted slope for each layer through the field centre.
    for _row, _colour in zip(result["layers"], ("#4cc9f0", "#90ee90", "#ffd166")):
        _axes.plot(
            _row["ray_space_slope"] * _u, _u,
            color=_colour, lw=1.6, ls="--",
            label=f"{_row['label']}  slope {_row['ray_space_slope']:+.4f}",
        )
    _axes.set_xlabel("image-plane position $s$ (mm)")
    _axes.set_ylabel("aperture position $u$ (mm)")
    _axes.set_title("Ray space $L(u,s)$ — each depth is a family of parallel streaks")
    _axes.legend(loc="upper right", fontsize=8, framealpha=0.85)
    _axes.set_xlim(float(_s[0]), float(_s[-1]))
    _figure
    return


@app.cell
def _(mo):
    mo.md(r"""
    Read the streak tilts: the in-focus layer runs vertically, the near layer leans one
    way, the far layer the other. The dashed guides are the predicted slopes \(1-\beta\).

    The hard edges are **occlusion** boundaries, and they tilt too — an occluding edge has
    the slope of the *occluder*, which is why depth-from-focus misreads edges (below).

    ## Sub-aperture views: the same data as a camera array

    Take one row of ray space — fix \(u\) — and you have the scene viewed through one
    small part of the lens. A pinhole view. A light-field camera is a camera array that
    shares one lens.
    """)
    return


@app.cell
def _(np, plt, result):
    _views = np.array(result["sub_aperture"]["images"])
    _u_views = np.array(result["sub_aperture"]["u_mm"])
    _s = np.array(result["sub_aperture"]["s_mm"])

    _figure, _axes = plt.subplots(figsize=(9.5, 3.4))
    for _index, _u_value in enumerate(_u_views):
        _axes.plot(
            _s, _views[_index] + 0.35 * _index, lw=1.0,
            label=f"$u$ = {_u_value:+.1f} mm",
        )
    _axes.set_xlabel("image-plane position $s$ (mm)")
    _axes.set_ylabel("radiance (offset per view)")
    _axes.set_title("Sub-aperture views — features shift by their own disparity")
    _axes.legend(loc="upper right", fontsize=8, ncols=2, framealpha=0.85)
    _figure
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Refocusing is shear, then sum

    A photograph on a *different* plane sums along a **tilted** path. With
    \(\alpha = v_0/v\):

    $$I_\alpha(x) = \int L\big(u,\;\alpha x + u(1-\alpha)\big)\,\mathrm{d}u$$

    Shear ray space, then project. Whichever slope you straighten sums coherently into a
    sharp edge; every other slope smears. **Setting \(\alpha = \beta\) focuses that layer.**

    Drag the slider: the vertical dashed lines mark the three layer \(\beta\) values.
    """)
    return


@app.cell
def _(mo, result):
    _alphas = result["refocus"]["alpha"]
    refocus_slider = mo.ui.slider(
        start=0, stop=len(_alphas) - 1, step=1, value=len(_alphas) // 2,
        label=r"refocus $\alpha$ index", show_value=False,
    )
    refocus_slider
    return (refocus_slider,)


@app.cell
def _(np, plt, refocus_slider, result):
    _refocus = result["refocus"]
    _alphas = np.array(_refocus["alpha"])
    _photos = np.array(_refocus["photos"])
    _s = np.array(_refocus["s_mm"])
    _pick = int(refocus_slider.value)
    _distance = _refocus["focus_distance_mm"][_pick]

    _figure, _axes = plt.subplots(2, 1, figsize=(9.5, 6.0), height_ratios=(3, 2))
    _axes[0].imshow(
        _photos, origin="lower", aspect="auto", cmap="gray",
        extent=(float(_s[0]), float(_s[-1]), float(_alphas[0]), float(_alphas[-1])),
    )
    _axes[0].axhline(_alphas[_pick], color="#ff006e", lw=1.4)
    for _row in result["layers"]:
        _axes[0].axhline(_row["beta"], color="#4cc9f0", lw=0.9, ls="--")
    _axes[0].set_ylabel(r"refocus $\alpha$")
    _axes[0].set_title("Every refocused photograph at once (cyan = layer $\\beta$ values)")

    _label = "beyond range" if _distance is None else f"{_distance:.0f} mm"
    _axes[1].plot(_s, _photos[_pick], lw=1.2, color="#222222")
    _axes[1].set_xlabel("position $x$ (mm)")
    _axes[1].set_ylabel("radiance")
    _axes[1].set_title(rf"$\alpha$ = {_alphas[_pick]:.4f}  →  focused at {_label}")
    _axes[1].set_ylim(0.0, 1.05)
    _figure.tight_layout()
    _figure
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Depth from focus

    Sweep \(\alpha\), measure sharpness, and take the peak. Do it **per region** rather
    than over the whole field, or the peaks of different depths blend into one.

    One trap, and it is a real one: an **occlusion edge is sharpest when the occluder is
    in focus**, not the background. Measuring a backdrop in a thin sliver beside a near
    object returns the *near object's* distance. `calculate_light_field` therefore shrinks
    each region away from its borders by the widest defocus blur before measuring, and
    sets `edge_limited` when nothing survives.
    """)
    return


@app.cell
def _(np, plt, result):
    _refocus = result["refocus"]
    _alphas = np.array(_refocus["alpha"])

    _figure, _axes = plt.subplots(figsize=(9.5, 3.8))
    for _region, _colour in zip(_refocus["regions"], ("#e63946", "#2a9d8f", "#e9c46a")):
        _axes.plot(
            _alphas, _region["sharpness_normalized"], lw=1.5, color=_colour,
            label=f"{_region['label']}  →  {_region['recovered_distance_mm']:.0f} mm",
        )
        _axes.axvline(_region["beta"], color=_colour, lw=0.9, ls=":")
    _axes.set_xlabel(r"refocus $\alpha$")
    _axes.set_ylabel("normalized sharpness")
    _axes.set_title(r"Sharpness per visible region — peaks land on each layer's $\beta$ (dotted)")
    _axes.legend(loc="upper right", fontsize=8)
    _figure
    return


@app.cell
def _(mo, result):
    _rows = "\n".join(
        f"| {_region['label']} | {_truth:.0f} | {_region['recovered_distance_mm']:.0f} "
        f"| {100 * (_region['recovered_distance_mm'] - _truth) / _truth:+.1f}% "
        f"| {100 * _region['visible_fraction']:.0f}% | {_region['edge_limited']} |"
        for _region, _truth in (
            (_region, next(
                _row["object_distance_mm"] for _row in result["layers"]
                if _row["label"] == _region["label"]
            ))
            for _region in result["refocus"]["regions"]
        )
    )
    mo.md(f"""
    | region | true (mm) | recovered (mm) | error | visible | edge limited |
    | --- | --- | --- | --- | --- | --- |
    {_rows}

    **Error grows with distance**, and that is physics, not sloppiness. Disparity scales
    as \\(1/Z\\), so depth error scales as \\(Z^2\\). A light-field camera is a stereo rig
    whose **baseline is the lens aperture** — try the aperture slider at the top and watch
    the far layer's estimate improve as the baseline grows.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## The aperture is the baseline

    Sweeping the aperture makes the trade explicit: a wider aperture measures depth better
    and holds focus over a shorter range. Same knob, opposite directions.
    """)
    return


@app.cell
def _(LightFieldSpec, calculate_light_field, np, plt):
    _radii = np.array([2.0, 3.0, 4.5, 6.0, 8.0, 10.0])
    _errors = {}
    for _radius in _radii:
        _result = calculate_light_field(
            LightFieldSpec(aperture_radius_mm=float(_radius), refocus_count=81)
        )
        for _region in _result["refocus"]["regions"]:
            _truth = next(
                _row["object_distance_mm"] for _row in _result["layers"]
                if _row["label"] == _region["label"]
            )
            _errors.setdefault(_region["label"], []).append(
                abs(_region["recovered_distance_mm"] - _truth) / _truth * 100.0
            )

    _figure, _axes = plt.subplots(figsize=(9.5, 3.6))
    for _label, _values in _errors.items():
        _axes.plot(2 * _radii, _values, marker="o", lw=1.4, label=_label)
    _axes.set_xlabel("aperture diameter = stereo baseline (mm)")
    _axes.set_ylabel("depth error (%)")
    _axes.set_title("Depth accuracy improves with baseline; the far layer benefits most")
    _axes.set_yscale("log")
    _axes.legend(fontsize=8)
    _axes.grid(alpha=0.3, which="both")
    _figure
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Build your own scene

    `LightFieldLayer` takes an object distance, a lateral extent (which is what creates
    occlusion), and a texture. Use `"random"` for correspondence and depth work —
    `"bars"` is periodic and therefore **ambiguous** for matching, which is a mistake worth
    making once deliberately rather than by accident.
    """)
    return


@app.cell
def _(LightFieldLayer, LightFieldSpec, np, plt, sample_radiance):
    _custom = (
        LightFieldLayer(
            object_distance_mm=700.0, half_width_mm=18.0, center_mm=12.0,
            period_mm=0.8, brightness=1.0, seed=5, label="very near",
        ),
        LightFieldLayer(
            object_distance_mm=1300.0, half_width_mm=400.0, center_mm=0.0,
            period_mm=1.25, brightness=0.6, seed=6, label="in-focus backdrop",
        ),
    )
    _spec = LightFieldSpec(layers=_custom)
    _u = np.linspace(-_spec.aperture_radius_mm, _spec.aperture_radius_mm, 161)
    _s = np.linspace(-_spec.field_half_width_mm, _spec.field_half_width_mm, 513)
    _field = sample_radiance(
        _u[:, None], _s[None, :], layers=_custom,
        focal_length_mm=_spec.focal_length_mm,
        image_distance_mm=_spec.image_distance_mm,
    )

    _figure, _axes = plt.subplots(figsize=(9.5, 3.6))
    _axes.imshow(
        _field, origin="lower", aspect="auto", cmap="inferno",
        extent=(float(_s[0]), float(_s[-1]), float(_u[0]), float(_u[-1])),
    )
    _axes.set_xlabel("image-plane position $s$ (mm)")
    _axes.set_ylabel("aperture position $u$ (mm)")
    _axes.set_title("A strongly defocused near object in front of an in-focus backdrop")
    _figure
    return


@app.cell
def _(mo):
    mo.md(r"""
    The near object's streaks lean hard while the backdrop stays vertical, and the
    occluded wedge behind the near object is visible as the bow-tie gap: **different parts
    of the aperture see behind the occluder to different extents**. That is the parallax a
    plenoptic camera turns into depth — and it comes free from a single lens, with no
    second camera and no baseline occlusion gap.

    ---

    Next: `notebooks/plenoptic_cameras.py` builds the cameras that actually record this,
    and shows why plenoptic 1.0 and 2.0 are one design with a knob.
    """)
    return


if __name__ == "__main__":
    app.run()
