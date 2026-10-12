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
    from matplotlib.patches import Polygon
    from owl import PlenopticSpec, calculate_plenoptic, microlens_geometry

    return PlenopticSpec, Polygon, calculate_plenoptic, microlens_geometry, mo, np, plt


@app.cell
def _(mo):
    mo.md(r"""
    # Plenoptic 1.0 and 2.0 are one camera with a knob

    A microlens array of pitch \(d\) sits at \(z_\mu\) with the sensor \(b\) behind it, and
    every microlens obeys the same thin-lens law:

    $$\frac{1}{a} + \frac{1}{b} = \frac{1}{f_\mu}, \qquad |m| = \frac{b}{a}$$

    The camera families differ **only in which plane \(a\) refers to**:

    | mode | array position | microlenses focused on | microimages |
    | --- | --- | --- | --- |
    | `plenoptic_1` | on the image plane | the **aperture** (\(a = v_0\)) | pictures of the pupil |
    | `keplerian` | behind the image plane | the **image** (\(a > 0\)) | inverted scene patches |
    | `galilean` | in front of the image plane | the virtual image (\(a < 0\)) | erect scene patches |

    And one invariant holds throughout, because a pixel budget is a pixel budget:

    $$\text{spatial samples} \times \text{angular samples} = \text{total pixels}$$

    Companion notes: `docs/lightfield/02-plenoptic-1.md`, `03-plenoptic-2.md`,
    `04-rendering-and-depth.md`.
    """)
    return


@app.cell
def _(mo):
    mode_radio = mo.ui.radio(
        options={
            "plenoptic 1.0 (array on image plane)": "plenoptic_1",
            "plenoptic 2.0 Keplerian (array behind)": "keplerian",
            "plenoptic 2.0 Galilean (array in front)": "galilean",
        },
        value="plenoptic 2.0 Keplerian (array behind)",
        label="design",
    )
    offset_slider = mo.ui.slider(
        start=0.6, stop=6.0, step=0.1, value=3.0,
        label=r"array offset $|a|$ from image plane (mm)", show_value=True,
    )
    mo.hstack([mode_radio, offset_slider], justify="start", gap=2)
    return mode_radio, offset_slider


@app.cell
def _(PlenopticSpec, calculate_plenoptic, mode_radio, offset_slider):
    spec = PlenopticSpec(
        mode=mode_radio.value,
        microlens_offset_mm=0.0 if mode_radio.value == "plenoptic_1" else offset_slider.value,
    )
    result = calculate_plenoptic(spec)
    return result, spec


@app.cell
def _(mo, result):
    _g = result["geometry"]
    mo.md(f"""
    ## Where this design lands

    | quantity | value |
    | --- | --- |
    | conjugate \\(a\\) | {_g['conjugate_a_mm']:+.3f} mm |
    | sensor gap \\(b\\) | {_g['gap_b_mm']:.4f} mm |
    | array position \\(z_\\mu\\) | {_g['array_z_mm']:.2f} mm |
    | microlens magnification \\(\\|m\\| = b/a\\) | {_g['microlens_magnification']:.4f} |
    | matched patch \\(\\mu/p\\) | **{_g['matched_patch_pixels']:.2f} px** |
    | spatial samples | **{_g['spatial_samples_matched']:.0f}** |
    | angular samples | **{_g['angular_samples_matched']:.2f}** |
    | total pixels | {_g['total_pixel_count']} |
    | main lens / microlens \\(f/\\#\\) | f/{_g['main_f_number']:.2f} / f/{_g['microlens_f_number']:.2f} |
    | microimage fill ratio | {_g['microimage_fill_ratio']:.3f} |
    | pitch that would match exactly | {_g['matched_pitch_mm']:.4f} mm |

    Spatial × angular = {_g['spatial_samples_matched'] * _g['angular_samples_matched']:.0f},
    which is the pixel count. **Nothing is created; the split is chosen.**

    Switch to plenoptic 1.0 and watch the matched patch collapse below one pixel: that is the
    entire resolution penalty of the 1.0 design, and it is just \\(|m| \\approx f_\\mu/v_0\\).
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## What the sensor records

    Rows are microlenses, columns are pixels within each microimage. This is the raw frame,
    reshaped to make the structure visible.
    """)
    return


@app.cell
def _(np, plt, result):
    _raw = np.array(result["raw_sensor"]["values"])
    _fill = np.array(result["raw_sensor"]["aperture_fill"])

    _figure, _axes = plt.subplots(1, 2, figsize=(9.8, 4.0))
    _axes[0].imshow(_raw, origin="lower", aspect="auto", cmap="inferno")
    _axes[0].set_xlabel("pixel within microimage")
    _axes[0].set_ylabel("microlens index")
    _axes[0].set_title("raw sensor")
    _axes[1].imshow(_fill, origin="lower", aspect="auto", cmap="viridis", vmin=0, vmax=1)
    _axes[1].set_xlabel("pixel within microimage")
    _axes[1].set_title("fraction of rays inside the main aperture")
    _figure.tight_layout()
    _figure
    return


@app.cell
def _(mo):
    mo.md(r"""
    The right panel is **vignetting**, and it is not cosmetic: the edge of a microimage
    collects fewer rays than its centre, so a feature's brightness depends on where it sits.
    Flat-field this out *before* doing any correspondence, or the matcher is chasing an
    illumination gradient.

    ## One microimage, up close

    This is the difference between the two designs, in one plot.
    """)
    return


@app.cell
def _(np, plt, result, spec):
    _raw = np.array(result["raw_sensor"]["values"])
    _offsets = np.array(result["raw_sensor"]["pixel_offset_mm"])
    _picks = np.linspace(0, spec.lenslet_count - 1, 4).astype(int)

    _figure, _axes = plt.subplots(figsize=(9.5, 3.6))
    for _index in _picks:
        _axes.plot(
            _offsets * 1000.0, _raw[_index], lw=1.3, marker="o", ms=2.5,
            label=f"microlens {_index}",
        )
    _axes.set_xlabel(r"position within microimage ($\mu$m)")
    _axes.set_ylabel("signal")
    _axes.set_title(
        "Aperture image (flat-ish, vignetted) vs scene patch (structured)"
        if spec.mode == "plenoptic_1" else
        "Each microimage is a small picture of a scene patch"
    )
    _axes.legend(fontsize=8)
    _figure
    return


@app.cell
def _(mo, spec):
    mo.md(
        r"""
        In **plenoptic 1.0** each trace is a picture of the *main lens pupil* seen from one
        scene point: broad, smooth, and shaped by vignetting rather than by the scene. All the
        pixels under one microlens describe the same point, which is exactly why spatial
        resolution equals the microlens count.
        """
        if spec.mode == "plenoptic_1" else
        r"""
        In **plenoptic 2.0** each trace is a genuine small photograph of a scene region, so
        neighbouring pixels carry *different* spatial detail — that is where the resolution
        comes back. Notice that neighbouring microlenses show the **same features shifted**:
        the microimages overlap, and that shift is the disparity we use for depth.
        """
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## The sampling tiles in ray space

    Each pixel integrates a small parallelogram of \((u,s)\). Plenoptic 1.0 tiles are
    **upright** — a pixel pins \(u\) and spans the microlens in \(s\). The focused designs
    **shear** them: same area, same total information, finer along \(s\) and coarser along
    \(u\). That shear *is* the resolution trade, drawn.
    """)
    return


@app.cell
def _(Polygon, np, plt, result, spec):
    _tile_u = np.array(result["sampling_tiles"]["tile_u_mm"])
    _tile_s = np.array(result["sampling_tiles"]["tile_s_mm"])
    _lens_picks = np.linspace(0, spec.lenslet_count - 1, 5).astype(int)
    _pixel_picks = np.linspace(0, spec.pixels_per_lens - 1, 8).astype(int)

    _figure, _axes = plt.subplots(figsize=(9.5, 4.4))
    for _colour, _lens in zip(plt.cm.viridis(np.linspace(0, 0.9, len(_lens_picks))), _lens_picks):
        for _pixel in _pixel_picks:
            _axes.add_patch(Polygon(
                np.column_stack([_tile_s[_lens, _pixel], _tile_u[_lens, _pixel]]),
                closed=True, facecolor=_colour, edgecolor="black", lw=0.3, alpha=0.65,
            ))
    _axes.set_xlim(float(_tile_s.min()), float(_tile_s.max()))
    _axes.set_ylim(-spec.aperture_radius_mm * 1.1, spec.aperture_radius_mm * 1.1)
    _axes.axhline(spec.aperture_radius_mm, color="red", ls="--", lw=0.9)
    _axes.axhline(-spec.aperture_radius_mm, color="red", ls="--", lw=0.9)
    _axes.set_xlabel("image-plane position $s$ (mm)")
    _axes.set_ylabel("aperture position $u$ (mm)")
    _axes.set_title(f"Pixel sampling tiles in ray space — {spec.mode} (red = aperture limit)")
    _figure
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Full-resolution rendering

    Crop `patch_pixels` from the centre of each microimage, flip if the microimages are
    inverted, and tile the crops. That is the whole algorithm.

    The patch size chooses the plane you render, because tiling without gaps requires

    $$a' = \frac{d\,b}{\mu'}$$

    so **patch size and rendered plane are inverses**, and rendered resolution therefore
    depends on which depth you render. There is no single native resolution.
    """)
    return


@app.cell
def _(mo, result):
    _sweep = result["render"]["sweep"]
    patch_slider = mo.ui.slider(
        start=1, stop=len(_sweep), step=1,
        value=min(result["render"]["matched_patch_pixels"], len(_sweep)),
        label="patch size (pixels cropped per microimage)", show_value=True,
    )
    patch_slider
    return (patch_slider,)


@app.cell
def _(np, patch_slider, plt, result):
    _sweep = result["render"]["sweep"]
    _row = _sweep[int(patch_slider.value) - 1]
    _matched = result["geometry"]["matched_patch_pixels"]

    _figure, _axes = plt.subplots(2, 1, figsize=(9.5, 5.6), height_ratios=(2, 3))
    _axes[0].plot(_row["position_mm"], _row["image"], lw=0.9, color="#222222")
    _distance = _row["object_distance_mm"]
    _label = "no real object plane" if _distance is None else f"{_distance:.0f} mm"
    _axes[0].set_title(
        f"{_row['rendered_pixel_count']} rendered pixels   "
        f"$a'$ = {_row['conjugate_a_mm']:.3f} mm   →   {_label}"
    )
    _axes[0].set_xlabel("rendered position (mm)")
    _axes[0].set_ylabel("signal")

    _patches = [_item["patch_pixels"] for _item in _sweep]
    _ratios = [_item["seam_ratio"] for _item in _sweep]
    _valid = [(_p, _r) for _p, _r in zip(_patches, _ratios) if _r is not None]
    _axes[1].plot([_p for _p, _ in _valid], [_r for _, _r in _valid],
                  marker="o", lw=1.4, color="#3a86ff")
    _axes[1].axhline(1.0, color="grey", ls=":", lw=1.0)
    _axes[1].axvline(_matched, color="#e63946", ls="--", lw=1.2,
                     label=f"predicted matched patch = {_matched:.2f} px")
    _axes[1].axvline(_row["patch_pixels"], color="#222222", lw=1.0, alpha=0.5)
    _axes[1].set_yscale("log")
    _axes[1].set_xlabel("patch size (px)")
    _axes[1].set_ylabel("seam ratio (1 = seamless)")
    _axes[1].set_title("Seam continuity picks out the correct patch size")
    _axes[1].legend(fontsize=8)
    _figure.tight_layout()
    _figure
    return


@app.cell
def _(mo, result, spec):
    _best = result["render"]["best_seam_patch_pixels"]
    _matched = result["geometry"]["matched_patch_pixels"]
    _ratios = [_r["seam_ratio"] for _r in result["render"]["sweep"] if _r["seam_ratio"]]
    mo.md(
        f"""
        Best seam ratio **{min(_ratios):.2f}** at patch **{_best} px**, against a predicted
        matched patch of **{_matched:.2f} px**.

        """
        + (
            r"""
        For **plenoptic 1.0** the seam ratio never approaches 1 — it is in the hundreds. That
        is not a tuning failure: microimages here are pictures of the *aperture*, not of scene
        patches, so tiling crops of them is meaningless. Patch rendering is the **wrong
        algorithm** for 1.0; use shift-and-add over sub-aperture images instead. The matched
        patch of 1 px is the honest answer, and it is the 1.0 resolution penalty.
        """
            if spec.mode == "plenoptic_1" else
            r"""
        The seam minimum lands at or near the predicted patch — theory confirmed end to end.
        Where it sits slightly off, it is because **a single global patch size can only render
        one depth seamlessly**: the optimum settles between the patches matched to the
        different layers. Real renderers vary patch size per region, guided by the depth map
        below, which closes the loop.
        """
        )
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Depth, from the same number

    Adjacent microimages view a point at \(a'\) displaced by \(d\,b/a'\) — in pixels, exactly
    the matched patch size. So measuring the shift *measures the patch size*, and hence depth.

    Two things make this work, and both were mistakes worth making once:

    1. **Aperiodic texture.** A periodic target gives many equally good correlation peaks.
    2. **Wide enough overlap.** Mean-centred correlation of two samples is \(\pm 1\) for *any*
       pair, so a naive search pegs itself at the extreme shifts.

    Then the array's gift: microlens \(k\) against \(k{+}n\) must agree at \(n\Delta\), so
    scoring **many baselines** together collapses the false peaks. But the number of usable
    baselines is capped by \(a/b\) — the angular sampling. **The baselines you get are the
    angular resolution you paid for.**
    """)
    return


@app.cell
def _(np, plt, result):
    _estimates = result["depth"]["estimates"]
    _x = np.array([_e["center_mm"] for _e in _estimates])
    _z = np.array([
        np.nan if _e["object_distance_mm"] is None else _e["object_distance_mm"]
        for _e in _estimates
    ])
    _confident = np.array([_e["confident"] for _e in _estimates])

    _figure, _axes = plt.subplots(figsize=(9.5, 4.0))
    for _row, _colour in zip(result["layers"], ("#e63946", "#2a9d8f", "#e9c46a")):
        _axes.axhline(
            _row["object_distance_mm"], color=_colour, ls="--", lw=1.2,
            label=f"{_row['label']} = {_row['object_distance_mm']:.0f} mm",
        )
    _axes.scatter(_x[~_confident], _z[~_confident], s=26, facecolor="none",
                  edgecolor="grey", lw=0.9, label="low confidence")
    _axes.scatter(_x[_confident], _z[_confident], s=34, color="#3a86ff",
                  label="confident")
    _axes.set_xlabel("position across the array (mm)")
    _axes.set_ylabel("estimated object distance (mm)")
    _axes.set_yscale("log")
    _axes.set_title("Multi-baseline depth from microimage disparity")
    _axes.legend(fontsize=8, ncols=2)
    _figure
    return


@app.cell
def _(mo, result):
    _estimates = result["depth"]["estimates"]
    _confident = [_e for _e in _estimates if _e["confident"]]
    _rows = "\n".join(
        f"| {_r['label']} | {_r['conjugate_a_mm']:+.2f} | "
        + (f"{_r['expected_shift_pixels']:+.2f}" if _r["expected_shift_pixels"] else "n/a")
        + " | "
        + (f"{_r['microimage_blur_pixels']:.2f}" if _r["microimage_blur_pixels"] else "n/a")
        + " | "
        + (f"{_r['texture_cell_pixels']:.2f}" if _r["texture_cell_pixels"] else "n/a")
        + f" | {'yes' if _r['microimage_detail_resolved'] else '**no**'} |"
        for _r in result["layers"]
    )
    mo.md(f"""
    ## Microimage depth of field — the 2.0 limitation

    A microlens is focused on **one** plane. A layer whose image lands at \\(a' \\neq a\\) is
    defocused *inside its own microimage* by \\(d\\,|b-b'|/b'\\). Once that blur exceeds the
    scene detail in the microimage, the detail is gone and no rendering or matching recovers it.

    | layer | \\(a'\\) (mm) | disparity (px) | blur (px) | detail (px) | resolved? |
    | --- | --- | --- | --- | --- | --- |
    {_rows}

    Confident depth estimates: **{len(_confident)} of {len(_estimates)}** lenslet positions.

    So the two designs trade *different* limits: **plenoptic 1.0** works over a huge depth
    range at terrible resolution; **2.0** works at good resolution over a restricted range
    around its conjugate plane. Shrink the offset slider toward 0.6 mm and watch resolution
    climb while the blur column blows past the detail column — resolution and usable depth
    range pull directly against each other.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## The trade, across designs

    One sweep of the array offset shows the whole family at once.
    """)
    return


@app.cell
def _(PlenopticSpec, calculate_plenoptic, np, plt):
    _offsets = np.linspace(0.7, 6.0, 22)
    _series = {}
    for _mode in ("keplerian", "galilean"):
        _spatial, _angular, _blur = [], [], []
        for _offset in _offsets:
            if _mode == "keplerian" and _offset <= 0.55:
                _spatial.append(np.nan); _angular.append(np.nan); _blur.append(np.nan)
                continue
            _r = calculate_plenoptic(PlenopticSpec(
                mode=_mode, microlens_offset_mm=float(_offset), lenslet_count=11,
                lenslet_sample_count=9, pixel_sample_count=1, patch_sweep_max=6,
                depth_baseline_count=2,
            ))
            _spatial.append(_r["geometry"]["spatial_samples_matched"])
            _angular.append(_r["geometry"]["angular_samples_matched"])
            _blur.append(max(
                _row["microimage_blur_pixels"] or 0.0 for _row in _r["layers"]
            ))
        _series[_mode] = (_spatial, _angular, _blur)

    _figure, _axes = plt.subplots(1, 2, figsize=(9.8, 3.8))
    for _mode, (_spatial, _angular, _blur) in _series.items():
        _axes[0].plot(_offsets, _spatial, marker="o", ms=3, lw=1.3, label=f"{_mode} spatial")
        _axes[0].plot(_offsets, _angular, marker="s", ms=3, lw=1.3, ls="--",
                      label=f"{_mode} angular")
        _axes[1].plot(_offsets, _blur, marker="o", ms=3, lw=1.3, label=_mode)
    _axes[0].set_xlabel(r"array offset $|a|$ (mm)")
    _axes[0].set_ylabel("samples")
    _axes[0].set_yscale("log")
    _axes[0].set_title("Spatial rises as angular falls; product is fixed")
    _axes[0].legend(fontsize=7)
    _axes[1].set_xlabel(r"array offset $|a|$ (mm)")
    _axes[1].set_ylabel("worst microimage blur (px)")
    _axes[1].set_title("Small offset = high resolution = more blur")
    _axes[1].legend(fontsize=8)
    _figure.tight_layout()
    _figure
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## What to take away

    1. **One geometry.** All three designs are \(1/a + 1/b = 1/f_\mu\) with a different choice
       of conjugate plane. Plenoptic 1.0 is the \(a \to v_0\) limit, not a separate camera.
    2. **A fixed pixel budget.** Spatial × angular = total pixels, always. 2.0 does not create
       resolution; it re-divides the budget, continuously, by moving the array.
    3. **One number does three jobs.** The patch size is the crop width, the rendered plane,
       and the disparity — which is why depth estimation and rendering are the same measurement.
    4. **Every gain has a named cost.** 1.0 pays in resolution. 2.0 pays in microimage depth of
       field and in the baselines available for depth. Choosing \(a\) is choosing which cost.
    5. **It is a metrology problem.** Sub-pixel microimage registration, a calibrated \(b\), and
       aperiodic texture matter more than the algorithm — see `docs/lightfield/05-calibration.md`.
    """)
    return


if __name__ == "__main__":
    app.run()
