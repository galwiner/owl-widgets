# 2 — Plenoptic 1.0: put a microlens array at the image plane

**One idea:** the sensor destroys the light field by summing over the aperture. Plenoptic 1.0
prevents that by placing a microlens array exactly where the image forms, and letting each
microlens **spread the aperture out across a patch of pixels** instead of collapsing it.

---

## The layout

```
 object      main lens              MLA at v0        sensor
                 |                      ||          |
   ----->        |)        ...           ||   b     |
                 |                      ||          |
                 |<-------- v0 -------->||<-- b --->|
```

Three commitments define the design:

1. The array sits **on** the image plane, \(z_\mu = v_0\).
2. Each microlens is focused on the **main lens aperture**, so with \(a = v_0\),
   $$\frac{1}{v_0} + \frac{1}{b} = \frac{1}{f_\mu}$$
3. The sensor sits at that \(b\), which since \(v_0 \gg f_\mu\) is barely more than \(f_\mu\).
   "Microlenses focused at infinity" is the usual shorthand and is accurate to about 1%.

## What one microimage contains

Because each microlens images the aperture, **the patch of pixels behind microlens \(k\) is
a little picture of the main lens**, seen from the scene point that microlens sits on.

That is the whole trick, and it gives a beautifully clean split of coordinates:

| coordinate | where it lives | meaning |
| --- | --- | --- |
| \(s\) — **spatial** | *which* microlens | position in the image |
| \(u\) — **angular** | *which pixel* inside the microimage | part of the aperture used |

So the raw sensor is a direct, almost unprocessed sampling of \(L(u,s)\). Reading it out:

- Fix a pixel index and collect it from every microlens → a **sub-aperture image**: the
  whole scene as viewed through one small part of the lens. A pinhole view.
- Collect all pixels under one microlens → the **angular fan** at that one image point.

In ray space the sampling tiles come out **upright**: a pixel pins down \(u\) and spans the
microlens width in \(s\). That rectangular grid is the signature of plenoptic 1.0.

## f-number matching

Microimages must exactly abut: overlap means neighbouring lenslets contaminate each other,
gaps mean wasted pixels. The microimage width is the aperture demagnified by \(b/z_\mu\),
so tiling requires

$$\underbrace{\frac{b}{d}}_{\text{microlens } f/\#} \;=\; \underbrace{\frac{z_\mu}{2A}}_{\text{main lens } f/\#}$$

**Match the f-numbers, not the focal lengths.** This is the single most important
manufacturing constraint in any plenoptic camera, and it is why these cameras have a fixed
working aperture — stop the main lens down and the microimages shrink, leaving dead pixels
and a smaller angular range.

In OWL, `microimage_fill_ratio` reports how close you are, and `matched_pitch_mm` tells you
the pitch that would make it exactly 1:

| | value |
| --- | --- |
| main lens | f/4.33 |
| microlens (\(b=0.505\) mm, \(d=0.131\) mm) | f/3.85 |
| fill ratio | 0.889 — under-filled, 11% of pixels wasted |
| pitch that would match | 0.1165 mm |

## The price: resolution

Here is why Lytro pictures were small. **Final image resolution = number of microlenses.**
Every pixel under a microlens buys an angular sample, not a spatial one.

With the defaults — 41 microlenses, 60 pixels each, 2460 pixels total:

| | plenoptic 1.0 |
| --- | --- |
| spatial samples | 41 |
| angular samples | 60 |
| total pixels | 2460 |

A 2460-pixel sensor yields a 41-pixel photograph. Scale that up: a 16 Mpx sensor with
10×10 pixels per lenslet yields a 0.16 Mpx image. That is the plenoptic 1.0 bargain, and
it is what plenoptic 2.0 exists to renegotiate.

Note the invariant, which holds for every design in this series:

$$\text{spatial} \times \text{angular} = \text{total pixels}$$

You never create information. You only choose how to divide a fixed pixel budget between
"where" and "which direction." Plenoptic 1.0 takes the most extreme split available.

## Refocusing it

Shift-and-add: take each sub-aperture image, slide it by an amount proportional to its
\(u\), and sum. That is the discrete form of the shear-then-project integral from
[one-pager 1](01-ray-space.md) — the shift *is* the shear. The refocusable range is set by
how far a scene point's ray-space streak stays inside the sampled region.

---

## Check yourself

1. You stop the main lens from f/4 to f/8. What happens to the raw image?
2. Why does a microimage look like a disc, and what is that disc a picture of?
3. Your sensor is 4000×3000 with 20×20 pixels per microlens. How big is the photograph?
4. Where does a microimage of a *badly out of focus* scene point appear?

<details>
<summary>Answers</summary>

1. Each microimage shrinks to half its diameter, so ~75% of the pixels under each lenslet
   go dark. You lose angular samples and gain nothing; the spatial resolution is unchanged.
2. It is an image of the main lens exit pupil, formed by that microlens. Its shape is the
   aperture's shape — which is why iris blades show up in the microimages.
3. 200×150 pixels. 12 Mpx of sensor, 0.03 Mpx of picture.
4. In the *same place* — under the microlens at its in-focus image position — because the
   microlens position encodes \(s\) only. Defocus changes the **distribution across the
   microimage**, not which microlens lights up. Defocus has become angular structure.

</details>

---

**In OWL:** `PlenopticSpec(mode="plenoptic_1", microlens_offset_mm=0.0)`.
**Next:** [3 — Plenoptic 2.0](03-plenoptic-2.md) moves the array off the image plane and
gets most of that resolution back.
