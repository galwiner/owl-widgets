# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo==0.24.0",
#     "owl-widgets==0.1.1",
# ]
# ///

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    from owl import (
        ApertureFocusStudy,
        ApertureStudySpec,
        PupilMapStudy,
        RayWaveStudy,
        StopRayStudy,
        StopStudySpec,
    )

    return (
        ApertureFocusStudy,
        ApertureStudySpec,
        PupilMapStudy,
        RayWaveStudy,
        StopRayStudy,
        StopStudySpec,
        mo,
    )


@app.cell
def _(mo):
    mo.md(r"""
    # Apertures

    A Gaussian waist propagates a distance $ to a lens and is focused. At the lens
    sits a **hard circular aperture**. Everything here is a Fresnel FFT, so the
    diffraction the aperture causes is in the answer rather than assumed away.

    87937w_L = w_0\sqrt{1 + (d/z_R)^2} \qquad z_R = \frac{\pi w_0^2}{\lambda}87937

    The beam radius at the lens is the natural yardstick. The studies compare the
    unclipped beam with aperture diameters \,w_L$, $, and /bin/sh.5\,w_L$. Each
    study has independent controls, results, and nearby interpretation.
    """)
    return


@app.cell
def _(ApertureFocusStudy, ApertureStudySpec, mo):
    focus_widget = mo.ui.anywidget(
        ApertureFocusStudy(ApertureStudySpec(grid_size=256))
    )
    focus_widget
    return (focus_widget,)


@app.cell
def _(focus_widget):
    focus_result = focus_widget.value["result"]
    return (focus_result,)


@app.cell
def _(focus_result, mo):
    _s = focus_result["spec"]
    _r = focus_result["gaussian_reference"]
    _sep = _r["geometric_image_z_mm"] - _r["true_waist_z_mm"]
    mo.md(rf"""
    ### 2f&ndash;2f: object at $2f$, image at $2f$

    | | value | |
    |:--|--:|:--|
    | waist $w_0$ | {_s['waist_mm']:g} mm | current control |
    | wavelength $\lambda$ | {_s['wavelength_nm'] / 1000:g} µm | current control |
    | waist to lens $s$ | {_s['distance_mm']:g} mm | current control |
    | **focal length $f$** | **{_s['focal_length_mm']:g} mm** | current control |
    | Rayleigh range $z_R$ | {_r['rayleigh_range_mm']:.0f} mm | $\pi w_0^2/\lambda$ |
    | beam at lens $w_L$ | {_r['lens_radius_mm']:.3f} mm | propagated Gaussian |
    | **geometric image plane** | $z = {_r['geometric_image_z_mm']:g}$ mm | thin-lens conjugate |
    | spot there | {_r['geometric_image_radius_mm'] * 1000:.0f} µm | magnification {_r['magnification']:.2f} |
    | **beam waist** | $z = {_r['true_waist_z_mm']:.0f}$ mm | from $q$ |
    | spot there | {_r['true_waist_radius_mm'] * 1000:.0f} µm | |

    Two planes, not one, and they are {_sep:.0f} mm apart. Rays identify the
    conjugate plane; the wave is narrowest at the Gaussian waist. The image plane
    is where the *pattern* is reproduced; the waist is where the *light* is
    concentrated. The defaults are a 2f&ndash;2f, 1:1 relay; when controls move,
    this reading follows the resulting conjugate and waist.
    """)
    return


@app.cell
def _(focus_result, mo):
    _ref = focus_result["gaussian_reference"]
    _scenarios = focus_result["scenarios"]
    _rows = []
    for _case in _scenarios:
        _ratio = _case["diameter_ratio"]
        _label = "none" if _ratio is None else f"{_ratio:g} w_L"
        _radius = "—" if _case["aperture_radius_mm"] is None else f"{_case['aperture_radius_mm'] * 1000:.0f} µm"
        _nf = "—" if _case["fresnel_number"] is None else f"{_case['fresnel_number']:.2f}"
        _rows.append(f"| {_label} | {_radius} | {_nf} | {_case['analytic_transmission']:.0%} | {_case['brightest_z_mm']:.0f} mm | {_case['focal_shift_mm']:+.0f} mm |")
    _table = "\n".join(_rows)
    _control = next(_x for _x in _scenarios if _x["diameter_ratio"] is None)
    _tight = min((_x for _x in _scenarios if _x["diameter_ratio"] is not None), key=lambda _x: _x["diameter_ratio"], default=None)
    _shift = "No clipped case is selected." if _tight is None else f"For the tightest aperture, {_tight["diameter_ratio"]:g} w_L, the brightest plane moves {abs(_tight['brightest_z_mm'] - _control['brightest_z_mm']):.0f} mm relative to the unclipped beam."
    _nfs = ", ".join(f"{_x['fresnel_number']:.2f}" for _x in _scenarios if _x["fresnel_number"] is not None)
    mo.md(rf"""
    ## What the aperture did

    Left is the $y=0$ section along $z$; right is the transverse spot at the
    brightest plane. A shared colour scale makes brightness comparable. The dashed
    reference is the unclipped $w(z)$ and its {_ref['true_waist_radius_mm'] * 1000:.0f} µm waist.

    | aperture $D/w_L$ | radius $a$ | $N_F=a^2/(\lambda f)$ | transmits | brightest plane | shift |
    |:--|--:|--:|--:|--:|--:|
    {_table}

    Clipping costs power, but it also **walks the waist upstream** and fills the
    spot with rings. {_shift} The controlling quantity is the Fresnel number:
    $N_F\gg1$ leaves the lens in charge, while $N_F\lesssim1$ lets diffraction from
    the hole set the beam. Current finite-aperture values: {_nfs or '—'}.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## The same apertures, traced as rays

    ABCD matrices move rays, and a ray is blocked or it is not. A bundle matched to
    the Gaussian has $\sigma_y=w_0/2$ and
    $\sigma_\theta=\lambda/(2\pi w_0)$, so free space gives
    $\sigma_y(z)=w(z)$. Its divergence is diffraction-limited, but it carries no
    **phase**: rays add in intensity and cannot interfere. The independent study
    below puts geometric and wave answers side by side.
    """)
    return


@app.cell
def _(ApertureStudySpec, RayWaveStudy, mo):
    ray_wave_widget = mo.ui.anywidget(
        RayWaveStudy(ApertureStudySpec())
    )
    ray_wave_widget
    return (ray_wave_widget,)


@app.cell
def _(ray_wave_widget):
    ray_wave_result = ray_wave_widget.value["result"]
    return (ray_wave_result,)


@app.cell
def _(mo, ray_wave_result):
    _ref = ray_wave_result["gaussian_reference"]
    _scenarios = ray_wave_result["scenarios"]
    _comparisons = ray_wave_result["image_plane_comparison"]["scenarios"]
    _by_ratio = {_x["diameter_ratio"]: _x for _x in _scenarios}
    _rows = []
    for _item in _comparisons:
        _ratio = _item["diameter_ratio"]
        _ray = _item["ray_encircled_incident_fraction"]
        _wave = _item["wave_encircled_incident_fraction"]
        _label = "none" if _ratio is None else f"{_ratio:g} w_L"
        _over = "—" if _ratio is None or _wave == 0 else f"{_ray / _wave:.1f}×"
        _rows.append(f"| {_label} | {_by_ratio[_ratio]['analytic_transmission']:.0%} | {_ray:.0%} | {_wave:.0%} | {_over} |")
    _table = "\n".join(_rows)
    _unclipped = next(_x for _x in _comparisons if _x["diameter_ratio"] is None)
    _tight = min((_x for _x in _comparisons if _x["diameter_ratio"] is not None), key=lambda _x: _x["diameter_ratio"], default=None)
    _reading = "Add a finite aperture to expose the disagreement." if _tight is None else f"At {_tight["diameter_ratio"]:g} w_L rays keep {_tight['ray_encircled_incident_fraction']:.0%} of incident power in the image spot; the wave keeps {_tight['wave_encircled_incident_fraction']:.0%}."
    mo.md(rf"""
    ### What the rays got right, and what they missed

    Unclipped, the bundle reproduces the lens beam, the
    {_ref['geometric_image_radius_mm'] * 1000:.0f} µm image-plane waist relay, and
    {_unclipped['ray_encircled_incident_fraction']:.0%} encircled energy.

    | aperture | transmits | in circle, rays | in circle, wave | rays overpredict by |
    |:--|--:|--:|--:|--:|
    {_table}

    The ray and transmission columns track: **an aperture removes rays and does
    nothing to survivors**. Rays therefore predict a dimmer but equally sharp image
    at ={_ref['geometric_image_z_mm']:g}$ mm. The wave mangles the survivors too.
    {_reading} Missing power is diffracted into rings and focal shift. This is the
    failure mode of a ray tolerance budget: stopped down looks dim but sharp until
    it is neither.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Aperture stops and field stops

    An **aperture stop** limits the cone from an axial point, setting NA, $/#,
    brightness, and spot size; its images are the entrance and exit pupils. A
    **field stop** limits which object points survive, setting field of view; its
    images are the entrance and exit windows. Anything at neither plane
    **vignettes**, partially clipping off-axis bundles.

    The marginal ray touches the aperture-stop rim; the chief ray runs from the
    field edge through its centre. Because a field stop needs an extended object,
    this study traces a row of object points rather than one axial beam.
    """)
    return


@app.cell
def _(StopRayStudy, StopStudySpec, mo):
    stop_ray_widget = mo.ui.anywidget(StopRayStudy(StopStudySpec()))
    stop_ray_widget
    return (stop_ray_widget,)


@app.cell
def _(stop_ray_widget):
    stop_ray_result = stop_ray_widget.value["result"]
    return (stop_ray_result,)


@app.cell
def _(mo, stop_ray_result):
    _records = stop_ray_result["stop_table"]
    _verdicts = {"aperture": "pure **aperture stop** — cone only", "field": "pure **field stop** — field only", "vignette": "**neither** — vignettes"}
    _rows = "\n".join(f"| {_x['label']} | {_x['z_mm']:g} mm | {_x['radius_mm']:g} mm | {_x['A_pupil']:+.2f} | {_x['B_field']:+.2f} | {_verdicts[_x['classification']]} |" for _x in _records)
    _by_id = {_x["id"]: _x for _x in _records}
    _a, _f, _v = _by_id["aperture"], _by_id["field"], _by_id["vignette"]
    _slide = abs(_v["B_field"] / _v["A_pupil"])
    _start = _v["radius_mm"] / abs(_v["A_pupil"]) - _a["radius_mm"]
    _end = _v["radius_mm"] / abs(_v["A_pupil"]) + _a["radius_mm"]
    _field_limit = _f["radius_mm"] / abs(_f["B_field"])
    mo.md(rf"""
    ### Reading the three panels

    A blocked ray satisfies $|Ap+Bh|>r$: $p$ is pupil height and $h$ is field height.

    | stop | $z$ | radius | $A$ (pupil) | $B$ (field) | what it is |
    |:--|--:|--:|--:|--:|:--|
    {_rows}

    - **$B=0$** clips the same cone at every field: an aperture stop.
    - **$A=0$** passes or kills each field point whole, with a cliff at
      $\pm {_field_limit:.1f}$ mm: a field stop.
    - **Both nonzero** slides the blocked region across the pupil at
      {_slide:.1f} mm/mm. Illumination rolls off from $|h|={_start:.1f}$ mm to
      {_end:.1f} mm.

    Position, not size, determines the taxonomy. The aperture stop sets NA and the
    spot; the field stop sets how much scene survives. Rays describe that exactly,
    but cannot say how large each surviving point becomes.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Field-dependent pupil

    With both pupil and field coefficients nonzero, the usable pupil changes with
    field. The off-axis bundle becomes the lens-shaped overlap of two circles: the
    **cat's eye**. This independent map shows that working aperture without
    inheriting the stop-ray controls.
    """)
    return


@app.cell
def _(PupilMapStudy, StopStudySpec, mo):
    pupil_map_widget = mo.ui.anywidget(PupilMapStudy(StopStudySpec()))
    pupil_map_widget
    return


if __name__ == "__main__":
    app.run()
