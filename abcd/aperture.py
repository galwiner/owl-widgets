# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo", "numpy", "matplotlib"]
# ///

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # Apertures

    A Gaussian waist propagates a distance $d$ to a lens and is focused. At the lens
    sits a **hard circular aperture**. Everything here is a Fresnel FFT, so the
    diffraction the aperture causes is in the answer rather than assumed away.

    The beam radius at the lens is the natural yardstick for the aperture:

    $$w_L = w_0\sqrt{1 + (d/z_R)^2} \qquad z_R = \frac{\pi w_0^2}{\lambda}$$

    Four panels: the unclipped beam as a control, then aperture **diameters**
    $2\,w_L$, $w_L$ and $0.5\,w_L$.
    """)
    return


@app.cell
def _():
    import marimo as mo
    import numpy as np
    import matplotlib.pyplot as plt

    return mo, np, plt


@app.cell
def _(np):
    def propagate(U, dx, wavelength, distance):
        """Fresnel free space: multiply by the paraxial transfer function in the
        spatial-frequency domain. dx, wavelength and distance share units."""
        ny, nx = U.shape
        FX, FY = np.meshgrid(np.fft.fftfreq(nx, d=dx), np.fft.fftfreq(ny, d=dx))
        H = np.exp(-1j * np.pi * wavelength * distance * (FX**2 + FY**2))
        return np.fft.ifft2(np.fft.fft2(U) * H)

    def z_slice(U, dx, wavelength, zs):
        """|U|^2 along y=0 at every z in zs. The angular spectrum of U does not
        change with distance, so one forward transform serves every plane."""
        ny, nx = U.shape
        FX, FY = np.meshgrid(np.fft.fftfreq(nx, d=dx), np.fft.fftfreq(ny, d=dx))
        F2, A = FX**2 + FY**2, np.fft.fft2(U)
        return np.array([
            np.abs(np.fft.ifft2(A * np.exp(-1j * np.pi * wavelength * z * F2))[ny // 2]) ** 2
            for z in zs
        ]).T

    def lens_phase(R2, wavelength, f):
        """Thin lens, same sign convention as propagate: exp(-i k r^2 / 2f)."""
        return np.exp(-1j * np.pi * R2 / (wavelength * f))

    def w_num(U, X):
        """1/e amplitude radius from the intensity second moment: w = 2 sigma.
        Honest for a Gaussian; a hard aperture puts power in Airy rings and the
        r^2 weighting makes this read high, so it is only used unclipped."""
        I = np.abs(U) ** 2
        return 2 * np.sqrt((I * X**2).sum() / I.sum())

    # the ABCD reference envelope, same helpers as the abcd notebook
    def q_waist(w0, lam):
        return 1j * np.pi * w0**2 / lam

    def w_of(q, lam):
        return np.sqrt(-lam / (np.pi * np.imag(1 / q)))

    def q_abcd(M, q):
        (A, B), (C, D) = M
        return (A * q + B) / (C * q + D)

    def free_M(dz):
        return np.array([[1.0, dz], [0.0, 1.0]])

    def lens_M(f):
        return np.array([[1.0, 0.0], [-1.0 / f, 1.0]])


    return (
        free_M,
        lens_M,
        lens_phase,
        propagate,
        q_abcd,
        q_waist,
        w_num,
        w_of,
        z_slice,
    )


@app.cell
def _(lens_M, mo, np, propagate, q_abcd, q_waist, w_num, w_of):
    # SI in the prompt, mm on the grid: w0 = 0.25e-3 m -> 0.25 mm, and so on.
    w0, lam, d = 0.25, 1e-3, 100.0
    f_lens = 50.0  # d = 2f: a 1:1 relay, image 2f past the lens

    zR = np.pi * w0**2 / lam  # 196 mm
    wL = w0 * np.sqrt(1 + (d / zR) ** 2)  # 0.281 mm

    # Where the beam actually goes, from q. In a 2f-2f relay the ray picture and
    # the beam picture part company, and both planes are worth having by name: the
    # geometric image is at 2f, but the beam's narrowest point is nowhere near it.
    q_out = q_abcd(lens_M(f_lens), q_waist(w0, lam) + d)  # q just past the lens
    z_waist = -np.real(q_out)             # 53 mm past the lens: the true narrowest point
    w_waist = w_of(q_out + z_waist, lam)  # 62 um
    z_img = 2 * f_lens                    # 100 mm past the lens: the geometric image
    w_img = w_of(q_out + z_img, lam)      # 250 um

    # a 2f-2f relay images the waist 1:1, and the wave picture agrees on the size
    assert np.isclose(w_img, w0, rtol=1e-3)
    # but not on where the beam is narrowest: zR = 196 mm swamps d - f = 50 mm, so
    # the waist lands barely past f rather than at the conjugate plane
    assert z_waist < 0.6 * z_img

    # Window sizing is the whole ballgame here. A hard 70 um hole diffracts at
    # ~lam/(pi a) = 4.5 mrad, so by the image plane the clipped light has spread
    # past 1 mm and an FFT window any narrower wraps it back onto the beam. Fourier
    # propagation is unitary, so that aliasing does NOT show up as lost power -- it
    # has to be found by widening the window and watching the answer move. Against
    # a 16 mm / 4096 reference, this grid is within 0.4% of peak everywhere plotted;
    # at 4 mm it was off by 21%. dx = 7.8 um is the price, and it is affordable
    # because only the aperture edge needs the resolution.
    # The lens phase is formally undersampled past r = 3.1 mm at f = 50, which is
    # 12 sigma out on a 0.28 mm beam -- it aliases nothing because it multiplies
    # nothing. Halve f again and that stops being true.
    N, width = 1024, 8.0
    dx = width / N
    span = (np.arange(N) - N // 2) * dx
    X, Y = np.meshgrid(span, span)
    R2 = X**2 + Y**2
    R = np.sqrt(R2)
    U0 = np.exp(-R2 / w0**2).astype(complex)

    # the grid carries the beam to the lens with the spot the closed form predicts
    assert np.isclose(w_num(propagate(U0, dx, lam, d), X), wL, rtol=1e-3)

    mo.md(
        f"""
        ### 2f&ndash;2f: object at $2f$, image at $2f$

        | | value | |
        |:--|--:|:--|
        | waist $w_0$ | {w0} mm | given |
        | wavelength $\lambda$ | {lam * 1e3:.0f} µm | given |
        | waist to lens $d$ | {d:g} mm | given |
        | **focal length $f$** | **{f_lens:g} mm** | **$d = 2f$** |
        | Rayleigh range $z_R$ | {zR:.0f} mm | $\pi w_0^2/\lambda$ |
        | beam at the lens $w_L$ | {wL:.3f} mm | $w_0\sqrt{{1 + (d/z_R)^2}}$ |
        | **geometric image plane** | $z$ = {d + z_img:g} mm | $2f$ past the lens |
        | spot there | {w_img * 1e3:.0f} µm | $= w_0$: a 1:1 relay |
        | **beam waist** | $z$ = {d + z_waist:.0f} mm | from $q$ |
        | spot there | {w_waist * 1e3:.0f} µm | |

        Two planes, not one, and they are {z_img - z_waist:.0f} mm apart. Rays say the
        lens relays the waist 1:1 onto the conjugate plane at $z$ = {d + z_img:g} mm,
        and the wave agrees exactly on the **size** there &mdash; {w_img * 1e3:.0f} µm,
        magnification $-1$. But the beam is narrowest {d + z_waist:.0f} mm in, at
        {w_waist * 1e3:.0f} µm, because $z_R$ = {zR:.0f} mm swamps $d - f$ = {d - f_lens:g} mm
        and Gaussian conjugates are not geometric ones. The image plane is where the
        *pattern* is reproduced; the waist is where the *light* is concentrated.

        Change `f_lens` above and everything below follows. The aperture Fresnel
        numbers $a^2/\lambda f$ go as $1/f$, so this lens roughly doubles them
        against the $f$ = 100 mm version.
        """
    )
    return (
        N,
        R,
        R2,
        U0,
        X,
        d,
        dx,
        f_lens,
        lam,
        q_out,
        span,
        w0,
        wL,
        w_img,
        w_waist,
        zR,
        z_img,
        z_waist,
    )


@app.cell
def _(
    N,
    R,
    R2,
    U0,
    X,
    d,
    dx,
    f_lens,
    lam,
    lens_phase,
    np,
    propagate,
    q_out,
    w0,
    wL,
    w_num,
    w_of,
    w_waist,
    zR,
    z_img,
    z_slice,
    z_waist,
):
    # aperture DIAMETER in units of w_L; inf is the unclipped control
    APERTURES = (np.inf, 2.0, 1.0, 0.5)
    # waist at 0, lens at 100, geometric image at 200, plus a little margin
    # so the image plane is not on the frame edge. Only a little: at z = 220
    # the smallest aperture's light starts wrapping and the 0.4% agreement
    # with a 16 mm / 4096 reference degrades to 1.8%.
    Z_END = d + z_img + 10

    # field arriving at the lens, already carrying the lens phase; the aperture is
    # applied on top of it, so everything upstream is shared between the panels
    U_lens = propagate(U0, dx, lam, d) * lens_phase(R2, lam, f_lens)

    # the unclipped beam waist is the brightest plane anywhere in this system, so
    # it sets the intensity scale for every panel: colour is comparable between
    # them and not just within one
    U_waist = propagate(U_lens, dx, lam, z_waist)
    ref_peak = (np.abs(U_waist) ** 2).max()
    assert np.isclose(w_num(U_waist, X), w_waist, rtol=1e-3)

    z_grid = np.linspace(0.0, Z_END, 180)
    _pre, _post = z_grid[z_grid <= d], z_grid[z_grid > d] - d
    pre_slice = z_slice(U0, dx, lam, _pre)

    def aperture(k):
        """The field just past a hard aperture of diameter k*wL at the lens.

        Edge feathered over one pixel. The smallest hole is 9 px in radius and a
        raw boolean circle rasterises into something square: its rings came out
        33% brighter on the diagonal than on the axis, which is a picture of the
        grid, not of the optics. Feathering drops that to 8%.
        ponytail: 8% azimuthal error remains; N=4096 gets to 4% at 50x the cost."""
        return U_lens * np.clip((k * wL / 2 - R) / dx + 0.5, 0.0, 1.0)

    def clipped(k):
        """For a hard aperture of diameter k*wL at the lens (inf = none):
        (y=0 intensity slice over z, throughput, brightest z, field at that z).

        Brightest on-axis plane, not narrowest second moment -- once the beam is
        truncated the rings dominate the r^2 weighting and w_num stops meaning
        anything, while peak irradiance is what a focus is actually for."""
        Ua = aperture(k)
        post = z_slice(Ua, dx, lam, _post)
        T = (np.abs(Ua) ** 2).sum() / (np.abs(U_lens) ** 2).sum()
        z_peak = _post[post[N // 2].argmax()]
        return np.hstack([pre_slice, post]), T, d + z_peak, propagate(Ua, dx, lam, z_peak)

    panels = {k: clipped(k) for k in APERTURES}

    # A hard circular cut of a Gaussian passes 1 - exp(-2 a^2 / w^2); inf passes
    # all. The 4% is the feathered edge, which squares to slightly less power than
    # it covers -- the accuracy floor of the smallest aperture here. The panels
    # quote the closed form, since throughput is a property of the hole and not of
    # the grid; this is the check that the grid agrees.
    for _k, (_, _T, _, _) in panels.items():
        assert np.isclose(_T, 1 - np.exp(-(_k**2) / 2), rtol=4e-2), (_k, _T)
    # unclipped, the FFT finds the waist where q says it is, at the size q says
    assert abs(panels[np.inf][2] - (d + z_waist)) < 2.0
    assert np.isclose(w_num(panels[np.inf][3], X), w_waist, rtol=1e-3)

    # unclipped w(z) through the same system, straight from q
    w_ref = np.concatenate([
        w0 * np.sqrt(1 + (_pre / zR) ** 2),
        [w_of(q_out + z, lam) for z in _post],
    ])
    return APERTURES, U_lens, Z_END, aperture, panels, ref_peak, w_ref, z_grid


@app.cell
def _(
    APERTURES,
    Z_END,
    d,
    f_lens,
    np,
    panels,
    plt,
    ref_peak,
    span,
    wL,
    w_ref,
    w_waist,
    z_grid,
    z_img,
    z_waist,
):
    _fig = plt.figure(figsize=(11.5, 13))
    _gs = _fig.add_gridspec(len(APERTURES), 2, width_ratios=[2, 1],
                            wspace=0.12, hspace=0.30)
    _norm = plt.matplotlib.colors.LogNorm(vmin=1e-3, vmax=1.0)
    _crop = 0.22  # mm, shared by every cross section so the spots are comparable
    _shareL = _shareR = None

    for _i, _k in enumerate(APERTURES):
        _sl, _T, _zp, _Up = panels[_k]
        _a = _k * wL / 2
        _last = _i == len(APERTURES) - 1

        # --- left: the y = 0 section along z
        _ax = _fig.add_subplot(_gs[_i, 0], sharex=_shareL, sharey=_shareL)
        _shareL = _shareL or _ax
        _ax.imshow(
            _sl / ref_peak,
            extent=[z_grid[0], z_grid[-1], span[0], span[-1]],
            origin="lower",
            aspect="auto",
            cmap="inferno",
            norm=_norm,
        )
        _ax.plot(z_grid, w_ref, "w--", lw=1, alpha=0.7)
        _ax.plot(z_grid, -w_ref, "w--", lw=1, alpha=0.7,
                 label="unclipped $w(z)$, ABCD")
        if np.isfinite(_k):  # the two jaws at the lens plane
            _ax.plot([d, d], [_a, span[-1]], color="c", lw=3, solid_capstyle="butt")
            _ax.plot([d, d], [-_a, span[0]], color="c", lw=3, solid_capstyle="butt",
                     label="aperture")
            _title = (f"D = {_k:g} $w_L$ = {2 * _a * 1000:.0f} µm   "
                      f"(radius {_a * 1000:.0f} µm)   "
                      f"transmits {1 - np.exp(-(_k**2) / 2):.0%}   "
                      f"waist shift {_zp - d - z_waist:+.0f} mm")
        else:
            _ax.axvline(d, color="c", lw=1, alpha=0.5, label="lens")
            _title = (f"no aperture   transmits 100%   waist at z = {_zp:.0f} mm, "
                      f"geometric image at z = {d + z_img:g} mm")
        _ax.axvline(d + z_img, color="w", lw=0.9, ls=":", alpha=0.7,
                   label="geometric image plane")
        _ax.axvline(_zp, color="lime", lw=1.2,
                    label=f"brightest plane, z = {_zp:.0f} mm")
        _ax.set(ylabel="y (mm)", ylim=(-0.75, 0.75), xlim=(0, Z_END), title=_title)
        _ax.title.set_fontsize(10)
        _ax.tick_params(labelbottom=_last)

        # --- right: the transverse spot at that brightest plane
        _axr = _fig.add_subplot(_gs[_i, 1], sharex=_shareR, sharey=_shareR)
        _shareR = _shareR or _axr
        _axr.imshow(
            np.abs(_Up) ** 2 / ref_peak,
            extent=[span[0], span[-1], span[0], span[-1]],
            origin="lower",
            cmap="inferno",
            norm=_norm,
        )
        # same reference in both columns: the spot the unclipped beam would make
        _axr.add_patch(plt.Circle((0, 0), w_waist, fill=False, ec="w", ls="--", lw=1))
        _axr.set(
            xlim=(-_crop, _crop),
            ylim=(-_crop, _crop),
            ylabel="y (mm)",
            title=f"$z$ = {_zp:.0f} mm,   peak {np.abs(_Up).max() ** 2 / ref_peak:.2f}",
        )
        _axr.set_aspect("equal")
        _axr.title.set_fontsize(9)
        _axr.tick_params(labelbottom=_last, labelsize=8)

    _shareL.legend(loc="upper left", fontsize=8, framealpha=0.5)
    _fig.axes[-2].set_xlabel("z (mm)     — waist at 0, lens + aperture at 100, "
                             "geometric image at 200")
    _fig.axes[-1].set_xlabel("x (mm)")
    _fig.suptitle(
        f"$|U|^2$, log scale over 3 decades of the unclipped waist peak. Dashed "
        f"circle is the unclipped waist, $w$ = {w_waist * 1000:.0f} µm."
        f"\n$w_0$ = 0.25 mm, $\\lambda$ = 1 µm, $d$ = {d:g} mm, "
        f"$f$ = {f_lens:g} mm, $w_L$ = {wL:.3f} mm",
        fontsize=10,
    )
    _fig.tight_layout(rect=[0, 0, 1, 0.975])
    _fig
    return


@app.cell
def _(APERTURES, d, f_lens, lam, mo, np, panels, wL, w_waist, z_waist):
    # joined with the template's own indent: mo.md dedents by the common
    # leading whitespace, and unindented rows would drop it to zero and
    # leave every other line looking like a markdown code block
    _rows = "\n    ".join(
        f"| {'none' if not np.isfinite(_k) else f'${_k:g}\,w_L$'} "
        f"| {'—' if not np.isfinite(_k) else f'{_k * wL / 2 * 1e3:.0f} µm'} "
        f"| {'—' if not np.isfinite(_k) else f'{(_k * wL / 2) ** 2 / (lam * f_lens):.2f}'} "
        f"| {1 - np.exp(-(_k**2) / 2):.0%} "
        f"| {panels[_k][2]:.0f} mm "
        f"| {panels[_k][2] - (d + z_waist):+.0f} mm |"
        for _k in APERTURES
    )

    mo.md(
        f"""
        ## What the aperture did

        Left, the $y$=0 section along $z$; right, the transverse spot at the brightest
        plane. Every panel shares one colour scale, so brightness is comparable across
        the whole grid. The dashed reference is the beam the ray-matrix picture still
        insists you have &mdash; the unclipped $w(z)$ on the left, the unclipped waist
        ({w_waist * 1e3:.0f} µm) on the right.

        | aperture $D$ | radius $a$ | $N_F = a^2/\lambda f$ | transmits | brightest plane | shift |
        |:--|--:|--:|--:|--:|--:|
        {_rows}

        Clipping does two things at once, and only one of them is obvious. It costs
        power &mdash; that is the transmission column, and it is exactly what a ray
        budget predicts. It also **walks the waist upstream**, by
        {abs(panels[0.5][2] - panels[np.inf][2]):.0f} mm at the tightest aperture, and
        fills the spot with rings. Neither of those is in the transmission column.

        The knob is the aperture's **Fresnel number** $N_F = a^2/\lambda f$. At
        $N_F \gg 1$ the hole is a bystander and the lens sets the beam; at
        $N_F \lesssim 1$ the diffraction spread of the hole beats the convergence
        angle of the lens and the hole sets the beam. This $f$ = {f_lens:g} mm lens
        puts the three apertures at
        {", ".join(f"{(_k * wL / 2) ** 2 / (lam * f_lens):.2f}" for _k in APERTURES if np.isfinite(_k))}
        &mdash; straddling the transition, which is why the top row still focuses and
        the bottom one does not.
        """
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## The same apertures, traced as rays

    ABCD matrices move rays, and a ray is blocked or it is not. Feed the lens a
    bundle whose statistics match the Gaussian &mdash; at the waist, height and angle
    independent with $\sigma_y = w_0/2$ and $\sigma_\theta = \lambda/2\pi w_0$
    &mdash; and free space gives $2\sigma_y(z) = w(z)$ exactly. So the bundle already
    carries the beam's diffraction-limited divergence.

    What it cannot carry is **phase**. Rays add in intensity; nothing in this
    section can interfere. Everything the previous figure showed that this one does
    not is therefore diffraction, cleanly separated.
    """)
    return


@app.cell
def _(
    APERTURES,
    R,
    U_lens,
    aperture,
    d,
    dx,
    f_lens,
    free_M,
    lam,
    lens_M,
    np,
    propagate,
    w0,
    wL,
    w_img,
    z_img,
):
    N_RAYS = 1_000_000
    Z_SPOT = d + z_img  # compare both models in the plane the relay images onto

    def ray_step(M, Y, T):
        """Apply one ABCD matrix to a bundle of (height, angle) pairs. Y and T are
        (2, n): the same matrix acts on the x and y axes independently."""
        return M[0, 0] * Y + M[0, 1] * T, M[1, 0] * Y + M[1, 1] * T

    sig_y, sig_t = w0 / 2, lam / (2 * np.pi * w0)
    _rng = np.random.default_rng(0)
    _Y0 = _rng.normal(0.0, sig_y, (2, N_RAYS))
    _T0 = _rng.normal(0.0, sig_t, (2, N_RAYS))

    _YL, _TL = ray_step(free_M(d), _Y0, _T0)       # up to the lens
    r_lens = np.hypot(_YL[0], _YL[1])              # where the aperture bites
    _YF, _TF = ray_step(lens_M(f_lens), _YL, _TL)  # through it

    # unclipped, the bundle reproduces both closed forms it should: w_L at the lens
    # and, at the conjugate plane, the waist relayed 1:1
    assert np.isclose(2 * _YL[0].std(), wL, rtol=5e-3)
    assert np.isclose(2 * ray_step(free_M(z_img), _YF, _TF)[0][0].std(), w_img, rtol=5e-3)

    # coarser than the wave grid: these are Monte Carlo counts, and 2 dx bins keep
    # four times the rays per bin without blurring a 250 um spot
    spot_edges = np.arange(-0.6, 0.6 + 2 * dx, 2 * dx)

    def ray_spot(k):
        """(2D histogram at Z_SPOT, fraction of the *incident* power inside the
        unclipped image spot)."""
        _keep = r_lens <= k * wL / 2
        _Y, _ = ray_step(free_M(z_img), _YF[:, _keep], _TF[:, _keep])
        _H, _, _ = np.histogram2d(_Y[0], _Y[1], bins=(spot_edges, spot_edges))
        return _H.T, (np.hypot(_Y[0], _Y[1]) < w_img).sum() / N_RAYS

    def wave_spot(k):
        """Same plane, same metric, from the Fresnel field."""
        _I = np.abs(propagate(aperture(k), dx, lam, z_img)) ** 2
        return _I, _I[R < w_img].sum() / (np.abs(U_lens) ** 2).sum()

    rays = {k: ray_spot(k) for k in APERTURES}
    waves = {k: wave_spot(k) for k in APERTURES}
    ray_peak = rays[np.inf][0].max()
    img_peak = waves[np.inf][0].max()  # this figure is scaled to the plane it shows

    # a Gaussian spot puts 1 - 1/e^2 inside its own w, and both models agree
    assert np.isclose(rays[np.inf][1], 1 - np.exp(-2.0), rtol=2e-2)
    assert np.isclose(waves[np.inf][1], 1 - np.exp(-2.0), rtol=2e-2)

    # A small deterministic fan for the diagram: the +/-2 sigma corners of the same
    # phase space, which is where w(z) and the divergence angle both live. Grouped
    # by launch height, because at d = 2f this is a 1:1 inverting relay -- every ray
    # leaving one point of the object plane lands on one point of the image plane,
    # whatever its angle, and that is what "imaging" means.
    FAN_HEIGHTS = np.linspace(-w0, w0, 5)
    _g = np.meshgrid(FAN_HEIGHTS, np.linspace(-lam / (np.pi * w0), lam / (np.pi * w0), 11),
                     indexing="ij")
    fan_y0, fan_t0 = _g[0].ravel(), _g[1].ravel()
    fan_yL, _ftL = ray_step(free_M(d), fan_y0, fan_t0)
    fan_yEnd = fan_yL + z_img * ray_step(lens_M(f_lens), fan_yL, _ftL)[1]

    # the imaging condition, as a check: magnification -1, angle irrelevant
    assert np.allclose(fan_yEnd, -fan_y0, atol=1e-9)
    return (
        FAN_HEIGHTS,
        Z_SPOT,
        fan_y0,
        fan_yEnd,
        fan_yL,
        img_peak,
        ray_peak,
        ray_step,
        rays,
        spot_edges,
        waves,
    )


@app.cell
def _(
    APERTURES,
    FAN_HEIGHTS,
    Z_END,
    Z_SPOT,
    d,
    fan_y0,
    fan_yEnd,
    fan_yL,
    img_peak,
    np,
    plt,
    ray_peak,
    rays,
    span,
    spot_edges,
    wL,
    w_img,
    w_ref,
    waves,
    z_grid,
):
    _fig = plt.figure(figsize=(13, 12))
    _gs = _fig.add_gridspec(len(APERTURES), 3, width_ratios=[2, 1, 1],
                            wspace=0.16, hspace=0.32)
    _norm = plt.matplotlib.colors.LogNorm(vmin=1e-3, vmax=1.0)
    _crop = 0.55
    _fan_colors = plt.cm.cool(np.linspace(0, 1, len(FAN_HEIGHTS)))
    _shareL = _shareS = None

    for _i, _k in enumerate(APERTURES):
        _a = _k * wL / 2
        _last = _i == len(APERTURES) - 1
        _H, _enc_r = rays[_k]
        _I, _enc_w = waves[_k]

        # --- left: the ray fan itself, blocked rays stopping at the aperture
        _ax = _fig.add_subplot(_gs[_i, 0], sharex=_shareL, sharey=_shareL)
        _shareL = _shareL or _ax
        _ax.set_facecolor("black")
        _stop = np.abs(fan_yL) > _a
        for _j in np.flatnonzero(_stop):
            _ax.plot([0, d], [fan_y0[_j], fan_yL[_j]], color="#ff4d4d", lw=0.6, alpha=0.8)
        for _j in np.flatnonzero(~_stop):
            _ax.plot([0, d, Z_END], [fan_y0[_j], fan_yL[_j], fan_yEnd[_j]], lw=0.7,
                     alpha=0.9, color=_fan_colors[np.argmin(abs(FAN_HEIGHTS - fan_y0[_j]))])
        _ax.plot(z_grid, w_ref, "w--", lw=1, alpha=0.6)
        _ax.plot(z_grid, -w_ref, "w--", lw=1, alpha=0.6, label="Gaussian $w(z)$")
        if np.isfinite(_k):
            _ax.plot([d, d], [_a, 0.75], color="c", lw=3, solid_capstyle="butt")
            _ax.plot([d, d], [-_a, -0.75], color="c", lw=3, solid_capstyle="butt",
                     label="aperture")
            _title = (f"D = {_k:g} $w_L$   {(~_stop).sum()}/{len(_stop)} fan rays pass"
                      f"   {_stop.sum()} blocked (red)")
        else:
            _ax.axvline(d, color="c", lw=1, alpha=0.5, label="lens")
            _title = "no aperture   every ray passes"
        _ax.axvline(Z_SPOT, color="w", lw=0.7, ls=":", alpha=0.6)
        _ax.set(ylabel="y (mm)", ylim=(-0.75, 0.75), xlim=(0, Z_END), title=_title)
        _ax.title.set_fontsize(10)
        _ax.tick_params(labelbottom=_last)
        if _last:
            _ax.set_xlabel("z (mm)")

        # --- middle and right: the same plane, two models
        for _c, (_img, _peak, _enc, _tag) in enumerate((
            (_H, ray_peak, _enc_r, "rays"),
            (_I, img_peak, _enc_w, "wave"),
        )):
            _e = spot_edges if _c == 0 else span
            _axs = _fig.add_subplot(_gs[_i, _c + 1], sharex=_shareS, sharey=_shareS)
            _shareS = _shareS or _axs
            _axs.set_facecolor("black")  # empty Monte Carlo bins are 0, not missing
            _axs.imshow(_img / _peak, extent=[_e[0], _e[-1], _e[0], _e[-1]],
                        origin="lower", cmap="inferno", norm=_norm)
            _axs.add_patch(plt.Circle((0, 0), w_img, fill=False, ec="w", ls="--", lw=1))
            _axs.set(xlim=(-_crop, _crop), ylim=(-_crop, _crop),
                     title=f"{_tag}   peak {_img.max() / _peak:.2g}   "
                           f"in circle {_enc:.0%}")
            _axs.set_aspect("equal")
            _axs.title.set_fontsize(9)
            _axs.tick_params(labelbottom=_last, labelleft=_c == 0, labelsize=8)
            if _c == 0:
                _axs.set_ylabel("y (mm)")
            if _last:
                _axs.set_xlabel("x (mm)")

    _shareL.legend(loc="upper left", fontsize=8, framealpha=0.75)
    _fig.suptitle(
        f"Rays cannot interfere. Colour groups the fan by launch height: at "
        f"$d = 2f$ each group lands on one point of the image plane.\nBoth spot "
        f"columns are at $z$ = {Z_SPOT:g} mm, the geometric image; dashed circle is "
        f"the unclipped spot there, $w$ = {w_img * 1000:.0f} µm, and \"in circle\" "
        f"is the fraction of the *incident* power inside it.",
        fontsize=10,
    )
    _fig.tight_layout(rect=[0, 0, 1, 0.965])
    _fig
    return


@app.cell
def _(APERTURES, Z_SPOT, mo, np, panels, rays, w_img, waves):
    # joined with the template's own indent: mo.md dedents by the common
    # leading whitespace, and unindented rows would drop it to zero and
    # leave every other line looking like a markdown code block
    _rows = "\n    ".join(
        f"| {'none' if not np.isfinite(_k) else f'${_k:g}\,w_L$'} "
        f"| {1 - np.exp(-(_k**2) / 2):.0%} "
        f"| {rays[_k][1]:.0%} | {waves[_k][1]:.0%} "
        f"| {'—' if not np.isfinite(_k) else f'{rays[_k][1] / waves[_k][1]:.1f}×'} |"
        for _k in APERTURES
    )

    mo.md(
        f"""
        ### What the rays got right, and what they missed

        The bundle is not a straw man. Unclipped it reproduces $w_L$ at the lens, the
        1:1 relay of the waist at the image plane ({w_img * 1e3:.0f} µm) and
        {rays[np.inf][1]:.0%} encircled energy, all to a fraction of a percent. Its
        divergence *is* the diffraction-limited one. Then the aperture goes in:

        | aperture | transmits | in circle, rays | in circle, wave | rays overpredict by |
        |:--|--:|--:|--:|--:|
        {_rows}

        Read the ray column against the transmission column: they track each other.
        That is the whole geometric story &mdash; **an aperture removes rays and does
        nothing to the ones it lets through**. Whatever survives still lands where it
        was aimed, so the image only ever gets dimmer, never worse, and it never moves
        off $z$ = {Z_SPOT:g} mm.

        The wave column says the aperture also mangles the survivors. At
        $0.5\,w_L$ the rays keep {rays[0.5][1]:.0%} of the incident power inside the
        image spot; the real beam keeps {waves[0.5][1]:.0%}. The difference is not
        absorbed anywhere &mdash; it is diffracted out of the core into rings and into
        the {abs(panels[0.5][2] - panels[np.inf][2]):.0f} mm waist shift, and rays have
        no representation for either, because both are interference.

        This is the practical failure mode of a ray-based tolerance budget: it will
        tell you a stopped-down system is dim but sharp, right up to the point where
        it is neither.
        """
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Aperture stops and field stops

    Every opening in a system does one of three jobs, and which job depends only on
    **where it sits**, not on how big it is.

    - The **aperture stop** limits the *cone* accepted from the on-axis object
      point. It sets NA and $f$/#, so it sets both how bright the image is and how
      small a spot the system can make. Its image in object space is the **entrance
      pupil**; in image space, the **exit pupil**.
    - The **field stop** limits *which object points* get through at all. It sets
      the field of view. It lives at or near an image plane &mdash; in a camera it is
      the sensor edge. Its images are the **entrance** and **exit windows**.
    - Anything at neither a pupil nor a window **vignettes**: it clips off-axis
      bundles partially, so the image fades toward the corners.

    Two rays name the pair. The **marginal ray** runs from the axial object point to
    the *rim* of the aperture stop; the **chief ray** runs from the edge of the field
    through the *centre* of the aperture stop. The stop the marginal ray touches is
    the aperture stop; the one the chief ray touches is the field stop.

    This is a purely geometric story, so this section is rays only &mdash; but it is
    the same 2f&ndash;2f relay, the same two matrices, and it connects straight back:
    the aperture stop *is* the aperture the earlier sections were diffracting off.

    A field stop needs something to cut, so the object here is **extended**: a row
    of points across the object plane rather than one beam on the axis.
    """)
    return


@app.cell
def _(d, f_lens, free_M, lens_M, np, ray_step, z_img):
    Z_SEC = d + z_img + 40  # rays need no FFT window, so this frame can run past the image
    N_PUP, R_SAMPLE = 20_000, 0.9  # rays per field point, and the lens's own clear radius

    # (z, radius) for every opening in the path. Only the position distinguishes them.
    STOP_A = (d, 0.5)                # on the lens: at the pupil plane
    STOP_F = (d + z_img, 1.2)        # at the image plane: at a window
    STOP_V = (d + 0.5 * z_img, 0.8)  # halfway: at neither

    STOPS = {
        "aperture stop only — iris on the lens": [STOP_A],
        "+ field stop at the image plane": [STOP_A, STOP_F],
        "+ a stop halfway to the image": [STOP_A, STOP_V],
    }

    def ray_y(z, y0, t0):
        """Ray height at absolute z, for rays leaving the object plane at (y0, t0).
        The same two matrices as everywhere else, evaluated at an arbitrary plane."""
        _yl, _tl = ray_step(lens_M(f_lens), *ray_step(free_M(d), y0, t0))
        z = np.asarray(z, float)
        return np.where(z <= d, y0 + z * t0, _yl + (z - d) * _tl)

    # One fixed pupil sample, reused for every field height: common random numbers,
    # so the illumination curve is smooth instead of Monte Carlo hash. Sampling only
    # inside R_SAMPLE makes the lens rim an implicit stop, which is what glass is.
    _u = np.random.default_rng(1).random((2, N_PUP))
    pupil_xy = R_SAMPLE * np.sqrt(_u[0]) * np.array(
        [np.cos(2 * np.pi * _u[1]), np.sin(2 * np.pi * _u[1])]
    )

    def stop_pass(stops, h):
        """Which pupil-sampled rays from field height h clear every stop."""
        _Y0 = np.zeros((2, N_PUP))
        _Y0[1] = h
        _T0 = (pupil_xy - _Y0) / d
        _ok = np.ones(N_PUP, bool)
        for _z, _r in stops:
            _P = ray_y(_z, _Y0, _T0)
            _ok &= np.hypot(_P[0], _P[1]) <= _r
        return _ok

    field_h = np.linspace(-2.4, 2.4, 49)
    _raw = {n: np.array([stop_pass(s, h).mean() for h in field_h]) for n, s in STOPS.items()}
    illum = {n: v / v[len(field_h) // 2] for n, v in _raw.items()}  # relative to on-axis

    _names = list(STOPS)
    _edge = np.abs(field_h) > 1.4
    # an aperture stop at the pupil is field-blind: same cone from every point
    assert np.allclose(illum[_names[0]], 1.0, atol=0.02)
    # a stop at the image plane is a cliff -- full transmission, then nothing
    assert illum[_names[1]][np.abs(field_h) < 1.1].min() > 0.98
    assert illum[_names[1]][np.abs(field_h) > 1.3].max() < 0.02
    # a stop at neither plane rolls off gradually: that is vignetting
    assert 0.02 < illum[_names[2]][_edge].max() < 0.7
    assert np.all(np.diff(illum[_names[2]][field_h >= 0]) <= 1e-9)

    # the pupil as each field point sees it, for the vignetting case: the cat's eye
    PUPIL_FIELDS = (0.0, 1.4, 1.8, 2.05)
    pupil_maps = {h: stop_pass(STOPS[_names[2]], h) for h in PUPIL_FIELDS}

    FAN_FIELDS = np.linspace(-2.0, 2.0, 5)
    FAN_PUPIL = np.linspace(-R_SAMPLE, R_SAMPLE, 7)

    def stop_coeffs(stop):
        """(A, B) for a stop: the ray that a stop blocks satisfies |A p + B h| > r,
        where p is pupil height and h is field height. This is the whole taxonomy.

        B = 0  -> blocking is field-blind: a pure APERTURE stop, at a pupil.
        A = 0  -> blocking ignores the pupil: a pure FIELD stop, at a window.
        both   -> the blocked region drifts across the pupil with field, which is
                  exactly what vignetting is."""
        _z, _r = stop
        return float(ray_y(_z, 0.0, 1.0 / d)), float(ray_y(_z, 1.0, -1.0 / d))

    # the three stops sit at the three corners of that taxonomy
    assert np.isclose(stop_coeffs(STOP_A)[1], 0.0, atol=1e-9)  # pure aperture stop
    assert np.isclose(stop_coeffs(STOP_F)[0], 0.0, atol=1e-9)  # pure field stop
    assert all(abs(_c) > 0.1 for _c in stop_coeffs(STOP_V))    # neither
    return (
        FAN_FIELDS,
        FAN_PUPIL,
        PUPIL_FIELDS,
        STOPS,
        STOP_A,
        STOP_F,
        STOP_V,
        Z_SEC,
        field_h,
        illum,
        pupil_maps,
        pupil_xy,
        ray_y,
        stop_coeffs,
    )


@app.cell
def _(
    FAN_FIELDS,
    FAN_PUPIL,
    STOPS,
    STOP_A,
    STOP_F,
    Z_SEC,
    d,
    field_h,
    illum,
    np,
    plt,
    ray_y,
    stop_coeffs,
    z_img,
):
    _fig = plt.figure(figsize=(12, 15))
    _gs = _fig.add_gridspec(4, 1, height_ratios=[1.15, 1.15, 1.15, 1.3], hspace=0.30)
    _zs = np.linspace(0, Z_SEC, 400)
    _fc = plt.cm.cool(np.linspace(0, 1, len(FAN_FIELDS)))
    _YLIM = 2.7
    _share = None
    _ray_axes = []

    for _row, (_name, _stops) in enumerate(STOPS.items()):
        _ax = _fig.add_subplot(_gs[_row], sharex=_share, sharey=_share)
        _share = _share or _ax
        _ray_axes.append(_ax)
        _ax.set_facecolor("black")

        for _fi, _h in enumerate(FAN_FIELDS):
            for _p in FAN_PUPIL:
                _t = (_p - _h) / d
                _cut = Z_SEC
                for _z, _r in _stops:
                    if abs(float(ray_y(_z, _h, _t))) > _r:
                        _cut = min(_cut, _z)
                _m = _zs <= _cut
                _ax.plot(_zs[_m], ray_y(_zs[_m], _h, _t), color=_fc[_fi], lw=0.6, alpha=0.85)
                if _cut < Z_SEC:  # where the ray dies, and on which stop
                    _ax.plot(_cut, ray_y(_cut, _h, _t), ".", color="#ff4d4d", ms=4)

        # the two rays that define the pair
        _ax.plot(_zs, ray_y(_zs, 0.0, STOP_A[1] / d), "w:", lw=1.3,
                 label="marginal ray: axis → stop rim")
        _ax.plot(_zs, ray_y(_zs, FAN_FIELDS[-1], -FAN_FIELDS[-1] / d), "w--", lw=1.3,
                 label="chief ray: field edge → stop centre")

        for _z, _r in _stops:
            _ax.plot([_z, _z], [_r, _YLIM], color="c", lw=4, solid_capstyle="butt")
            _ax.plot([_z, _z], [-_r, -_YLIM], color="c", lw=4, solid_capstyle="butt")
            _A, _B = stop_coeffs((_z, _r))
            _ax.annotate(f"z={_z:g}   A={_A:+.2f}  B={_B:+.2f}", (_z, -_YLIM),
                         textcoords="offset points", xytext=(0, 4), ha="center",
                         va="bottom", fontsize=7.5, color="c",
                         bbox=dict(fc="black", ec="none", alpha=0.65, pad=1.5))
        _ax.axvline(d + z_img, color="w", lw=0.8, ls=":", alpha=0.45)
        _ax.set(ylabel="y (mm)", ylim=(-_YLIM, _YLIM), xlim=(0, Z_SEC), title=_name)
        _ax.title.set_fontsize(10)
        _ax.tick_params(labelbottom=False)
        if _row == 0:
            _ax.legend(loc="upper left", fontsize=8, framealpha=0.65)

    _ray_axes[-1].set_xlabel("z (mm)     — object at 0, lens at 100, image at 200")
    _ray_axes[-1].tick_params(labelbottom=True)

    _axi = _fig.add_subplot(_gs[3])
    for (_name, _v), _c in zip(illum.items(), ("C0", "C3", "C2")):
        _axi.plot(field_h, _v, _c, lw=1.9, label=_name)
    _axi.axvline(STOP_F[1], color="C3", lw=0.8, ls=":", alpha=0.7)
    _axi.axvline(-STOP_F[1], color="C3", lw=0.8, ls=":", alpha=0.7)
    _axi.annotate(f"field stop edge, ±{STOP_F[1]:g} mm", (STOP_F[1], 0.55),
                  xytext=(6, 0), textcoords="offset points", fontsize=8, color="C3")
    _axi.set(
        xlabel="object field height (mm)",
        ylabel="relative illumination",
        xlim=(field_h[0], field_h[-1]),
        ylim=(-0.04, 1.1),
        title="Same aperture stop in all three: only the second stop's *position* differs",
    )
    _axi.title.set_fontsize(10)
    _axi.grid(alpha=0.25)
    _axi.legend(fontsize=8, loc="lower center")

    _fig.suptitle(
        "Rays from five field points, coloured by field height; a red dot is where a "
        "stop kills the ray.\nA and B are the pupil and field coefficients: B = 0 is "
        "a pure aperture stop, A = 0 a pure field stop.",
        fontsize=10,
    )
    _fig.tight_layout(rect=[0, 0, 1, 0.965])
    _fig
    return


@app.cell
def _(PUPIL_FIELDS, STOP_A, STOP_V, plt, pupil_maps, pupil_xy, stop_coeffs):
    # The pupil as each field point sees it. A stop away from the pupil plane
    # projects into pupil coordinates as a circle that *slides* with field height,
    # and the surviving aperture is the intersection -- the cat's eye.
    _fig, _axes = plt.subplots(1, len(PUPIL_FIELDS), figsize=(12, 3.6))
    _cA, _rA = 0.0, STOP_A[1]
    _A_v, _B_v = stop_coeffs(STOP_V)

    for _ax, _h in zip(_axes, PUPIL_FIELDS):
        _ok = pupil_maps[_h]
        _ax.set_facecolor("black")
        _ax.plot(pupil_xy[0][~_ok], pupil_xy[1][~_ok], ".", ms=0.5, color="#5a2323")
        _ax.plot(pupil_xy[0][_ok], pupil_xy[1][_ok], ".", ms=0.5, color="#ffc844")
        _ax.add_patch(plt.Circle((0, 0), _rA, fill=False, ec="c", lw=1.3))
        # the halfway stop, projected: centre -B h / A, radius r / |A|
        _ax.add_patch(plt.Circle((0, -_B_v * _h / _A_v), STOP_V[1] / abs(_A_v),
                                 fill=False, ec="#ff7777", lw=1.1, ls="--"))
        _ax.set(
            xlim=(-1.0, 1.0), ylim=(-1.0, 1.0),
            title=f"field h = {_h:g} mm   passes {_ok.mean() / pupil_maps[0.0].mean():.0%}",
            xlabel="pupil x (mm)",
            ylabel="pupil y (mm)" if _h == PUPIL_FIELDS[0] else "",
        )
        _ax.set_aspect("equal")
        _ax.title.set_fontsize(9)

    _fig.suptitle(
        "The exit pupil seen from four field heights, with the halfway stop in place. "
        "Cyan is the aperture stop;\ndashed red is the halfway stop projected into "
        "pupil coordinates — it slides with field, and the overlap is what gets through.",
        fontsize=9,
    )
    _fig.tight_layout(rect=[0, 0, 1, 0.93])
    _fig
    return


@app.cell
def _(STOP_A, STOP_F, STOP_V, mo, stop_coeffs):
    _verdict = {"A": "pure **aperture stop** — sets the cone, blind to field",
                "F": "pure **field stop** — sets the field, blind to the pupil",
                "V": "**neither** — vignettes"}
    _rows = "\n    ".join(
        f"| {_label} | {_z:g} mm | {_r:g} mm | {stop_coeffs((_z, _r))[0]:+.2f} "
        f"| {stop_coeffs((_z, _r))[1]:+.2f} | {_verdict[_key]} |"
        for _key, _label, (_z, _r) in (
            ("A", "iris on the lens", STOP_A),
            ("F", "at the image plane", STOP_F),
            ("V", "halfway to the image", STOP_V),
        )
    )

    mo.md(
        f"""
        ### Reading the three panels

        Every ray a stop blocks satisfies $|A p + B h| > r$, with $p$ the height it
        crosses the pupil at and $h$ the field height it came from. Those two
        coefficients are the entire taxonomy:

        | stop | $z$ | radius | $A$ (pupil) | $B$ (field) | what it is |
        |:--|--:|--:|--:|--:|:--|
        {_rows}

        - **$B = 0$** &mdash; the stop cannot tell field points apart, so it clips the
          same cone from every one of them. Relative illumination is dead flat and
          the field is uncut. That is an aperture stop, and it is what "at a pupil"
          means.
        - **$A = 0$** &mdash; the stop cannot tell rays within a bundle apart, so it
          passes a field point whole or kills it whole. Relative illumination is a
          cliff at $\pm${STOP_F[1]:g} mm. That is a field stop, and it is what "at a
          window" means. In a camera it is the sensor edge.
        - **Both nonzero** &mdash; the blocked region *slides across the pupil* as the
          field angle grows, at {abs(stop_coeffs(STOP_V)[1] / stop_coeffs(STOP_V)[0]):.1f} mm
          of pupil per mm of field. Illumination rolls off instead of cutting, from
          $|h|$ = {STOP_V[1] / abs(stop_coeffs(STOP_V)[0]) - STOP_A[1]:.1f} mm to
          {STOP_V[1] / abs(stop_coeffs(STOP_V)[0]) + STOP_A[1]:.1f} mm, and the working
          aperture becomes the lens-shaped overlap of two circles &mdash; the **cat's
          eye** in the pupil maps above.

        Nothing about the *sizes* decided any of this; only the positions did. Move
        the {STOP_F[1]:g} mm stop from the image plane to the lens and it becomes an
        aperture stop that does nothing, because the {STOP_A[1]:g} mm iris is already
        smaller.

        **Where this meets the rest of the notebook.** The aperture stop is the
        aperture the earlier sections were diffracting off: it sets NA, so it sets
        the focal spot size, the Airy rings and the focal shift. The field stop sets
        how much of the scene survives, and it diffracts too &mdash; but it sits at an
        image plane, so its ringing softens the *edge of the frame* rather than the
        resolution. A ray model gets stops exactly right, which is why this section
        is rays only; what it cannot tell you is how big each surviving point is.
        """
    )
    return


if __name__ == "__main__":
    app.run()
