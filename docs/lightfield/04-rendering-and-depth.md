# 4 — Rendering and depth: one number does both jobs

**One idea:** to turn a focused-plenoptic raw image into a photograph you crop a patch from
the centre of each microimage and tile the crops. The **patch size** is the only parameter —
and it is simultaneously the refocus control, the resolution control, and the depth estimate.

---

## Full-resolution rendering, in three lines

```
for each microlens k:
    crop `patch_pixels` pixels from the centre of microimage k
    flip it if the microimages are inverted (Keplerian)
    append to the output
```

That's it. That is Lumsdaine & Georgiev's full-resolution rendering. The rendered image has

$$N_\text{rendered} = N_\text{lenslets} \times \text{patch\_pixels}$$

pixels, compared with \(N_\text{lenslets}\) for plenoptic 1.0.

The flip matters: Keplerian microimages are inverted real images, so tiling them unflipped
produces an image that is locally mirrored inside every patch — a subtle, striped corruption
that is easy to ship by accident. Galilean microimages are erect and need no flip.

## Why the patch size selects a depth

Microlens \(k\) at position \(s_k\) projects a point \(X\) on the plane a distance \(a'\) in
front of the array to sensor offset

$$\xi = -\frac{b}{a'}\,(X - s_k)$$

Adjacent microlenses are \(d\) apart, so tiling without gaps or overlap requires the crop
width \(\mu'\) to satisfy \((a'/b)\,\mu' = d\), i.e.

$$\boxed{\;a' = \frac{d\,b}{\mu'}\;}$$

**Patch size and rendered plane are inverses.** Crop small patches → large \(a'\) → a plane
far in front of the array. Crop large patches → small \(a'\) → a plane close to it.

This has a consequence people find surprising: in plenoptic 2.0 **rendered resolution depends
on the depth you render**. There is no single "native resolution." Objects at the plane that
happens to need big patches come out sharp and detailed; objects needing small patches come
out coarse.

Consequences worth internalising:

- The matched patch for the design plane is \(\mu/p = \text{pixels\_per\_lens}\cdot b/a\).
- Patch size is quantised to whole pixels, so the renderable planes are **discrete**.
- \(\mu' \le d\) always (you cannot crop more than a microimage), which caps resolution gain
  at `pixels_per_lens` and floors \(a'\) at \(b\).

## The same number is the disparity

Take one scene point on the plane at \(a'\), seen by microlenses \(k\) and \(k{+}1\). Its
sensor offsets differ by \((b/a')\,d\), which in pixels is

$$\Delta = \frac{d\,b}{a'\,p} = \text{pixels\_per\_lens}\cdot\frac{b}{a'} = \frac{\mu'}{p}$$

**The microimage-to-microimage disparity equals the matched patch size.** One quantity, two
readings:

- **as a renderer:** how many pixels to crop
- **as a measurement:** the stereo disparity, hence the depth

`test_matched_patch_equals_the_microimage_disparity` pins this. It means you can *measure*
the right patch size from the data rather than assuming it — which is exactly what depth
estimation is.

## Reading depth out of the raw image

Convert a measured disparity to an object distance in three steps:

$$\Delta \;\longrightarrow\; a' = \frac{d\,b}{\Delta\,p} \;\longrightarrow\; v = z_\mu - a'
\;\longrightarrow\; \frac{1}{Z} = \frac{1}{F} - \frac{1}{v}$$

Two practical traps:

**Repetitive texture is ambiguous.** Correlating microimages of a periodic grating gives many
equally good peaks. My first attempt at this returned correlations of exactly 1.000 at
completely wrong shifts, for two compounding reasons — a periodic test target, and normalized
correlation computed over a 2-pixel overlap, which is \(\pm1\) for *any* pair of samples.
Enforce a minimum overlap, and use aperiodic texture.

**Use many baselines.** This is the part that makes it work. Microlens \(k\) against \(k{+}n\)
must agree at \(n\Delta\), so score all available \(n\) together and false peaks collapse.
But note the ceiling: baseline \(n\) needs \(n\Delta\) to still fit inside a microimage, so

$$n_\text{max} \approx \frac{a}{b} = \text{angular samples}$$

**The number of baselines you get is the angular resolution you paid for.** High spatial
resolution in 2.0 means few baselines and therefore weaker depth estimation. The trade-off
propagates all the way through.

With the defaults (multi-baseline, aperiodic texture, confidence filtering on correlation
≥ 0.6 and peak ratio ≥ 1.1), OWL recovers the three layer distances with a median error of
about 3%, keeping roughly three quarters of the lenslet positions.

## Seam continuity as a cross-check

A correct patch size makes neighbouring crops join seamlessly; a wrong one produces a
picket-fence at every patch boundary. `seam_ratio` compares the jump across each seam with
the ordinary sample step inside a crop, so ~1 is seamless and ≫1 is a fence:

| design | best seam ratio | at patch |
| --- | --- | --- |
| Galilean (\(a=-3\)) | 0.70 | 9 px (matched: 8.6) |
| Keplerian (\(a=+3\)) | 2.18 | 14 px (matched: 12.0) |
| plenoptic 1.0 | 778 | — |

Three things to read here:

1. **Galilean lands on its matched patch**, confirming the theory end to end.
2. **Keplerian lands between** its layers' matched patches (12.0, 14.4, 9.0) because a single
   global patch size can only render one depth seamlessly. Real renderers therefore vary the
   patch size per region, guided by the depth map — which closes the loop.
3. **Plenoptic 1.0 never joins up at all** (ratio ~778). Its microimages are pictures of the
   aperture, not of scene patches, so tiling crops of them is meaningless. Patch rendering is
   not a better algorithm for 1.0; it is the wrong algorithm. Use shift-and-add instead.

---

## Check yourself

1. You halve the patch size. What happens to rendered resolution and to the plane in focus?
2. Why can't one patch size render a whole 3D scene sharply?
3. You render Keplerian data without flipping patches. What does it look like?
4. You need better depth precision, so you move the array closer to the image plane to raise resolution. What happens to the depth estimate?

<details>
<summary>Answers</summary>

1. Resolution halves. \(a' = db/\mu'\) doubles, so the rendered plane moves twice as far in
   front of the array — i.e. to a nearer object distance.
2. Because the matched patch depends on \(a'\), which depends on depth. One patch size renders
   one plane seamlessly; everything else shows seam artifacts. Hence depth-guided rendering
   with a spatially varying patch size.
3. Each patch is individually mirrored while the overall layout stays correct — a periodic
   striped scrambling at the patch scale, often mistaken for a registration bug.
4. It gets **worse**. Smaller \(a\) means larger \(|m|=b/a\), so fewer angular samples,
   fewer usable baselines, larger disparities that overflow the microimage, and a narrower
   microimage depth of field. Resolution and depth quality pull in opposite directions.

</details>

---

**In OWL:** `calculate_plenoptic(...)["render"]["sweep"]` and `["depth"]["estimates"]`.
**Next:** [5 — Calibration and metrology](05-calibration.md): what you actually have to
measure to make any of this work on hardware.
