# OWL — Optics Widget Library

Small, inspectable optics experiments in Python notebooks. Built on anywidget; inspired by [wigglystuff](https://github.com/koaning/wigglystuff)'s notebook-first, composable widgets. No wigglystuff dependency or copied implementation.

**Supported models:** free space, ideal thin lenses, flat/curved refractive interfaces, flat/curved mirrors, thick lenses in air, circular hard apertures, paraxial rays, ideal Gaussian references, and scalar paraxial FFT diffraction. `Bench` supports all these elements, tunes wavelength/waist and wave sampling, and defaults to clipped rays over the x–z physical-intensity center cut. The trace selector also offers physical optics alone, rays alone, and the unclipped Gaussian reference; the transverse cross-section panel remains plane-selectable. Calculations live in Python, not duplicated in JavaScript.

## Install

OWL requires Python 3.12 or newer.

```sh
pip install owl-widgets
```

Or with uv:

```sh
uv add owl-widgets
```

The distribution name is `owl-widgets`; the Python import is `owl`. Runtime JavaScript and CSS, including Plotly.js, ship in the wheel for offline use.

## Run the notebooks

From this checkout's `optics` directory:

```sh
uvx --from marimo==0.24.0 marimo edit --sandbox notebooks/optics_basics.py
uvx --from marimo==0.24.0 marimo edit --sandbox notebooks/apertures.py
uvx --from marimo==0.24.0 marimo edit --sandbox notebooks/keplerian_telescope.py
```

Each notebook declares all dependencies inline (PEP 723) and pins `owl-widgets==0.1.1` from PyPI. No global installation, local checkout, or `sys.path` modification is needed.

- `optics_basics.py`: free propagation, thin lenses, ray focus versus Gaussian waist, wavelength tuning, mirrors, interfaces, and thick lenses.
- `apertures.py`: controlled Fresnel aperture sweeps, brightest-plane spots, launch-height-colored ray/wave comparisons, stop taxonomy, field-height-colored ray fans, relative illumination, and cat’s-eye pupil maps.
- `keplerian_telescope.py`: contrasts a two-positive-lens ray-optical afocal spacing ($f_{obj} + f_{eye}$) with the spacing that minimizes Gaussian-beam divergence.

Each experiment owns independent inputs. Study controls update their plots and the notebook's downstream tables and narrative together.

## Compose a bench

```python
import marimo as mo
from owl import Bench, FreeSpace, GaussianBeam, OpticalSystem, ThinLens

widget = Bench(
    OpticalSystem((FreeSpace(60), ThinLens(50), FreeSpace(150))),
    beam=GaussianBeam(waist_mm=0.07, wavelength_nm=633),
    ray_span_mm=0.1,
)
bench = mo.ui.anywidget(widget)
bench
```

In a **separate downstream marimo cell**, read `bench.value` to react to edits:

```python
settings = bench.value["settings"]
system = OpticalSystem.from_dict(settings["system"])
beam = GaussianBeam.from_dict(settings["beam"])
profile = system.gaussian(beam)
profile.z_mm, profile.radius_mm, profile.q_mm
```

`Bench` is an anywidget, with no marimo dependency. Other notebook hosts have not yet been integration-tested. All JavaScript/CSS ships in the wheel; no CDN or Node build is needed to use it.

### Settings and measurements

- `bench.value["result"]`: ray heights, sampled Gaussian radii, element positions, output-plane measurements, and wave results. `result["rays"]["alive"]` is a sample-by-ray survival mask; blocked rays stay blocked.
- `result["longitudinal"]` contains the x–z physical-intensity center cut (`|U|²` normalized to the input peak). The bench shows it on a three-decade logarithmic scale with rays overlaid by default.
- `result["cross_sections"]` contains `planes`, `x_mm`, `window_mm`, and `warnings`. Each plane has `label`, `z_mm`, `intensity`, and `transmission`; `intensity[y][x]` uses `x_mm` for both transverse axes. Planes retain the input and one exit per original element, in encounter order.
- `widget.to_dict()` / `Bench.from_dict(settings)`: detached JSON-compatible experiment settings, including `wave = {"grid_size": ..., "window_mm": ...}`.
- Assign a **new complete** `widget.settings` dictionary for programmatic updates; nested in-place edits do not trigger trait notifications.
- Invalid numerical edits retain the last valid calculation and expose `error`.
- View selection is local to each display and is not part of the saved optical experiment.
- Sliders preview locally while scrubbing and recalculate on release; number inputs support values outside the default slider ranges.

### Apertures and linked cross sections

`Aperture(radius_mm, x_mm=0, y_mm=0)` is exported from `owl`: a circular hard opening, including its boundary. Meridional rays lie at transverse `x=0`; both aperture offsets affect clipping. Apertures do not modify the Gaussian q reference.

`Bench(..., grid_size=128, window_mm=None)` accepts keyword-only wave settings. Grid sizes are 64, 128, 256, or 512; `window_mm` is the full square width, with `None` selecting an automatic estimate. The bench exposes these sampling controls in its UI.

Create the source and linked display in the **same marimo cell**, then read values only downstream:

```python
from owl import Aperture, CrossSection

source = Bench(
    OpticalSystem((Aperture(0.3), FreeSpace(100))),
    beam=GaussianBeam(0.15, 633),
    grid_size=256,
    window_mm=2,
)
source_view = mo.ui.anywidget(source)
section_view = mo.ui.anywidget(CrossSection(source))
mo.vstack([source_view, section_view])
```

`CrossSection(source)` observes the existing `Bench` calculation; it does not propagate a second field. Each display selects its own plane. Do not reconstruct the source from `source_view.value` in a reactive downstream cell. Close a discarded raw `CrossSection` widget to detach its observer.

Intensity is normalized to the **input peak**, not each plane's peak. The longitudinal center cut uses a three-decade logarithmic scale; transverse heatmaps use a fixed black-to-gold 0–1 scale, saturating above 1. The plane-selected transverse center slice (nearest `y=0`) shares a vertical scale across all planes and retains focused peaks above 1. Transmission is sampled integrated power divided by sampled input power, not a ray-count fraction.

The scalar Fresnel solver uses a **periodic FFT window**. Auto sizing follows the unclipped Gaussian and aperture extents, not all diffracted light. Increase window width to check wraparound and grid size to check hard-edge/phase sampling; increasing width at fixed grid also coarsens resolution. Hard circular masks require convergence checks. Warnings flag risks, and their absence is not proof of convergence. Interfaces omit Fresnel reflection losses.

## Aperture study widgets

The aperture notebook uses small, independent study widgets so controls stay beside the plots they affect. `ApertureFocusStudy()` renders the four-case longitudinal/brightest-plane Fresnel comparison. `RayWaveStudy()` renders the matched ray-density/Fresnel comparison at the geometric image; passing fan rays are colored by launch height and blocked rays are red. `ApertureStudy()` remains available as a combined compatibility view.

```python
from owl import ApertureFocusStudy, ApertureStudySpec, RayWaveStudy

focus = mo.ui.anywidget(ApertureFocusStudy(ApertureStudySpec(
    grid_size=256,
    window_mm=8,
    ray_count=100_000,
)))
focus

comparison = mo.ui.anywidget(RayWaveStudy(ApertureStudySpec()))
comparison
```

`StopRayStudy()` renders the aperture-stop, field-stop, and vignetting comparison, including field-height-colored ray fans, chief and marginal rays, geometric relative illumination, and stop coefficients/classification. `PupilMapStudy()` independently renders the field-dependent cat’s-eye pupil maps. `StopStudy()` remains the combined compatibility view.

```python
from owl import PupilMapStudy, StopRayStudy, StopStudySpec

stops = mo.ui.anywidget(StopRayStudy(StopStudySpec()))
stops

pupils = mo.ui.anywidget(PupilMapStudy(StopStudySpec()))
pupils
```

Both are AnyWidgets with synced `settings`, `result`, and `error`. Assign complete settings dictionaries; invalid updates roll back atomically. `ApertureStudySpec` and `StopStudySpec`, plus `calculate_aperture_study()` and `calculate_stop_study()`, provide the same validated calculations without a frontend. Results use finite JSON and expose the arrays and metrics used by the plots, so downstream marimo cells can build live tables and explanations.

## Numerical interface

```python
import numpy as np
from owl import FreeSpace, GaussianBeam, OpticalSystem, ThinLens

system = OpticalSystem((FreeSpace(100), ThinLens(50), FreeSpace(100)))
rays = system.trace(np.array([[0.1, -0.1], [0.0, 0.0]]))
profile = system.gaussian(GaussianBeam(0.25, 1000))
matrix = system.matrix()
```

- Lengths: **mm**; source wavelength: **nm**; ray angles: **rad**.
- Rays use `(height, angle)` column vectors; matrix composition follows element encounter order.
- `RayTrace.rays` has shape `(samples, 2, rays)`; samples retain the input and each element exit, expanding thick lenses into entry/gap/exit.
- Both trace types expose per-sample `n` (refractive index) and `s` (direction, +1/-1). `z_mm` is signed laboratory position and can decrease after reflection.
- `length_mm` is total traveled geometric length, including glass thickness, not output z or index-weighted optical path length. Use `output_z_mm`, `output_n`, and `output_direction` for the output state.
- Gaussian input: waist at `z=0`, in air, `M²=1`; `q=z+i z_R`. Radius is the **1/e² intensity radius**.
- `GaussianTrace` retains both sides of surfaces and internal thick-lens propagation. A sampled minimum is not an exact waist measurement; the notebook uses output `q` for exact free-continuation calculations in the output medium, with local wavelength `beam.wavelength_mm / system.output_n`.
- Free-continuation distances follow the outgoing direction: `q(d) = q_out + d`, `z(d) = output_z_mm + output_direction * d`. Negative distances extrapolate the output field, not propagation back through earlier elements.
- Bench rays are a parallel fan, not a sampled phase-space representation of the Gaussian beam. Both plot layers use the same physical units; axis extents auto-fit the selected layers.

### Surfaces and return paths

Import `Interface`, `Mirror`, and `ThickLens` from `owl`. Flat surfaces use Python `np.inf` (JSON `null`); radius zero is invalid. An interface's positive radius places its center of curvature along the incident direction; a mirror's positive radius is concave. `Interface(R, n1, n2)` requires `n1` to match the current medium. `FreeSpace(d)` travels a nonnegative distance in that medium; `ThickLens(R1, R2, thickness, n)` requires surrounding air.

Systems list elements in **encounter order**, not sorted laboratory z. Mirrors reverse direction but do not automatically revisit earlier optics. Explicitly append return-path gaps and surfaces: a reversed interface is `Interface(-R, n2, n1)`, and a reversed thick lens is `ThickLens(-R2, -R1, thickness, n)` (swap and negate radii). Keep return-path indices consistent too.

`StopStudy` classifies the controlled thin-lens relay's pupil-plane, image-plane, and intermediate stops from its A/B coefficients. General multi-element automatic stop selection, nonparaxial physical optics, beamlets, dispersion, aberrations, polarization, and nonideal `M²` are not implemented yet. Changing wavelength does not change an ideal lens's focal length. Very strong lenses/tight beams can violate the paraxial assumption; the core validates numerical inputs, not physical applicability.

## Develop and validate

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, testing, and pull-request guidance. The main validation commands are:

```sh
uv run --no-project --refresh-package owl-widgets --with . --with pytest pytest tests
uvx --from marimo==0.25.1 marimo check --strict notebooks/optics_basics.py notebooks/apertures.py notebooks/keplerian_telescope.py

uvx --from marimo==0.25.1 marimo export html --sandbox notebooks/optics_basics.py -o /tmp/owl-optics-basics.html
uvx --from marimo==0.25.1 marimo export html --sandbox notebooks/apertures.py -o /tmp/owl-apertures.html
uvx --from marimo==0.25.1 marimo export html --sandbox notebooks/keplerian_telescope.py -o /tmp/owl-keplerian-telescope.html

uv build
```

Browser renderer tests (Node.js; first run downloads Chromium):

```sh
npm exec --yes --package=@playwright/test -- playwright install chromium
npm exec --yes --package=@playwright/test -- node --test tests/test_frontend.mjs
npm exec --yes --package=@playwright/test -- node --test tests/test_studies_frontend.mjs
```

Browser tests exercise the real renderer with a model double, not a live marimo kernel. Python tests cover propagation and widget updates separately. Static HTML export runs the notebook but is not a substitute for a live kernel for Python-backed controls.

## Community and security

Contributions are welcome; see [`CONTRIBUTING.md`](CONTRIBUTING.md). Report suspected vulnerabilities privately according to [`SECURITY.md`](SECURITY.md), not through a public issue. OWL is available under the [MIT License](LICENSE), with bundled dependency notices in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Publication

Distribution name: `owl-widgets`; Python import: `owl`; working version: `0.1.1`. Licensed under the MIT License; see `LICENSE`.

Version `0.1.1` is published at [PyPI](https://pypi.org/project/owl-widgets/0.1.1/). The example notebooks pin that release in their inline PEP 723 dependencies. Existing `abcd/` notebooks are unchanged.
