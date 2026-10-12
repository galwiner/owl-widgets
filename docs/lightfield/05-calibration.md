# 5 — Calibration and metrology: what you have to measure

**One idea:** every formula in this series assumes you know \(d\), \(b\), \(f_\mu\), \(z_\mu\),
and where each microimage centre lands on the pixel grid. On real hardware you know none of
them to the precision the maths demands. Plenoptic calibration is mostly about recovering the
microlens-to-sensor geometry, and it is unusually unforgiving.

---

## Why the tolerance is brutal

The sensitivity comes from one line in [one-pager 4](04-rendering-and-depth.md):

$$a' = \frac{d\,b}{\Delta\,p}$$

\(\Delta\) is a disparity of order 10 pixels. To get 1% depth accuracy you need \(\Delta\) to
~0.1 px, so you need microimage centres known to **sub-pixel** accuracy — across the whole
array, simultaneously. And note \(a'\) is a *small difference of large numbers*:
\(a' = z_\mu - v\), with \(z_\mu \approx 55\) mm and \(a' \approx 3\) mm. A 50 µm error in
array standoff is a ~1.7% error in \(a'\), which propagates straight into depth.

**Plenoptic depth accuracy is limited by mechanical metrology, not by algorithms.**

## Step 1 — the white image

Uniformly illuminate a flat diffuse field and expose. Each microlens forms a disc, and this
"white image" is the workhorse calibration frame. Standard for Lytro-class devices; do it per
aperture setting.

From it you extract:

| quantity | how | why you need it |
| --- | --- | --- |
| microimage centres | centroid each disc | the origin for every crop and disparity |
| pitch in pixels \(d/p\) | fit a lattice to the centres | almost never an integer |
| array rotation | the lattice's angle vs the pixel rows | a fraction of a degree matters |
| \(f/\#\) match | disc diameter vs pitch | overlap or wasted pixels |
| vignetting | disc brightness profile | flat-field correction before matching |

**Fit a global lattice; do not use per-disc centroids directly.** Independent centroids carry
independent noise and produce disparity errors that masquerade as depth structure. A
two-parameter (origin, pitch) plus rotation model over thousands of lenslets averages the
noise down.

Non-integer pitch is the norm — e.g. 0.131 mm on a 2.18 µm pixel is 60.05 px. Every crop
therefore needs interpolation, and rounding to whole pixels injects a periodic artifact at the
lenslet frequency. Resample; don't round.

Rotation is worse than it looks: over 2000 lenslets, 0.1° of array rotation walks the centres
by ~3.5 lenslet pitches across the field. Left uncorrected it looks like a smooth depth ramp.

## Step 2 — the axial unknowns

\(b\), \(f_\mu\), and \(z_\mu\) are the hard ones, because the first two are internal to a
bonded assembly.

- \(f_\mu\) — from the vendor, or measure a spare array on a bench. Watch for the design
  wavelength; if you are working in IR and the array was specified in visible light,
  dispersion shifts \(f_\mu\) and hence \(b\).
- \(b\) — rarely measurable directly. Infer it: image a target at a **known** distance, measure
  \(\Delta\), and invert \(a' = db/(\Delta p)\). This is the calibration that matters most.
- \(z_\mu\) — follows from \(b\), \(f_\mu\) and the lens law, plus the main lens focus setting.

**Calibrate against known distances rather than trusting the mechanical stack.** Use three or
more target distances spanning the working range and fit; one distance cannot separate a
\(b\) error from a \(z_\mu\) error.

Then verify with an independent check: the seam-continuity metric from one-pager 4 should
minimise at the patch size your calibration predicts. If the seam minimum and the predicted
matched patch disagree, your geometry is wrong — and this test needs no ground-truth target.

## Step 3 — photometric and stray light

Correspondence assumes the same scene point looks the same in neighbouring microimages. Three
things break that:

- **Vignetting** — microimage edges are dimmer, so a feature's apparent brightness depends on
  where it sits. Flat-field with the white image before matching, not after.
- **Crosstalk** — with fill ratio > 1 microimages overlap and contaminate each other. OWL's
  `microimage_fill_ratio` is the design-time version of this check; measure it on hardware from
  the white image. Overlap is much worse than gaps: gaps cost pixels, overlap costs
  correctness.
- **Diffraction** — a 130 µm lenslet at f/4.5 has an Airy diameter around 7 µm in the visible,
  several pixels at fine pitch. Geometric optics predicts a patch size that diffraction will
  not deliver. In the IR this scales with \(\lambda\) and gets notably worse.

## Step 4 — depth validation

Report depth error against known distances, not disparity residuals. Because
\(\sigma_Z \propto Z^2\), a single-distance check tells you almost nothing.

Minimum useful set:

1. Targets at several distances across the range, with **aperiodic** texture. A periodic chart
   will give you confidently wrong answers (one-pager 4).
2. Report the **confident fraction** alongside accuracy. A method that answers 20% of pixels at
   2% error is not comparable to one answering 90% at 5%, and quoting only the error hides it.
3. Include an occlusion boundary deliberately. Edges are where depth methods fail, and where
   the depth-from-focus edge artifact from one-pager 1 shows up.
4. Verify the measured microimage blur against the predicted
   `microimage_blur_pixels` to confirm you have the depth-of-field window you designed.

## How this compares with a dot-projector depth camera

Worth being blunt, because the comparison decides whether a plenoptic camera belongs in a
product at all:

| | plenoptic (1.0 or 2.0) | structured light / stereo |
| --- | --- | --- |
| baseline | the lens aperture, ~10 mm | the mechanical baseline, 20–100 mm |
| depth precision at 1 m | modest | much better, by the baseline ratio |
| texture dependence | needs scene texture | projector supplies its own |
| single aperture | yes — no occlusion between views | parallax occlusion gaps |
| resolution cost | real (1.0 severe, 2.0 moderate) | none |
| calibration burden | sub-pixel MLA registration | extrinsics between two units |

A plenoptic camera is a stereo rig whose baseline is trapped inside one lens. It wins on
compactness, single-shot capture, no inter-camera occlusion, and post-capture refocus. It
loses on ranging precision, and it pays in resolution and calibration effort. For a
dot-projector system the texture problem disappears entirely, because the projector guarantees
the aperiodic-texture condition that plenoptic correspondence needs from the scene.

---

## Check yourself

1. Your depth map shows a smooth left-to-right ramp on a flat wall. Most likely cause?
2. Why calibrate \(b\) from a known-distance target instead of measuring the stack-up?
3. Microimages overlap by 10%. Why is that worse than a 10% gap?
4. A visible-light-specified MLA is used at 940 nm. What shifts, and what does it do to the rendering?

<details>
<summary>Answers</summary>

1. Array rotation relative to the pixel grid (or a pitch error). Both make the assumed centres
   drift linearly across the field, biasing every disparity in one direction. Re-fit the
   lattice including rotation.
2. \(b\) is inside a bonded assembly, it is a small number multiplying your disparity, and
   mechanical tolerances are comparable to \(b\) itself. Inverting a known distance measures
   the optical quantity you actually use, absorbing the errors you cannot see.
3. A gap wastes pixels but leaves every microimage valid. Overlap puts light from neighbouring
   lenslets into the same pixels, so microimages are no longer independent views — correspondence
   and patch rendering both break, and no post-processing separates the contributions.
4. \(f_\mu\) lengthens with wavelength, so the actual \(b\) no longer satisfies the lens law for
   your assumed \(a\): the conjugate plane moves, the matched patch size changes, and the
   microimage depth of field shifts. Rendering with the visible-light patch size produces seam
   artifacts everywhere. Diffraction blur also grows roughly 1.7×.

</details>

---

**In OWL:** `microimage_fill_ratio`, `matched_pitch_mm`, `microimage_blur_pixels`,
`texture_cell_pixels`, `seam_ratio`, and the `confident` flag on depth estimates.
**Back to:** [1 — Ray space](01-ray-space.md).
