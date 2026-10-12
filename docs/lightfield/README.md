# Light fields and plenoptic cameras

Five one-pagers and two marimo notebooks, building from "what is a light field" to "what you
have to measure to build one." Read in order; each is ~5 minutes.

| # | one-pager | the one idea |
| --- | --- | --- |
| 1 | [Ray space](01-ray-space.md) | A light field is radiance indexed by ray. Depth becomes slope; refocusing becomes shear-then-sum. |
| 2 | [Plenoptic 1.0](02-plenoptic-1.md) | Put the microlens array **on** the image plane and focus it on the aperture. Costs almost all spatial resolution. |
| 3 | [Plenoptic 2.0](03-plenoptic-2.md) | Focus the microlenses **on the image** instead. Same lens law, different conjugate; resolution comes back. |
| 4 | [Rendering and depth](04-rendering-and-depth.md) | Patch size is the refocus knob, the resolution, and the depth estimate — all one number. |
| 5 | [Calibration](05-calibration.md) | Sub-pixel microlens registration, and why depth accuracy is a metrology problem. |

## The through-line

Everything in these notes is one geometry with one knob. A microlens array sits at \(z_\mu\)
with the sensor \(b\) behind it, and every microlens obeys

$$\frac{1}{a} + \frac{1}{b} = \frac{1}{f_\mu}$$

The camera families differ *only* in which plane \(a\) refers to:

- **plenoptic 1.0** — array on the image plane, microlenses focused on the **aperture**
- **plenoptic 2.0 Keplerian** — array behind the image plane, focused on the **image** (\(a>0\), inverted microimages)
- **plenoptic 2.0 Galilean** — array in front of the image plane, focused on the virtual image (\(a<0\), erect microimages)

And one invariant holds throughout, because a pixel budget is a pixel budget:

$$\text{spatial samples} \times \text{angular samples} = \text{total pixels}$$

Plenoptic 1.0 is the extreme end of that trade, not a separate design. Its notorious
resolution penalty falls out of \(|m| = b/a \approx f_\mu/v_0 \approx 1\%\).

## Notebooks

```sh
cd /Users/galwiner/code/sandbox/optics
uvx --from marimo==0.24.0 marimo edit --sandbox notebooks/light_field_ray_space.py
uvx --from marimo==0.24.0 marimo edit --sandbox notebooks/plenoptic_cameras.py
```

- `light_field_ray_space.py` — ray space for a three-layer scene, sub-aperture views,
  shear-and-sum refocusing, and depth from focus.
- `plenoptic_cameras.py` — the three designs side by side: raw sensor, microimages, sampling
  tiles in ray space, patch rendering, and multi-baseline depth.

## Simplifications, stated plainly

- **One transverse axis.** \(L(u,s)\) is 2D rather than 4D, which makes every visualization a
  plottable image. The second axis behaves identically; nothing conceptual is lost.
- **Geometric and paraxial.** Thin lenses, no aberrations. Diffraction is discussed in
  one-pager 5 but not simulated — for that, see OWL's `wave.py` and the aperture studies.
- **Fronto-parallel opaque layers.** Occlusion is modelled (front-to-back compositing with
  hard edges); slanted or transparent surfaces are not.

## Code

| module | contents |
| --- | --- |
| `src/owl/lightfield.py` | `LightFieldLayer`, `LightFieldSpec`, `calculate_light_field`, `sample_radiance`, `layer_beta` |
| `src/owl/plenoptic.py` | `PlenopticSpec`, `calculate_plenoptic`, `microlens_geometry` |
| `tests/test_lightfield.py` | 33 tests, including depth-from-focus recovery |
| `tests/test_plenoptic.py` | 37 tests, including the thin-lens law in all modes and the spatial×angular invariant |

Both calculators follow OWL's existing study pattern: a frozen, validated, serializable spec
in, a strict-JSON dictionary of plot-ready values out, no plotting in Python.

## Sources

- R. Ng, *Digital Light Field Photography*, PhD thesis, Stanford, 2006 — plenoptic 1.0, Fourier slice refocusing.
- A. Lumsdaine & T. Georgiev, *The Focused Plenoptic Camera*, ICCP 2009 — plenoptic 2.0 and full-resolution rendering.
- T. Georgiev & A. Lumsdaine, *Focused plenoptic camera and rendering*, J. Electronic Imaging 19(2), 2010.
- E. Adelson & J. Wang, *Single Lens Stereo with a Plenoptic Camera*, IEEE TPAMI 1992 — the original.
- M. Levoy & P. Hanrahan, *Light Field Rendering*, SIGGRAPH 1996 — the two-plane parameterization.
