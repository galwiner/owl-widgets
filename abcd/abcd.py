# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo", "numpy", "matplotlib", "anywidget", "traitlets"]
# ///

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # ABCD matrix optics

    Ray transfer matrices for a sequential optical train. Build a system on the
    bench below and watch a fan of geometric rays go through it. The *same*
    matrices read a Gaussian beam too &mdash; that comes further down, on a second
    bench that can overlay the two.

    Drag an element **sideways** to slide it along $z$, **up or down** to scrub its
    power smoothly from converging through flat and out into diverging. Click it to
    type exact numbers. Hover anywhere to read $w$, $R$ and the accumulated matrix
    at that plane.

    Ray tracing is linear, so the ray span only sets the scale &mdash; double it and
    every height doubles, leaving the picture identical and the printed $\pm$ extent
    twice as large. `rays` is the knob that changes what you see.
    """)
    return


@app.cell
def _():
    import marimo as mo
    import numpy as np
    import matplotlib.pyplot as plt
    import anywidget
    import traitlets

    return anywidget, mo, np, plt, traitlets


@app.cell
def _(mo):
    mo.md(r"""
    $\begin{bmatrix} y' \\ \theta' \end{bmatrix}
    = \begin{bmatrix} A & B \\ C & D \end{bmatrix}
    \begin{bmatrix} y \\ \theta \end{bmatrix}
    \qquad
    \mathrm{free}(d) = \begin{bmatrix} 1 & d \\ 0 & 1 \end{bmatrix}
    \qquad
    \mathrm{lens}(f) = \begin{bmatrix} 1 & 0 \\ -1/f & 1 \end{bmatrix}
    \qquad
    \mathrm{mirror}(R) = \begin{bmatrix} 1 & 0 \\ -2/R & 1 \end{bmatrix}
    \qquad
    \mathrm{iface}(R, n_1, n_2) = \begin{bmatrix} 1 & 0 \\ \frac{n_1-n_2}{n_2 R} & n_1/n_2 \end{bmatrix}$
    """)
    return


@app.cell
def _(np, plt):
    from collections import namedtuple

    # element = 2x2 matrix, length along z, flips direction?, index downstream,
    # index *inside* this element (set only by solid bodies that occupy z)
    El = namedtuple("El", "M dz flip n n_in", defaults=(0.0, False, None, None))

    def free(d):
        return El(np.array([[1.0, d], [0.0, 1.0]]), d)

    def lens(f):
        return El(np.array([[1.0, 0.0], [-1.0 / f, 1.0]]))

    def mirror(R=np.inf):
        # curved mirror of radius R == lens of f = R/2, then z runs backwards
        return El(lens(R / 2).M if np.isfinite(R) else np.eye(2), 0.0, True)

    def iface(R=np.inf, n1=1.0, n2=1.0):
        # refraction at a curved surface, R > 0 = center of curvature downstream
        return El(np.array([[1.0, 0.0], [(n1 - n2) / (R * n2), n1 / n2]]), n=n2)

    def thick(R1=np.inf, R2=np.inf, t=10.0, n=1.5):
        # real lens in air: entry face, t of glass, exit face -- occupies z
        M = iface(R2, n, 1.0).M @ free(t).M @ iface(R1, 1.0, n).M
        return El(M, t, n_in=n)

    # constructors the node builder can add
    ELEMENTS = {"free": free, "lens": lens, "mirror": mirror, "iface": iface, "thick": thick}

    def trace(elements, rays):
        """rays: 2xN [y; theta]. Returns z (n+1,) and rays at each node (n+1, 2, N)."""
        z, out, r, s = [0.0], [rays], rays, 1
        for e in elements:
            e = El(*e)
            r = e.M @ r
            s = -s if e.flip else s
            z.append(z[-1] + s * e.dz)
            out.append(r)
        return np.array(z), np.stack(out)

    def mark(ax, z, elements):
        """Element faces and index shading; shared by the ray and beam plots."""
        n = 1.0
        for i, e in enumerate(elements):
            e = El(*e)
            if e.dz == 0:
                ax.axvline(z[i], color="k", lw=2 if e.flip else 1, alpha=0.4)
            else:
                span = sorted((z[i], z[i + 1]))
                here = n if e.n_in is None else e.n_in
                if e.n_in is not None:  # solid body: mark both faces
                    for face in span:
                        ax.axvline(face, color="k", lw=1, alpha=0.4)
                if here != 1.0:  # shade and label any medium that is not air
                    ax.axvspan(*span, color="C0", alpha=0.08, lw=0)
                    ax.text(
                        sum(span) / 2, 0.97, f"n = {here:g}", fontsize=8,
                        transform=ax.get_xaxis_transform(), ha="center", va="top",
                    )
            n = n if e.n is None else e.n

    def draw(elements, rays):
        z, r = trace(elements, rays)
        fig, ax = plt.subplots(figsize=(9, 3.5))
        ax.plot(z, r[:, 0, :], ".-", lw=1, ms=4)
        ax.axhline(0, color="k", lw=0.5)
        mark(ax, z, elements)
        ax.set(xlabel="z", ylabel="y")
        return fig

    # 2f-2f imaging: parallel input heights collapse to -y at the image plane
    _z, _r = trace([free(100), lens(50), free(100)], np.array([[1.0, 2.0], [0.0, 0.0]]))
    assert np.allclose(_r[-1, 0], [-1.0, -2.0])
    # mirror(R) focuses like a lens of f = R/2 and sends z back where it came from
    assert np.allclose(mirror(100).M, lens(50).M)
    _z, _ = trace([free(100), mirror(), free(100)], np.zeros((2, 1)))
    assert np.allclose(_z, [0, 100, 100, 0])
    # lensmaker: two interfaces back to back == thin lens, 1/f = (n-1)(1/R1 - 1/R2)
    _n, _R1, _R2 = 1.5, 60.0, -60.0
    _f = 1 / ((_n - 1) * (1 / _R1 - 1 / _R2))
    assert np.allclose(iface(_R2, _n, 1).M @ iface(_R1, 1, _n).M, lens(_f).M)
    # only an interface changes the index; every other element leaves n alone
    assert (iface(60, 1, 1.5).n, free(10).n, lens(50).n, mirror().n) == (1.5, None, None, None)
    # the rule FLIP encodes: a surface met again on the way back has its curvature
    # signed and its indices swapped. Double-passing it lands back in air and
    # doubles the power -- it does not undo the first pass.
    _fwd, _bck = iface(60, 1, 1.5), iface(-60, 1.5, 1)
    _MM = _bck.M @ _fwd.M
    assert np.isclose(_MM[1, 1], 1.0) and np.isclose(_MM[1, 0], 2 * _bck.M[1, 0])
    # a solid body carries its own internal index; a gap just inherits the ambient one
    assert (thick(60, -60, 10, 1.5).n_in, free(10).n_in) == (1.5, None)
    # thick lens: C = -1/f with the t-dependent lensmaker equation
    _t = 10.0
    _ft = 1 / ((_n - 1) * (1 / _R1 - 1 / _R2 + (_n - 1) * _t / (_n * _R1 * _R2)))
    assert np.allclose(thick(_R1, _R2, _t, _n).M[1, 0], -1 / _ft)
    assert np.allclose(thick(_R1, _R2, 0.0, _n).M, lens(_f).M)  # t -> 0 is the thin lens
    return ELEMENTS, El, free, iface, lens, mark, trace


@app.cell
def _(np):
    # Parameter names and defaults per element kind, plus the mirror-return rule.
    # The bench widget reads this same dict over the wire, so the schema and the
    # flip rule are each written once and JS cannot drift from Python.
    #
    # flip: (index, sign) pairs. The element list is the order the beam meets
    # things, so a return pass after a mirror has to be spelled out -- and each
    # surface is then seen from the other side: curvatures change sign and the
    # indices swap.
    KINDS = {
        "free": {"params": {"d": "100"}, "flip": [(0, 1)]},
        "lens": {"params": {"f": "50"}, "flip": [(0, 1)]},
        "mirror": {"params": {"R": "inf"}, "flip": [(0, 1)]},
        "iface": {
            "params": {"R": "100", "n1": "1", "n2": "1.5"},
            "flip": [(0, -1), (2, 1), (1, 1)],
        },
        "thick": {
            "params": {"R1": "100", "R2": "-100", "t": "10", "n": "1.5"},
            "flip": [(1, -1), (0, -1), (2, 1), (3, 1)],
        },
    }

    # Params stay *strings* on the wire. That keeps the half-typed-input
    # tolerance below, and it dodges JSON: "inf" is a perfectly good mirror
    # radius but Infinity is not valid JSON and would not survive the trip.
    def num(s, fallback):
        """Text -> np.float64, tolerating half-typed input. np.float64 keeps a
        stray 0 (e.g. lens(0)) from raising ZeroDivisionError mid-edit."""
        try:
            return np.float64(s)
        except ValueError:
            return np.float64(fallback)

    def neg(s):
        # %g, not str(): it matches the widget's fmt() so both sides spell a
        # flipped parameter the same way ("-60", not "-60.0"). Same number
        # either way, but identical strings make the two folds comparable.
        return f"{-num(s, '0'):g}"

    FLIP = {
        kind: (lambda p, rule=spec["flip"]: [neg(p[i]) if s < 0 else p[i] for i, s in rule])
        for kind, spec in KINDS.items()
    }

    # the signed permutations really do say what the prose above says
    assert FLIP["iface"](["60", "1", "1.5"]) == ["-60", "1.5", "1"]
    assert FLIP["thick"](["60", "-60", "10", "1.5"]) == ["60", "-60", "10", "1.5"]
    assert FLIP["lens"](["50"]) == ["50"]
    return KINDS, num


@app.cell
def _(anywidget, traitlets):
    class Bench(anywidget.AnyWidget):
        """Draggable ABCD bench. The matrices are re-derived in JS so a drag
        redraws at frame rate without touching the kernel; the cell further down
        asserts that mirror against trace() and the q propagation."""

        _esm = r"""
        const PI = Math.PI;
        const KIND_COLOR = {free:"#8aa0b8", lens:"#3b82f6", mirror:"#f59e0b",
                            iface:"#10b981", thick:"#8b5cf6"};

        // Must agree with np.float64 on every string the UI can produce, so this
        // is a whitelist rather than parseFloat: parseFloat("1e") is 1 and
        // Number("") is 0, while np.float64 raises on both and falls back.
        const NUMRE = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;
        function num(s, fb) {
          if (typeof s === "number") return s;
          const t = String(s).trim().toLowerCase();
          if (t === "inf" || t === "+inf" || t === "infinity") return Infinity;
          if (t === "-inf" || t === "-infinity") return -Infinity;
          if (t === "nan") return NaN;
          return NUMRE.test(t) ? Number(t) : Number(fb);
        }
        function fmt(v) {
          if (Number.isNaN(v)) return "nan";
          if (!Number.isFinite(v)) return v > 0 ? "inf" : "-inf";
          return String(+v.toPrecision(6));
        }
        function mul(A, B) {
          return [[A[0][0]*B[0][0]+A[0][1]*B[1][0], A[0][0]*B[0][1]+A[0][1]*B[1][1]],
                  [A[1][0]*B[0][0]+A[1][1]*B[1][0], A[1][0]*B[0][1]+A[1][1]*B[1][1]]];
        }
        const finiteM = (M) => M.flat().every(Number.isFinite);

        // one per constructor in the physics cell; same M, dz, flip, n, n_in
        function element(kind, p) {
          if (kind === "free")
            return {M:[[1,p[0]],[0,1]], dz:p[0], flip:false, n:null, n_in:null};
          if (kind === "lens")
            return {M:[[1,0],[-1/p[0],1]], dz:0, flip:false, n:null, n_in:null};
          if (kind === "mirror") {
            const R = p[0];
            const M = Number.isFinite(R) ? [[1,0],[-1/(R/2),1]] : [[1,0],[0,1]];
            return {M, dz:0, flip:true, n:null, n_in:null};
          }
          if (kind === "iface") {
            const [R,n1,n2] = p;
            return {M:[[1,0],[(n1-n2)/(R*n2), n1/n2]], dz:0, flip:false, n:n2, n_in:null};
          }
          if (kind === "thick") {
            const [R1,R2,t,n] = p;
            const M = mul(element("iface",[R2,n,1]).M,
                          mul([[1,t],[0,1]], element("iface",[R1,1,n]).M));
            return {M, dz:t, flip:false, n:null, n_in:n};
          }
        }

        function traceRays(els, ys) {
          let s = 1, r = ys.map(y => [y, 0]), M = [[1,0],[0,1]];
          const z = [0], out = [r], Ms = [M];
          for (const e of els) {
            r = r.map(([y,t]) => [e.M[0][0]*y + e.M[0][1]*t, e.M[1][0]*y + e.M[1][1]*t]);
            M = mul(e.M, M);
            if (e.flip) s = -s;
            z.push(z[z.length-1] + s*e.dz);
            out.push(r); Ms.push(M);
          }
          // Ms is what the cross-check really leans on: every input ray has
          // theta = 0, so the drawn heights only ever exercise the A entry.
          return {z, r: out, M: Ms};
        }

        const qabcd = (M, q) => {
          const nr = M[0][0]*q.re + M[0][1], ni = M[0][0]*q.im;
          const dr = M[1][0]*q.re + M[1][1], di = M[1][0]*q.im;
          const den = dr*dr + di*di;
          return {re:(nr*dr + ni*di)/den, im:(ni*dr - nr*di)/den};
        };
        const wOf = (q, lam, n) => {
          const den = q.re*q.re + q.im*q.im;
          return Math.sqrt(-(lam/n) / (PI * (-q.im/den)));
        };
        const rOf = (q) => {
          const den = q.re*q.re + q.im*q.im;
          const curv = q.re/den;
          return curv === 0 ? Infinity : 1/curv;
        };

        // mirrors beam_profile(): gaps are sampled, a solid body is a chord.
        // steps=60 and the sampling rule match np.linspace(0, dz, 60)[1:] exactly,
        // so the envelope arrays can be compared element-wise with no interpolation.
        function beamProfile(els, q0, lam, steps=60) {
          let n = 1, z = 0, s = 1, q = q0;
          const zs = [0], ws = [wOf(q0, lam, n)], qs = [q0], aa = [1];
          const nodeZ = [0], nodeW = [ws[0]], nodeM = [[[1,0],[0,1]]];
          let acc = [[1,0],[0,1]];
          for (const e of els) {
            if (e.dz && e.n_in === null) {
              for (let i = 1; i < steps; i++) {
                const step = i === steps - 1 ? e.dz : e.dz * i / (steps - 1);
                zs.push(z + s*step);
                qs.push({re:q.re + step, im:q.im});
                ws.push(wOf({re:q.re + step, im:q.im}, lam, n));
                // every ray launches with theta = 0, so y(z) = A(z) y(0) and the
                // fan is narrowest exactly where |A| is. One free step into the
                // gap: A -> A + step*C.
                aa.push(acc[0][0] + step*acc[1][0]);
              }
            }
            q = qabcd(e.M, q);
            acc = mul(e.M, acc);
            if (e.flip) s = -s;
            z += s*e.dz;
            if (e.n !== null) n = e.n;
            zs.push(z); qs.push(q); ws.push(wOf(q, lam, n)); aa.push(acc[0][0]);
            nodeZ.push(z); nodeW.push(wOf(q, lam, n)); nodeM.push(acc);
          }
          return {zs, ws, qs, aa, nodeZ, nodeW, nodeM};
        }

        function render({ model, el }) {
          el.innerHTML = `
            <div class="abcd">
              <div class="abcd-bar"></div>
              <div class="abcd-warn"></div>
              <svg class="abcd-svg" viewBox="0 0 900 340"></svg>
              <div class="abcd-edit"></div>
              <div class="abcd-foot">
                <label>w<sub>0</sub><input class="abcd-w0" type="text"><span class="unit">mm</span></label>
                <label>&lambda;<input class="abcd-lam" type="text"><span class="unit">mm</span></label>
                <label>ray span<input class="abcd-span" type="text"><span class="unit">mm</span></label>
                <label>rays<input class="abcd-nrays" type="text"></label>
                <span class="abcd-read"></span>
              </div>
            </div>`;
          const svg = el.querySelector(".abcd-svg");
          const bar = el.querySelector(".abcd-bar");
          const warn = el.querySelector(".abcd-warn");
          const edit = el.querySelector(".abcd-edit");
          const read = el.querySelector(".abcd-read");
          const NS = "http://www.w3.org/2000/svg";

          const W = 900, PAD = 52;
          const CHIP_Y = 8, CHIP_H = 30;
          // One panel, always. "both" overlays the two readings on it rather
          // than stacking them: sharing the *horizontal* axis is the whole point,
          // because it puts the ray focus and the beam waist directly above one
          // another. They keep separate vertical scales -- w is ~0.07 mm against
          // rays at ~10 mm, and a shared scale would flatten the envelope onto
          // the axis -- so each scale is labelled in its own colour.
          const BAND = [52, 300], H = 340;
          const SHOW = {rays: {ray: true, beam: false},
                        beam: {ray: false, beam: true},
                        both: {ray: true, beam: true}};
          const modeNow = () => SHOW[model.get("mode")] ? model.get("mode") : "both";

          // live during a drag; committed to the model on release
          let spec = null, drag = null, lastFrame = null;
          // clip ids must not collide: two benches share one page
          const uid = "abcdclip" + Math.random().toString(36).slice(2, 8);

          const kinds = () => model.get("kinds");
          const defaults = (kind) => Object.values(kinds()[kind].params);
          const labels = (kind) => Object.keys(kinds()[kind].params);
          const current = () => spec ?? model.get("system").map(
            e => ({kind: e.kind, params: [...e.params]}));

          function build(sp) {
            return sp.map(e => {
              const defs = defaults(e.kind);
              const p = e.params.map((s, i) => num(s, num(defs[i], 0)));
              return Object.assign(element(e.kind, p), {kind: e.kind, params: e.params});
            });
          }

          const mk = (tag, attrs, cls) => {
            const n = document.createElementNS(NS, tag);
            for (const k in attrs) n.setAttribute(k, attrs[k]);
            if (cls) n.setAttribute("class", cls);
            return n;
          };

          function draw(opts = {}) {
            const sp = current();
            const mode = modeNow();
            const show = SHOW[mode];
            const [BY0, BY1] = BAND, A0 = BY0;
            const els = build(sp);
            const bad = els.map(e => !finiteM(e.M));
            const lam = num(model.get("lam"), 633e-6), w0 = num(model.get("w0"), 0.5);
            const span = num(model.get("ray_span"), 10);
            const nr = Math.max(1, Math.min(201,
              Math.round(num(model.get("n_rays"), 21)) || 21));
            const ys = Array.from({length: nr},
              (_, i) => nr === 1 ? 0 : -span + 2*span*i/(nr-1));

            const tr = traceRays(els, ys);
            const ok = !bad.some(Boolean) && w0 > 0 && lam > 0;
            const bp = ok ? beamProfile(els, {re:0, im:PI*w0*w0/lam}, lam) : null;

            // Both axes autoscale, so a redraw re-fits the picture to itself and
            // a drag can look like nothing happened -- lengthening a gap merely
            // zoomed out. While a gesture is live the frame is frozen to whatever
            // it was at pointerdown and the curves are clipped to the band, so the
            // beam visibly moves against a fixed frame. It re-fits on release.
            const F = drag && drag.frame;
            const zAll = tr.z.filter(Number.isFinite);
            let z0 = Math.min(0, ...zAll), z1 = Math.max(1, ...zAll);
            if (!(z1 > z0)) { z0 = 0; z1 = 1; }
            if (F) { z0 = F.z0; z1 = F.z1; }
            const zpx = (z) => PAD + (W - 2*PAD) * (z - z0) / (z1 - z0);

            let yMax = Math.max(1e-9, ...tr.r.flat(1).map(v => Math.abs(v[0]))
                                        .filter(Number.isFinite)) * 1.1;
            let wMax = bp ? Math.max(1e-9, ...bp.ws.filter(Number.isFinite)) * 1.15 : 1;
            if (F) { yMax = F.yMax; wMax = F.wMax; }
            else lastFrame = {z0, z1, yMax, wMax};
            const mid = (BY0 + BY1)/2, half = (BY1 - BY0)/2;
            const ypx = (y) => mid - half * y / yMax;
            const wpx = (w) => mid - half * w / wMax;

            svg.textContent = "";
            const defs = mk("defs", {});
            const clip = mk("clipPath", {id: uid});
            clip.appendChild(mk("rect", {x: PAD - 6, y: BY0 - 2,
              width: W - 2*PAD + 12, height: BY1 - BY0 + 4}));
            defs.appendChild(clip);
            svg.appendChild(defs);
            const g = (cls) => { const n = mk("g", {}, cls); svg.appendChild(n); return n; };
            const gShade = g("abcd-shade"), gCurve = g("abcd-curve"),
                  gAxis = g("abcd-axis"), gChip = g("abcd-chips");
            gCurve.setAttribute("clip-path", `url(#${uid})`);

            // element faces and refractive-index shading, both panels (== mark())
            let n_med = 1;
            for (let i = 0; i < els.length; i++) {
              const e = els[i];
              const za = tr.z[i], zb = tr.z[i+1];
              if (e.dz === 0) {
                for (const [p0, p1] of [BAND])
                  gShade.appendChild(mk("line",
                    {x1: zpx(za), x2: zpx(za), y1: p0, y2: p1,
                     "stroke-width": e.flip ? 3 : 1.2}, "abcd-face"));
              } else {
                const lo = Math.min(za, zb), hi = Math.max(za, zb);
                const here = e.n_in === null ? n_med : e.n_in;
                if (e.n_in !== null)
                  for (const f of [lo, hi])
                    for (const [p0, p1] of [BAND])
                      gShade.appendChild(mk("line",
                        {x1: zpx(f), x2: zpx(f), y1: p0, y2: p1,
                         "stroke-width": 1.2}, "abcd-face"));
                if (here !== 1) {
                  for (const [p0, p1] of [BAND])
                    gShade.appendChild(mk("rect",
                      {x: zpx(lo), y: p0, width: Math.max(0, zpx(hi)-zpx(lo)),
                       height: p1-p0}, "abcd-medium"));
                  const lab = mk("text", {x: (zpx(lo)+zpx(hi))/2, y: A0 - 4,
                                          "text-anchor": "middle"}, "abcd-nlabel");
                  lab.textContent = "n = " + (+here.toPrecision(4));
                  gShade.appendChild(lab);
                }
              }
              if (e.n !== null) n_med = e.n;
            }

            // axes
            // Both panels autoscale, and ray tracing is linear -- doubling the
            // launch span doubles every height, so the *shape* cannot change.
            // Printing the extent is what makes the span control visible.
            gAxis.appendChild(mk("line",
              {x1: PAD, x2: W-PAD, y1: mid, y2: mid}, "abcd-zero"));
            let _ly = BY0 + 11;
            for (const [on, name, ext, cls] of [
              [show.ray, "y (rays)", yMax, "abcd-focus-ray"],
              [show.beam, "w (beam)", wMax, "abcd-focus-w"],
            ]) {
              if (!on) continue;
              const t = mk("text", {x: 6, y: _ly}, cls + " abcd-scalelab");
              t.textContent = `${name} ±${+ext.toPrecision(3)} mm`;
              gAxis.appendChild(t);
              _ly += 13;
            }
            const sc = mk("text", {x: W-PAD, y: H - 10, "text-anchor": "end"}, "abcd-axlabel");
            sc.textContent = `z: ${+z0.toPrecision(4)} … ${+z1.toPrecision(4)} mm`;
            gAxis.appendChild(sc);

            // ray fan
            for (let k = 0; show.ray && k < ys.length; k++) {
              const pts = tr.z.map((z, i) => `${zpx(z)},${ypx(tr.r[i][k][0])}`);
              if (pts.some(s => s.includes("NaN"))) continue;
              gCurve.appendChild(mk("polyline",
                {points: pts.join(" "), fill: "none"}, "abcd-ray"));
            }

            // Gaussian envelope
            if (bp && show.beam) {
              const up = bp.zs.map((z, i) => `${zpx(z)},${wpx(bp.ws[i])}`);
              const dn = bp.zs.map((z, i) => `${zpx(z)},${wpx(-bp.ws[i])}`).reverse();
              gCurve.appendChild(mk("path",
                {d: `M${up.join("L")}L${dn.join("L")}Z`}, "abcd-fill"));
              for (const side of [1, -1])
                gCurve.appendChild(mk("polyline",
                  {points: bp.zs.map((z,i) => `${zpx(z)},${wpx(side*bp.ws[i])}`).join(" "),
                   fill: "none"}, "abcd-env"));
            }

            // Where each reading focuses. These are different planes: the ray
            // fan pinches where |A| = 0, the beam waists where Re(q) = 0, and
            // the gap between them is the whole reason to show both at once.
            let focusNote = "";
            if (bp) {
              // A *local* interior minimum, not the global one: for a tight input
              // waist the smallest spot in the system is the launch waist itself,
              // and marking that would say nothing about the optics.
              const locmin = (arr, key) => {
                let best = -1;
                for (let i = 1; i < arr.length - 1; i++) {
                  const b = key(arr[i]);
                  if (b <= key(arr[i-1]) && b <= key(arr[i+1])
                      && (best < 0 || b < key(arr[best]))) best = i;
                }
                return best;
              };
              // w^2 is quadratic in z inside a gap, so the parabola vertex is the
              // exact waist rather than whichever sample happened to land nearest
              const vertex = (zs, arr, i) => {
                const a = arr[i-1]**2, b = arr[i]**2, c = arr[i+1]**2;
                const den = a - 2*b + c;
                return den === 0 ? zs[i]
                  : zs[i] + 0.25 * (a - c) / den * (zs[i+1] - zs[i-1]);
              };
              // A is piecewise linear in z, so its zero crossing is exact too
              let zRay = null;
              for (let i = 0; i < bp.aa.length - 1; i++) {
                const u = bp.aa[i], v = bp.aa[i+1];
                if ((u <= 0 && v >= 0) || (u >= 0 && v <= 0)) {
                  zRay = u === v ? bp.zs[i]
                    : bp.zs[i] + (bp.zs[i+1] - bp.zs[i]) * u / (u - v);
                  break;
                }
              }
              const iW = locmin(bp.ws, (v) => v);
              const zW = iW > 0 ? vertex(bp.zs, bp.ws, iW) : null;
              const marks = [];
              if (zRay !== null && show.ray)
                marks.push([zRay, "abcd-focus-ray", "ray focus"]);
              if (zW !== null && show.beam) marks.push([zW, "abcd-focus-w", "waist"]);
              for (const [zf, cls, label] of marks) {
                for (const [p0, p1] of [BAND])
                  gCurve.appendChild(mk("line",
                    {x1: zpx(zf), x2: zpx(zf), y1: p0, y2: p1}, cls));
                const t = mk("text", {x: zpx(zf) + 3, y: BY1 - 6}, cls + " abcd-focuslab");
                t.textContent = label;
                gCurve.appendChild(t);
              }
              if (zRay !== null && zW !== null && show.ray && show.beam)
                focusNote = `ray focus ${+zRay.toPrecision(4)} · `
                  + `waist ${+zW.toPrecision(4)} · `
                  + `Δ ${(zW - zRay >= 0 ? "+" : "")}${+(zW - zRay).toPrecision(3)} mm`;
            }
            if (focusNote) {
              const fn = mk("text", {x: PAD, y: H - 10}, "abcd-axlabel");
              fn.textContent = focusNote;
              gAxis.appendChild(fn);
            }

            // draggable chips, one per element, sitting at its own z
            let lastX = -1e9, row = 0;
            els.forEach((e, i) => {
              const x = zpx(tr.z[i] + (e.dz ? (tr.z[i+1]-tr.z[i])/2 : 0));
              row = (x - lastX < 74) ? 1 - row : 0;
              lastX = x;
              const y = CHIP_Y + row * (CHIP_H + 4);
              const chip = mk("g", {transform: `translate(${x},${y})`,
                                    "data-i": i}, "abcd-chip");
              if (i === model.get("selected")) chip.classList.add("sel");
              if (bad[i]) chip.classList.add("bad");
              chip.appendChild(mk("rect",
                {x: -36, y: 0, width: 72, height: CHIP_H, rx: 7,
                 fill: KIND_COLOR[e.kind]}, "abcd-chipbox"));
              const t1 = mk("text", {x: 0, y: 12, "text-anchor": "middle"}, "abcd-chiptext");
              t1.textContent = e.kind;
              const t2 = mk("text", {x: 0, y: 24, "text-anchor": "middle"}, "abcd-chipsub");
              t2.textContent = e.params.join(", ");
              chip.append(t1, t2);
              gChip.appendChild(chip);
              gChip.appendChild(mk("line",
                {x1: x, x2: x, y1: y + CHIP_H, y2: A0}, "abcd-leader"));
            });

            warn.textContent = bad.some(Boolean)
              ? "Singular matrix in " + bad.map((b,i) => b ? `#${i} ${els[i].kind}` : null)
                  .filter(Boolean).join(", ")
                + ". Everything downstream goes to inf. A flat surface is R = inf, not R = 0."
              : "";
            warn.style.display = bad.some(Boolean) ? "block" : "none";

            svg._hit = {zpx, z0, z1, bp, els};
            if (!opts.skipEdit) drawEdit(sp);
            return {sp, els, tr, bp, ok};
          }

          function drawEdit(sp) {
            const i = model.get("selected");
            edit.textContent = "";
            if (i < 0 || i >= sp.length) return;
            const box = document.createElement("div");
            box.className = "abcd-editbox";
            const head = document.createElement("span");
            head.className = "abcd-editkind";
            head.textContent = `#${i} ${sp[i].kind}`;
            box.appendChild(head);
            labels(sp[i].kind).forEach((name, k) => {
              const l = document.createElement("label");
              l.innerHTML = `${name}`;
              const inp = document.createElement("input");
              inp.type = "text";
              inp.value = sp[i].params[k];
              // live redraw while typing, but the kernel only hears about it on
              // blur/Enter -- syncing per keystroke would re-run the notebook
              // once per character, and would ship half-typed strings across
              inp.addEventListener("input", () => {
                spec = current();
                spec[i].params[k] = inp.value;
                draw({skipEdit: true});
              });
              inp.addEventListener("change", () => {
                const s = current();
                s[i].params[k] = inp.value;
                commit(s);
              });
              l.appendChild(inp);
              box.appendChild(l);
            });
            for (const [txt, fn] of [
              ["◀", () => move(i, -1)], ["▶", () => move(i, 1)],
              ["✕", () => { const s = current(); s.splice(i, 1);
                            model.set("selected", -1); commit(s); }],
            ]) {
              const b = document.createElement("button");
              b.className = "abcd-btn";
              b.textContent = txt;
              b.addEventListener("click", fn);
              box.appendChild(b);
            }
            edit.appendChild(box);
          }

          function move(i, d) {
            const s = current();
            const j = i + d;
            if (j < 0 || j >= s.length) return;
            [s[i], s[j]] = [s[j], s[i]];
            model.set("selected", j);
            commit(s);
          }

          let selfSet = false;

          function commit(s) {
            spec = null;
            selfSet = true;
            model.set("system", s);
            const r = draw();
            model.set("check", checkPayload(r));
            model.save_changes();
            selfSet = false;
          }

          function checkPayload(r) {
            if (!r.ok || !r.bp) return {ok: false};
            // spec travels inside the same object as the arrays, so the pair
            // Python compares is atomic even if the traits arrive separately
            return {
              ok: true,
              spec: r.sp,
              z: r.tr.z,
              y: r.tr.r.map(step => step.map(v => v[0])),
              M: r.tr.M,
              zs: r.bp.zs,
              ws: r.bp.ws,
            };
          }

          // --- drag: horizontal moves along z, vertical scrubs strength.
          // Nothing syncs until pointerup, or every frame would re-run the kernel.
          const SCRUB = {lens: 0, mirror: 0, iface: 0, thick: 0};

          function dragZ(base, i, dz) {
            const s = base.map(e => ({kind: e.kind, params: [...e.params]}));
            const grow = (j, v) => {
              s[j].params[0] = fmt(Math.max(0, num(s[j].params[0], 0) + v));
            };
            if (s[i].kind === "free") { grow(i, dz); return s; }
            const prev = i > 0 && s[i-1].kind === "free" ? i-1 : null;
            const next = i+1 < s.length && s[i+1].kind === "free" ? i+1 : null;
            if (prev !== null) grow(prev, dz);
            if (next !== null) grow(next, -dz);
            return s;
          }

          function dragScrub(base, i, dy) {
            const s = base.map(e => ({kind: e.kind, params: [...e.params]}));
            const k = SCRUB[s[i].kind];
            if (k === undefined) return s;          // a free gap has no power
            const v = num(s[i].params[k], 1);
            // scrub the power 1/f rather than f: it runs smoothly from converging
            // through flat (f = inf) into diverging, and it can never land on the
            // singular f = 0 that the red flag exists to warn about
            const P = 1/v - dy / 10000;
            s[i].params[k] = fmt(P === 0 ? Infinity : 1/P);
            return s;
          }

          svg.addEventListener("pointerdown", (ev) => {
            const chip = ev.target.closest(".abcd-chip");
            if (!chip) return;
            const i = +chip.dataset.i;
            const hit = svg._hit;
            const perPx = (hit.z1 - hit.z0) / (W - 2*PAD);
            const pt = svgXY(ev);
            drag = {i, x0: pt.x, y0: pt.y, base: current(), perPx, moved: false,
                    frame: lastFrame};
            model.set("selected", i);
            draw();
            ev.preventDefault();
          });

          function svgXY(ev) {
            const r = svg.getBoundingClientRect();
            return {x: (ev.clientX - r.left) * W / r.width,
                    y: (ev.clientY - r.top) * H / r.height};
          }

          document.addEventListener("pointermove", (ev) => {
            if (!drag) { hover(ev); return; }
            const pt = svgXY(ev);
            const dx = pt.x - drag.x0, dy = pt.y - drag.y0;
            if (Math.abs(dx) < 2 && Math.abs(dy) < 2) return;
            drag.moved = true;
            spec = Math.abs(dx) >= Math.abs(dy)
              ? dragZ(drag.base, drag.i, dx * drag.perPx)
              : dragScrub(drag.base, drag.i, dy);
            draw();
          });

          document.addEventListener("pointerup", () => {
            if (!drag) return;
            const s = drag.moved ? current() : null;
            drag = null;
            if (s) commit(s); else { spec = null; commit(current()); }
          });

          function hover(ev) {
            const hit = svg._hit;
            if (!hit || !hit.bp) return;
            const r = svg.getBoundingClientRect();
            if (ev.clientX < r.left || ev.clientX > r.right ||
                ev.clientY < r.top || ev.clientY > r.bottom) return;
            const z = hit.z0 + (svgXY(ev).x - PAD) * (hit.z1 - hit.z0) / (W - 2*PAD);
            let best = 0;
            hit.bp.zs.forEach((zz, i) => {
              if (Math.abs(zz - z) < Math.abs(hit.bp.zs[best] - z)) best = i;
            });
            const q = hit.bp.qs[best];
            const R = rOf(q);
            let nb = 0;
            hit.bp.nodeZ.forEach((zz, i) => {
              if (Math.abs(zz - z) < Math.abs(hit.bp.nodeZ[nb] - z)) nb = i;
            });
            const M = hit.bp.nodeM[nb];
            read.textContent =
              `z = ${+hit.bp.zs[best].toPrecision(5)}   w = ${+hit.bp.ws[best].toPrecision(4)}` +
              `   R = ${Number.isFinite(R) ? +R.toPrecision(4) : "inf"}` +
              `   M(node ${nb}) = [${+M[0][0].toPrecision(4)} ${+M[0][1].toPrecision(4)};` +
              ` ${+M[1][0].toPrecision(4)} ${+M[1][1].toPrecision(4)}]`;
          }

          // --- toolbar
          // A mirror sends the light back through everything it just came
          // through, so adding one appends the return pass too. The element list
          // is the order the beam meets things, so that pass has to be spelled
          // out -- and each surface is then seen from the other side, which is
          // exactly what the flip table in KINDS encodes.
          const foldedOnto = (s) => [
            ...s,
            {kind: "mirror", params: ["inf"]},
            ...[...s].reverse().map(e => ({
              kind: e.kind,
              params: kinds()[e.kind].flip.map(([i, sg]) =>
                sg < 0 ? fmt(-num(e.params[i], 0)) : e.params[i]),
            })),
          ];

          for (const kind of Object.keys(model.get("kinds"))) {
            const b = document.createElement("button");
            b.className = "abcd-btn";
            b.textContent = "+ " + kind;
            if (kind === "mirror")
              b.title = "mirror, and the return pass back through the same optics";
            b.addEventListener("click", () => {
              const s = current();
              if (kind === "mirror") { commit(foldedOnto(s)); return; }
              s.push({kind, params: defaults(kind).slice()});
              commit(s);
            });
            bar.appendChild(b);
          }
          const clr = document.createElement("button");
          clr.className = "abcd-btn danger";
          clr.textContent = "clear";
          clr.addEventListener("click", () => {
            model.set("selected", -1);
            commit([]);
          });
          bar.appendChild(clr);

          if (model.get("toggle")) {
            const grp = document.createElement("span");
            grp.className = "abcd-modes";
            for (const [m, label] of [["rays", "rays"], ["beam", "Gaussian beam"],
                                      ["both", "both"]]) {
              const b = document.createElement("button");
              b.className = "abcd-btn" + (modeNow() === m ? " on" : "");
              b.textContent = label;
              b.addEventListener("click", () => {
                for (const x of grp.querySelectorAll("button")) x.classList.remove("on");
                b.classList.add("on");
                model.set("mode", m);
                model.save_changes();
              });
              grp.appendChild(b);
            }
            bar.appendChild(grp);
          }

          // Text, not number inputs: a number input renders 633e-6 as 0.000633
          // and truncates it in an 8ch box, and it is flaky with exponents. These
          // carry the string the user typed, exactly like the element params, and
          // num() parses it on both sides. Committed on blur/Enter, not per key.
          for (const [cls, trait] of [[".abcd-w0","w0"], [".abcd-lam","lam"],
                                      [".abcd-span","ray_span"], [".abcd-nrays","n_rays"]]) {
            const inp = el.querySelector(cls);
            inp.value = model.get(trait);
            inp.addEventListener("change", () => {
              model.set(trait, inp.value);
              const r = draw();
              model.set("check", checkPayload(r));
              model.save_changes();
            });
          }

          // A system set from outside (a test, a restored session) still has to
          // leave `check` describing what is actually drawn, or the cross-check
          // would compare a stale pair and pass vacuously. selfSet stops this
          // from firing a second time on our own commits.
          model.on("change:system", () => {
            if (selfSet) return;
            spec = null;
            const r = draw();
            model.set("check", checkPayload(r));
            model.save_changes();
          });
          model.on("change:selected", () => draw());
          model.on("change:mode", () => draw());
          const first = draw();
          model.set("check", checkPayload(first));
          model.save_changes();
        }
        export default { render };
        """

        _css = r"""
        /* The chrome inherits the page's colour, because marimo has its own
           light/dark toggle and prefers-color-scheme does not track it -- keying
           off the media query put near-white labels on a white page. Borders and
           muting use neutral alphas, which read on either background. Only the
           plot canvas has a fixed palette: it is always dark, on purpose. */
        .abcd {
          --abcd-plot-bg: #14171d; --abcd-plot-fg: #e5e7eb;
          --abcd-plot-mut: #9ca3af; --abcd-plot-line: #3f4753;
          --abcd-ray: #94a3b8; --abcd-env: #f87171; --abcd-bad: #e11d48;
          font: 12px/1.4 system-ui, sans-serif; color: inherit;
        }
        .abcd-svg { width: 100%; height: auto; background: var(--abcd-plot-bg);
                    border: 1px solid rgba(128,128,128,.4); border-radius: 10px;
                    touch-action: none; }
        .abcd-bar, .abcd-foot { display: flex; flex-wrap: wrap; gap: .35rem;
                                align-items: center; margin: .35rem 0; }
        .abcd-btn { font: inherit; color: inherit; padding: .18rem .5rem;
                    cursor: pointer; background: transparent;
                    border: 1px solid rgba(128,128,128,.55); border-radius: 6px; }
        .abcd-btn:hover { border-color: currentColor; }
        .abcd-btn.danger { color: var(--abcd-bad); border-color: var(--abcd-bad); }
        .abcd-modes { display: inline-flex; gap: 0; margin-left: auto; }
        .abcd-modes .abcd-btn { border-radius: 0; }
        .abcd-modes .abcd-btn:first-child { border-radius: 6px 0 0 6px; }
        .abcd-modes .abcd-btn:last-child { border-radius: 0 6px 6px 0; margin-left: -1px; }
        .abcd-btn.on { border-color: currentColor;
                       background: rgba(128,128,128,.22); font-weight: 600; }
        .abcd-foot label, .abcd-editbox label { display: inline-flex;
                    align-items: center; gap: .3rem; }
        .abcd-foot .unit, .abcd-editkind { opacity: .65; }
        .abcd-foot input, .abcd-editbox input {
          font: inherit; color: inherit; width: 8ch; padding: .12rem .3rem;
          background: transparent; border: 1px solid rgba(128,128,128,.55);
          border-radius: 5px; }
        .abcd-read { opacity: .8; font-variant-numeric: tabular-nums;
                     font-family: ui-monospace, monospace; }
        .abcd-warn { display: none; color: var(--abcd-bad); margin: .3rem 0;
                     padding: .3rem .5rem; border: 1px solid var(--abcd-bad);
                     border-radius: 6px; }
        .abcd-editbox { display: flex; flex-wrap: wrap; gap: .35rem;
                        align-items: center; margin: .35rem 0; padding: .35rem .5rem;
                        border: 1px solid rgba(128,128,128,.4); border-radius: 8px; }
        .abcd-face { stroke: var(--abcd-plot-fg); opacity: .45; }
        .abcd-medium { fill: #60a5fa; opacity: .12; }
        .abcd-nlabel, .abcd-axlabel { fill: var(--abcd-plot-mut); font-size: 10px; }
        .abcd-zero { stroke: var(--abcd-plot-line); }
        .abcd-ray { stroke: var(--abcd-ray); stroke-width: 1; opacity: .75; }
        .abcd-env { stroke: var(--abcd-env); stroke-width: 1.6; }
        .abcd-fill { fill: var(--abcd-env); opacity: .12; }
        .abcd-leader { stroke: var(--abcd-plot-line); stroke-dasharray: 2 3; }
        .abcd-focus-ray { stroke: var(--abcd-ray); fill: var(--abcd-ray); }
        .abcd-focus-w { stroke: var(--abcd-env); fill: var(--abcd-env); }
        .abcd-focus-ray, .abcd-focus-w { stroke-width: 1; stroke-dasharray: 4 3; }
        .abcd-focuslab { stroke: none; font-size: 9px; }
        .abcd-scalelab { stroke: none; font-size: 10px; }
        .abcd-chip { cursor: grab; }
        .abcd-chip:active { cursor: grabbing; }
        .abcd-chipbox { stroke: transparent; stroke-width: 2; }
        .abcd-chip.sel .abcd-chipbox { stroke: var(--abcd-plot-fg); }
        .abcd-chip.bad .abcd-chipbox { stroke: var(--abcd-bad); stroke-width: 3; }
        .abcd-chiptext { fill: #fff; font-size: 11px; font-weight: 600; }
        .abcd-chipsub { fill: #fff; font-size: 9px; opacity: .85; }
        """

        # Schema: [{"kind": "lens", "params": ["50"]}, ...]. Params are strings so
        # half-typed input survives the trip and "inf" does not have to be JSON.
        system = traitlets.List().tag(sync=True)
        # Schema: {"lens": {"params": {"f": "50"}, "flip": [[0, 1]]}, ...}
        kinds = traitlets.Dict().tag(sync=True)
        # Strings, like the element params: they keep "633e-6" readable in the
        # box, and num() parses them identically on both sides.
        w0 = traitlets.Unicode("0.5").tag(sync=True)
        lam = traitlets.Unicode("633e-6").tag(sync=True)
        ray_span = traitlets.Unicode("10").tag(sync=True)
        n_rays = traitlets.Unicode("21").tag(sync=True)
        selected = traitlets.Int(-1).tag(sync=True)
        # which reading is on screen: "rays", "beam" or "both". `toggle` is what
        # puts the switch in the toolbar -- the first bench in the notebook has
        # no switch, because the Gaussian section has not happened yet.
        mode = traitlets.Unicode("both").tag(sync=True)
        toggle = traitlets.Bool(False).tag(sync=True)
        # Schema: {"ok": bool, "z": [...], "y": [[...]], "w": [...]} at element
        # nodes. JS -> Python only, and only so the cell below can check it.
        check = traitlets.Dict({"ok": False}).tag(sync=True)

    return (Bench,)


@app.cell
def _(Bench, KINDS, mo):
    # Held in a public global: marimo keeps UI elements by weak reference, and a
    # collected widget silently stops responding.
    bench = mo.ui.anywidget(
        Bench(
            kinds=KINDS,
            mode="rays",  # the Gaussian reading is not introduced until below
            system=[
                {"kind": "free", "params": ["60"]},
                {"kind": "lens", "params": ["50"]},
                {"kind": "free", "params": ["60"]},
            ],
        )
    )
    bench
    return (bench,)


@app.cell
def _(ELEMENTS, KINDS, bench, np, num):
    # The seam back into Python. Nothing here writes to the widget -- JS owns the
    # system, Python only reads it -- so there is no state loop to suppress.
    system = [
        ELEMENTS[e["kind"]](
            *[num(s, d) for s, d in zip(e["params"], KINDS[e["kind"]]["params"].values())]
        )
        for e in bench.value["system"]
    ]

    _n = max(1, min(201, int(num(bench.value["n_rays"], "21"))))
    _span = num(bench.value["ray_span"], "10")
    rays = np.array([np.linspace(-_span, _span, _n), np.zeros(_n)])
    return (rays,)


@app.cell
def _(mo):
    mo.md(r"""
    ## Gaussian beams

    The lower panel on the bench above is this. A real beam is not a ray. It has a
    narrowest point &mdash; the **waist** $w_0$ &mdash;
    and diffraction makes it spread from there. Measuring $z$ from the waist:

    $$w(z) = w_0\sqrt{1 + \left(\frac{z}{z_R}\right)^2}
    \qquad
    z_R = \frac{\pi w_0^2}{\lambda}
    \qquad
    \theta_\infty = \frac{\lambda}{\pi w_0}$$

    $z_R$ is the Rayleigh range, where the spot has grown to $w_0\sqrt{2}$. The
    wavefront is flat at the waist and curves as the beam expands:

    $$R(z) = z\left[1 + \left(\frac{z_R}{z}\right)^2\right]
    \qquad
    I(r, z) = I_0\left(\frac{w_0}{w(z)}\right)^{2} e^{-2r^2/w^2(z)}$$

    Tight waist $\Rightarrow$ short $z_R$ and fast divergence. You cannot have both a
    small spot and a collimated beam.

    ### The $q$ parameter

    To push a beam through the optics above we need $w$ and $R$ carried together.
    **There is no $[y, \theta]$ vector here** &mdash; one complex number holds both:

    $$\frac{1}{q} = \frac{1}{R} - i\,\frac{\lambda}{\pi w^2}
    \qquad\Longrightarrow\qquad
    w = \sqrt{\frac{-\lambda}{\pi\,\mathrm{Im}(1/q)}}, \quad R = \frac{1}{\mathrm{Re}(1/q)}$$

    Which makes the pair above collapse to one line: $q(z) = z + i z_R$.

    The *same* matrices act on $q$, but projectively: multiply $[q, 1]$ by $M$, then
    divide through so the second entry is 1 again.

    $$M \begin{bmatrix} q \\ 1 \end{bmatrix}
    = \begin{bmatrix} Aq + B \\ Cq + D \end{bmatrix}
    \;\xrightarrow{\;\div\,(Cq+D)\;}\;
    \begin{bmatrix} q' \\ 1 \end{bmatrix}
    \qquad\text{so}\qquad
    q' = \frac{Aq + B}{Cq + D}$$

    That renormalisation is why the ABCD law is a ratio and not a matrix product.
    """)
    return


@app.cell
def _(El, free, iface, lens, mark, np, plt, trace):
    def q_waist(w0, lam):
        """q at a beam waist of radius w0. Lengths all in the same units as the layout."""
        return 1j * np.pi * w0**2 / lam

    def w_of(q, lam, n=1.0):
        # lam/n: these matrices track plain theta, so q carries the *local*
        # wavelength. Without the n the spot would jump by sqrt(n) at every surface.
        return np.sqrt(-(lam / n) / (np.pi * np.imag(1 / q)))

    def R_of(q):
        # a flat wavefront really does mean R = inf; np.real of a python complex
        # hands back a python float, so the bare division raises instead
        curv = np.real(1 / q)
        return np.inf if curv == 0 else 1 / curv

    def q_abcd(M, q):
        (A, B), (C, D) = M
        return (A * q + B) / (C * q + D)

    def beam_profile(elements, q0, lam, steps=60):
        """w(z) through the system. Gaps are sampled; a solid body is a straight
        chord between its faces, since one matrix has no inside."""
        n = 1.0
        zs, ws, z, q, s = [0.0], [w_of(q0, lam, n)], 0.0, q0, 1
        for e in elements:
            e = El(*e)
            if e.dz and e.n_in is None:  # a gap propagates as q -> q + dz
                for step in np.linspace(0, e.dz, steps)[1:]:
                    zs.append(z + s * step)
                    ws.append(w_of(q + step, lam, n))
            q = q_abcd(e.M, q)
            s = -s if e.flip else s
            z += s * e.dz
            n = n if e.n is None else e.n  # index downstream of this element
            zs.append(z)
            ws.append(w_of(q, lam, n))
        return np.array(zs), np.array(ws)

    def draw_beam(elements, q0, lam, ax=None):
        zs, ws = beam_profile(elements, q0, lam)
        z, _ = trace(elements, np.zeros((2, 1)))
        if ax is None:
            _, ax = plt.subplots(figsize=(9, 3.5))
        ax.plot(zs, ws, "C3", lw=1.5)
        ax.plot(zs, -ws, "C3", lw=1.5)
        ax.axhline(0, color="k", lw=0.5)
        mark(ax, z, elements)
        ax.set(xlabel="z", ylabel="w")
        return ax.figure

    # one Rayleigh range past the waist the spot has grown by sqrt(2), R = z_R + z_R^2/z_R
    _lam, _w0 = 633e-6, 0.5
    _zR = np.pi * _w0**2 / _lam
    _q = q_abcd(free(_zR).M, q_waist(_w0, _lam))
    assert np.isclose(w_of(_q, _lam), _w0 * np.sqrt(2))
    assert np.isclose(R_of(_q), 2 * _zR)
    # a lens one focal length from the waist puts the new waist at the other focus
    _q = q_abcd(free(80).M @ lens(80).M @ free(80).M, q_waist(_w0, _lam))
    assert np.isclose(R_of(_q), np.inf) or abs(R_of(_q)) > 1e12
    # the field is continuous across a refracting surface: w does not jump, only
    # the divergence does
    _q = q_abcd(free(50).M, q_waist(_w0, _lam))
    assert np.isclose(w_of(_q, _lam, 1.0), w_of(q_abcd(iface(np.inf, 1, 1.5).M, _q), _lam, 1.5))
    # the code reproduces the closed form it is documented with
    _zs, _ws = beam_profile([free(3 * _zR)], q_waist(_w0, _lam), _lam)
    assert np.allclose(_ws, _w0 * np.sqrt(1 + (_zs / _zR) ** 2))
    return R_of, beam_profile, draw_beam, q_abcd, q_waist, w_of


@app.cell
def _(mo):
    mo.md(r"""
    ### The same bench, reading the beam

    Nothing below is a different calculation &mdash; it is the same matrices acting
    on $q$ instead of on $[y, \theta]$. The switch in the toolbar flips which
    reading is drawn; **both** overlays them on one axis so the ray focus and the
    beam waist sit above each other. They are marked, and they are not in the same
    place: rays pinch where $A = 0$, the beam waists where $\mathrm{Re}\,q = 0$.
    Shrink $w_0$ and watch the gap open up.

    The two vertical scales differ by a factor of ~100, so each is labelled in its
    own colour. It is the *horizontal* axis they share, and that is the one that
    matters here.
    """)
    return


@app.cell
def _(Bench, KINDS, mo):
    # A second bench, placed after q has been introduced, so it can offer the
    # rays/Gaussian switch that the one at the top deliberately does not. Its
    # state is its own -- the two benches hold independent systems.
    beam_bench = mo.ui.anywidget(
        Bench(
            kinds=KINDS,
            mode="both",
            toggle=True,
            # zR = 24 mm against f = 50: small enough that the beam waist
            # lands 36 mm past where the ray fan pinches, which is the
            # whole point of being able to see both at once
            w0="0.07",
            system=[
                {"kind": "free", "params": ["60"]},
                {"kind": "lens", "params": ["50"]},
                {"kind": "free", "params": ["150"]},
            ],
        )
    )
    beam_bench
    return (beam_bench,)


@app.cell
def _(ELEMENTS, KINDS, beam_bench, beam_profile, bench, mo, np, num, q_waist,
      trace):
    # Each bench redraws in JS, which means the ABCD law is written twice. This
    # is what keeps the second copy honest: it re-runs on every completed
    # gesture, so the mirror is checked continuously while you play with it.
    def cross_check(b):
        """Re-derive in Python what the widget's JS says it drew. Returns the
        element count, or None when the state is not comparable."""
        chk = b.value["check"]
        # `ok` is false for an empty system, w0 <= 0 or a singular matrix -- all
        # legitimate states to leave a bench in, and JSON has no inf anyway.
        if not chk.get("ok"):
            return None

        # Built from chk["spec"], not from the system trait: then the spec and
        # the arrays it produced are one object and cannot disagree in flight.
        sysp = [
            ELEMENTS[r["kind"]](
                *[num(t, d) for t, d in zip(r["params"], KINDS[r["kind"]]["params"].values())]
            )
            for r in chk["spec"]
        ]
        n = max(1, min(201, int(num(b.value["n_rays"], "21"))))
        span = num(b.value["ray_span"], "10")
        rr = np.array([np.linspace(-span, span, n), np.zeros(n)])

        z, r = trace(sysp, rr)
        lam = num(b.value["lam"], "633e-6")
        zs, ws = beam_profile(sysp, q_waist(num(b.value["w0"], "0.5"), lam), lam)
        M = [np.eye(2)]
        for e in sysp:
            M.append(e.M @ M[-1])

        assert np.allclose(chk["z"], z, atol=1e-9), "JS and Python disagree on z"
        # every input ray has theta = 0, so the drawn heights only exercise A.
        # The cumulative matrices are what pin B, C and D -- a sign slip in
        # iface, a bad thick composition or a wrong flip would hide without this.
        assert np.allclose(chk["M"], M, rtol=1e-9, atol=1e-12), "…on the matrices"
        assert np.allclose(chk["y"], r[:, 0, :], rtol=1e-9, atol=1e-12), "…on ray heights"
        assert np.allclose(chk["zs"], zs, atol=1e-9), "…on the envelope sampling"
        assert np.allclose(chk["ws"], ws, rtol=1e-9, atol=1e-12), "…on the envelope"
        return len(sysp)

    # Both benches, every gesture. A silent check that quietly stopped running
    # looks exactly like a passing one, so it reports rather than staying mute.
    _lines = [
        f"- **{_name}** — "
        + (f"`{_n}` elements, JS matches `trace` and `beam_profile` to 1e-9."
           if _n is not None
           else "*not comparable (empty, singular, or w0 = 0) — flagged in red on the bench.*")
        for _name, _n in (("bench", cross_check(bench)),
                          ("beam_bench", cross_check(beam_bench)))
    ]
    mo.md("\n".join(_lines))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Propagating a gaussian beam with ABCD vs. FFT
    """)
    return


@app.cell
def _(draw_beam, free, mo, np, plt, q_abcd, q_waist, w_of):
    # A bare waist in free space: w0 = 0.25e-3 m at 1 um, propagated 5 Rayleigh
    # ranges, with the ABCD result checked against a Fresnel FFT.
    # Layout units are mm throughout, so w0 = 0.25 mm and lambda = 1e-3 mm.
    _w0, _lam = 0.25, 1e-3
    _zR = np.pi * _w0**2 / _lam  # 196 mm
    _PLANES = (1, 3)  # which z / zR to show the field at

    def propagate(U, dx, wavelength, distance):
        """Fresnel free space: multiply by the paraxial transfer function in the
        spatial-frequency domain. dx, wavelength and distance share units."""
        ny, nx = U.shape
        FX, FY = np.meshgrid(np.fft.fftfreq(nx, d=dx), np.fft.fftfreq(ny, d=dx))
        H = np.exp(-1j * np.pi * wavelength * distance * (FX**2 + FY**2))
        return np.fft.ifft2(np.fft.fft2(U) * H)

    def w_num(U, X):
        """1/e amplitude radius from the intensity second moment: w = 2 sigma."""
        I = np.abs(U) ** 2
        return 2 * np.sqrt((I * X**2).sum() / I.sum())

    # 4 mm window: at 5 zR the beam edge is still ~3% of peak, so a little energy
    # wraps around and the measured w comes out ~0.3% low. Widen it to fix.
    _N, _width = 512, 4.0
    _dx = _width / _N
    _span = (np.arange(_N) - _N // 2) * _dx
    _X, _Y = np.meshgrid(_span, _span)
    _U0 = np.exp(-(_X**2 + _Y**2) / _w0**2).astype(complex)

    _zf = np.linspace(0, 5 * _zR, 21)
    _wf = np.array([w_num(propagate(_U0, _dx, _lam, d), _X) for d in _zf])
    # the whole point of the comparison, as a check
    assert np.allclose(_wf, _w0 * np.sqrt(1 + (_zf / _zR) ** 2), rtol=0.01)

    _fields = {k: propagate(_U0, _dx, _lam, k * _zR) for k in _PLANES}
    # published so the phase-erasure cell can reuse the same beam and grid
    gauss = dict(w0=_w0, lam=_lam, zR=_zR, X=_X, fields=_fields)

    # the y = 0 slice through the volume: propagate to each z, keep the central row.
    # 240 planes is ~1.5 s. Gamma stretch, or the far field is too dim to see.
    _zi = np.linspace(0, 5 * _zR, 240)
    _slice = np.array([np.abs(propagate(_U0, _dx, _lam, d)[_N // 2]) ** 2 for d in _zi]).T

    _fig = plt.figure(figsize=(9, 7.5))
    _gs = _fig.add_gridspec(2, 2, height_ratios=[1, 1.35], hspace=0.3)

    _top = _fig.add_subplot(_gs[0, :])
    _top.imshow(
        _slice / _slice.max(),
        extent=[_zi[0], _zi[-1], _span[0], _span[-1]],
        origin="lower",
        aspect="auto",
        cmap="inferno",
        norm=plt.matplotlib.colors.PowerNorm(0.4),
    )
    draw_beam([free(5 * _zR)], q_waist(_w0, _lam), _lam, ax=_top)
    for _ln in _top.lines[:2]:  # the +/-w envelope: white reads on inferno
        _ln.set(color="w", linewidth=1.3)
    _top.lines[0].set_label("ABCD, $q$ parameter")
    _top.plot(_zf, _wf, "o", color="c", ms=4, label="Fresnel FFT, 2nd moment")
    _top.plot(_zf, -_wf, "o", color="c", ms=4)
    for _k in _PLANES:
        _z, _w = _k * _zR, _w0 * np.sqrt(1 + _k**2)  # w(z) = w0 sqrt(1 + (z/zR)^2)
        _top.plot([_z, _z], [-_w, _w], "w--", lw=1)
        _top.annotate(
            f"{_k} $z_R$\nw = {_w:.3f} mm",
            (_z, -_w),
            textcoords="offset points",
            xytext=(-6, -5),
            ha="right",
            va="top",
            fontsize=8,
            color="w",
        )
    _top.legend(loc="upper left", fontsize=8)
    _top.set(
        xlim=(_zi[0], _zi[-1]),
        ylim=(-1.45, 1.45),
        ylabel="y (mm)",
        title=f"$|U|^2$ in the $y$=0 plane   ($w_0$ = 0.25 mm at 1 um, $z_R$ = {_zR:.0f} mm)",
    )

    # the Fresnel result is the whole complex field, so the same planes can be shown
    # in full. Each panel is scaled to its own peak; the peak drops as (w0/w)^2, so
    # the shared axes are what show the beam growing.
    _crop = 1.5
    for _col, _k in enumerate(_PLANES):
        _I = np.abs(_fields[_k]) ** 2
        _ax = _fig.add_subplot(_gs[1, _col])
        _ax.imshow(
            _I / _I.max(),
            extent=[_span[0], _span[-1], _span[0], _span[-1]],
            origin="lower",
            cmap="inferno",
        )
        _w = _w0 * np.sqrt(1 + _k**2)
        _ax.add_patch(plt.Circle((0, 0), _w, fill=False, ec="w", ls="--", lw=1))
        _ax.set(
            xlim=(-_crop, _crop),
            ylim=(-_crop, _crop),
            xlabel="x (mm)",
            ylabel="y (mm)" if _col == 0 else "",
            title=f"$|U|^2$ at {_k} $z_R$",
        )
        _ax.text(
            0.03,
            0.03,
            f"peak {_I.max() / (np.abs(_U0) ** 2).max():.2f}\ndashed $w$ = {_w:.3f} mm",
            transform=_ax.transAxes,
            color="w",
            fontsize=8,
            va="bottom",
        )

    # w three ways at the marked planes. The analytic and ABCD columns are the same
    # closed form (one is w(z), the other falls out of q = z + i zR), so they agree
    # to machine precision; the FFT column is the independent one.
    _rows = "\n".join(
        f"| {_k} $z_R$ = {_k * _zR:.0f} mm "
        f"| {w_num(_fields[_k], _X):.5f} "
        f"| {_w0 * np.sqrt(1 + _k**2):.5f} "
        f"| {w_of(q_abcd(free(_k * _zR).M, q_waist(_w0, _lam)), _lam):.5f} |"
        for _k in _PLANES
    )
    _table = mo.md(
        "| plane | $w$ from power, 2nd moment | $w$ analytic | $w$ from ABCD $q$ |\n"
        "|:--|--:|--:|--:|\n" + _rows + "\n\nAll in mm."
    )

    mo.vstack([_fig, _table])
    return gauss, w_num


@app.cell
def _(mo):
    mo.md(r"""
    ### Erasing the phase

    `U -> |U|` keeps the intensity and throws away the wavefront curvature. The spot
    size at that plane is untouched, but the beam now looks like a **waist** there.

    Free space moves $q$ by $q \to q + z$, so $\mathrm{Im}\,q$ is fixed and
    $w^2 = \lambda|q|^2 / \pi\,\mathrm{Im}\,q$ is smallest where $\mathrm{Re}\,q = 0$.
    Erasing the phase sets $\mathrm{Re}\,q = 0$ *here*, so $w$ grows in **both**
    directions from this plane &mdash; the beam has forgotten the waist it came from,
    and propagating it backwards no longer returns the original field.

    Its new $w_0$ is larger, so it also spreads more slowly than the original. Note
    this is not about losing a focus: past its waist the original beam diverges
    monotonically too. Erase the phase *before* a waist and you really do destroy the
    focus that was coming.
    """)
    return


@app.cell
def _(R_of, beam_profile, free, gauss, mo, np, plt, q_waist, w_num, w_of):
    def waist_of(q, lam):
        """(w0, signed distance to the waist) implied by q. Negative is upstream."""
        return np.sqrt(lam * np.imag(q) / np.pi), -np.real(q)

    def q_from_field(U, X, lam):
        """q read straight off a complex field, no propagation needed: w from the
        intensity second moment, R from the quadratic phase across the centre row."""
        mid = U.shape[0] // 2
        x, row = X[mid], U[mid]
        keep = np.abs(row) ** 2 > 1e-4 * (np.abs(row) ** 2).max()  # ignore the noise floor
        c = np.polyfit(x[keep] ** 2, np.unwrap(np.angle(row[keep])), 1)[0]
        R = np.pi / (lam * c) if c else np.inf  # phase = c r^2  =>  R = pi / (lam c)
        return 1 / (1 / R - 1j * lam / (np.pi * w_num(U, X) ** 2))

    _lam, _zR, _X, _w00 = gauss["lam"], gauss["zR"], gauss["X"], gauss["w0"]
    _erased = {k: np.abs(U).astype(complex) for k, U in gauss["fields"].items()}

    _rows = []
    for _k, _U1 in gauss["fields"].items():
        for _tag, _U in (("as propagated", _U1), ("phase erased", _erased[_k])):
            _q = q_from_field(_U, _X, _lam)
            _wnew, _dist = waist_of(_q, _lam)
            _R = R_of(_q)
            _Rs = "inf" if abs(_R) > 1e6 else f"{_R:,.1f}"
            _rows.append(
                f"| {_k} $z_R$ | {_tag} | {w_of(_q, _lam):.4f} | {_Rs} "
                f"| {_wnew:.4f} | {_dist:+.1f} |"
            )

    # the measurement recovers the real waist from the propagated field
    assert np.isclose(waist_of(q_from_field(gauss["fields"][1], _X, _lam), _lam)[0], _w00, rtol=1e-3)

    # onward divergence: each erased field restarts as a waist of its own measured w
    _L = 12 * _zR
    _fig, _ax = plt.subplots(figsize=(9, 3.6))
    _zo, _wo = beam_profile([free(_L)], q_waist(_w00, _lam), _lam)
    _ax.plot(_zo / _zR, _wo, "C3", lw=1.6, label=f"with phase, $w_0$ = {_w00} mm")
    for _i, (_k, _U) in enumerate(_erased.items()):
        _w1 = w_of(q_from_field(_U, _X, _lam), _lam)
        _zb, _wb = beam_profile([free(_L - _k * _zR)], q_waist(_w1, _lam), _lam)
        _ax.plot(
            (_k * _zR + _zb) / _zR, _wb, f"C{_i}", lw=1.3, ls="--",
            label=f"erased at {_k} $z_R$, new $w_0$ = {_w1:.3f} mm",
        )
        _ax.axvline(_k, color="k", lw=0.6, alpha=0.4)
    _ax.set(
        xlabel="$z / z_R$",
        ylabel="w (mm)",
        xlim=(0, _L / _zR),
        ylim=(0, None),
        title="Same intensity, different beam: erasing the phase resets the waist",
    )
    _ax.legend(fontsize=8, loc="upper left")

    _table = mo.md(
        "| plane | field | $w$ here | $R$ here | implied $w_0$ | waist is at |\n"
        "|:--|:--|--:|--:|--:|--:|\n" + "\n".join(_rows)
        + f"\n\nmm throughout; *waist is at* is measured from that plane. "
        f"The real beam has $w_0$ = {_w00} mm at $z$ = 0."
    )

    mo.vstack([_fig, _table])
    return


if __name__ == "__main__":
    app.run()
