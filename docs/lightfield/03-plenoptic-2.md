# 3 — Plenoptic 2.0: focus the microlenses on the image, not at it

**One idea:** plenoptic 1.0 wastes spatial resolution because every pixel under a microlens
looks at the *same scene point*. Move the array off the image plane and focus each microlens
**on the image** instead of on the aperture. Now each microimage is a tiny photograph of a
small region, and its pixels carry distinct spatial detail.

Lumsdaine & Georgiev (2008/2009) called this the **focused plenoptic camera**. The rename to
"plenoptic 2.0" is marketing; the optics is a one-line change.

---

## The one-line change

Everything follows from choosing a different conjugate plane for the microlenses.

|  | plenoptic 1.0 | plenoptic 2.0 |
| --- | --- | --- |
| array position | \(z_\mu = v_0\) (on the image) | \(z_\mu = v_0 + a\) (off the image) |
| microlens focused on | the **aperture**, \(a = v_0\) | the **image**, \(a = z_\mu - v_0\) |
| microimage is a picture of | the main lens pupil | a patch of the scene |

Both obey the *same* thin-lens law — only \(a\) differs:

$$\frac{1}{a} + \frac{1}{b} = \frac{1}{f_\mu}, \qquad |m| = \frac{b}{a}$$

This is why `microlens_geometry()` in OWL handles all designs with one function, and why the
test suite can assert \(1/a + 1/b = 1/f_\mu\) for every mode. **There is one camera here,
with a knob.**

## Two ways to be off the image plane

$$a = z_\mu - v_0$$

is *signed*, and its sign names the two variants:

### Keplerian (real mode), \(a > 0\)

The array sits **behind** the image plane. The main lens forms a real image in mid-air, and
each microlens relays a piece of it onto the sensor. Microimages are **inverted**.
Requires \(a > f_\mu\) for a real relay.

```
            image forms here        MLA      sensor
 main lens        |                  ||       |
   ---)           *  <--- a --->     ||  b    |
                  |                  ||       |
```

### Galilean (virtual mode), \(a < 0\)

The array sits **in front of** the image plane. The converging cone is intercepted before it
focuses, so each microlens sees a *virtual* object behind itself. Microimages are **erect**.
Works for any \(|a| > 0\).

```
              MLA    sensor      image would form here
 main lens     ||     |                   |
   ---)        ||  b  |                   *
               ||     |                   |
```

Both give \(b>0\). Practically: Keplerian gives higher magnification for a given standoff;
Galilean is mechanically easier (array closer to the sensor) and keeps microimages erect,
which makes rendering code simpler. **The disparity sign flips between them** — a detail
that will silently invert your depth map if you ignore it.

## Why this buys resolution

A microimage now spans a real region of the image plane, of width \(d\cdot a/b\). Adjacent
microlenses are only \(d\) apart, so **neighbouring microimages overlap**, and the overlap
factor is exactly

$$\frac{a}{b} = \frac{1}{|m|} = \text{number of microlenses that see a given point}$$

That number *is* the angular sampling. And the useful pixels per microlens — the ones
carrying distinct spatial detail — are

$$\mu = d\,\frac{b}{a} = d\,|m|$$

This \(\mu\) is the **patch size**; [one-pager 4](04-rendering-and-depth.md) is about it.

So the fixed pixel budget gets re-divided:

| | plenoptic 1.0 | 2.0 Keplerian (\(a=3\)) | 2.0 Galilean (\(a=-3\)) |
| --- | --- | --- | --- |
| \(b\) (mm) | 0.505 | 0.600 | 0.429 |
| \(\|m\| = b/a\) | 0.0097 | 0.200 | 0.143 |
| matched patch (px) | **0.58 → 1** | **12.0** | **8.6** |
| spatial samples | 24 | **492** | 351 |
| angular samples | 103 | **5.0** | 7.0 |
| total pixels | 2460 | 2460 | 2460 |

Read the bottom three rows as one sentence: **the product is conserved, and 2.0 moves the
split**. A 20× gain in spatial resolution costs 20× in angular resolution. Nothing is
created; the trade is explicit and, crucially, *continuously tunable* by moving the array.

Plenoptic 1.0 is not a different camera — it is the \(a \to v_0\) limit, where \(|m|\)
becomes tiny and the matched patch collapses to a single pixel. The whole resolution penalty
of 1.0 falls out of \(|m| = b/a \approx f_\mu/v_0 \approx 1\%\).

## In ray space

The sampling tiles **shear over**. A plenoptic 1.0 pixel pins \(u\) and spans \(s\) across
the microlens; a 2.0 pixel mixes both, because sensor position now depends on where the ray
crossed the image plane *and* which microlens it went through. Slanted tiles tile the same
area — same total information — but with finer spacing along \(s\) and coarser along \(u\).

`tile_u_mm` / `tile_s_mm` in the result are the four corners of each pixel's parallelogram,
and `test_plenoptic_one_sampling_tiles_are_upright_in_ray_space` asserts the aspect ratio
difference.

## What it costs you: microimage depth of field

This is the limitation that does not appear in the plenoptic 1.0 story, and it is the one
that bites in practice.

A microlens is focused on **one** plane, \(a\). A scene layer whose image lands at \(a'\neq a\)
is *defocused inside its own microimage*, by

$$\text{blur} = d\,\frac{|b - b'|}{b'}, \qquad b' = \frac{f_\mu a'}{a' - f_\mu}$$

Once that blur exceeds the scene detail in the microimage, the detail is gone, and no amount
of clever rendering or multi-baseline matching recovers it. OWL reports
`microimage_blur_pixels` next to `texture_cell_pixels` so you can see the margin:

| layer | \(a'\) (mm) | blur (px) | detail (px) | resolved? |
| --- | --- | --- | --- | --- |
| near texture | 2.50 | 2.4 | 5.5 | yes |
| focus target | 3.00 | 0.0 | 4.6 | yes (exactly conjugate) |
| far backdrop | 4.02 | 3.0 | 6.8 | yes |

Push a layer to 700 mm and the blur exceeds the detail — that is
`test_a_layer_far_from_the_conjugate_plane_loses_microimage_detail`.

**So plenoptic 2.0 trades a hard resolution limit for a depth-of-field limit.** 1.0 works
over a huge depth range at terrible resolution; 2.0 works at good resolution over a
restricted range around the microlens conjugate plane. Choosing \(a\) is choosing where that
usable range sits and how wide it is — smaller \(a\) means more resolution and a tighter range.

---

## Check yourself

1. You slide the array from \(z_\mu=v_0\) outward to \(z_\mu = v_0 + 3\). What happens to spatial and angular resolution?
2. Why must Keplerian mode satisfy \(a > f_\mu\), while Galilean has no such floor?
3. A colleague reports 2.0 "beats 1.0 with no downside." What have they missed?
4. Microimages overlap 5×. How many microlenses see a given scene point, and what is the matched patch as a fraction of the pitch?

<details>
<summary>Answers</summary>

1. \(|m|=b/a\) rises from ~0.01 to 0.2, so spatial resolution rises ~20× (24→492 samples) and
   angular falls ~20× (103→5). The product is fixed at the pixel count.
2. Keplerian needs a **real** image from the microlens, which a thin lens only forms for an
   object beyond its focal length. Galilean's object is virtual (\(a<0\)), and
   \(b = f_\mu a/(a-f_\mu)\) is positive for every \(a<0\).
3. Microimage depth of field. 2.0 only resolves depths near the microlens conjugate plane;
   away from it the microimages blur and both rendering and correspondence fail. Also that
   rendered resolution becomes depth-dependent (one-pager 4).
4. 5 microlenses see each point; the matched patch is \(1/5\) of the pitch. Overlap factor,
   angular sample count, and pitch-to-patch ratio are all the same number \(a/b\).

</details>

---

**In OWL:** `PlenopticSpec(mode="keplerian" | "galilean", microlens_offset_mm=...)`,
`microlens_geometry()`.
**Next:** [4 — Rendering and depth](04-rendering-and-depth.md) turns the patch size into
both the refocus knob and the depth estimator.
