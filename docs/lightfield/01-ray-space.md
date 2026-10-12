# 1 — Ray space: what a light field actually is

**One idea:** a camera records a 2D image, but the thing arriving at the camera is 4D.
A light field is just "radiance, indexed by which ray you mean." Everything else —
refocusing, depth, plenoptic cameras — is bookkeeping on that index.

---

## Naming a ray

A ray in free space needs 4 numbers, not 2. The trick is to pick two reference planes
and record where the ray crosses each. In a camera the natural choice is the **lens
plane** and the **image plane**:

- \(u\) — where the ray crosses the main lens (which part of the aperture it used)
- \(s\) — where the ray crosses the reference image plane

The light field is \(L(u, s)\): the radiance of that one ray. In a real camera both are
2D, so \(L(u_x,u_y,s_x,s_y)\) is 4D. **Everything here collapses to one transverse axis**,
which makes \(L(u,s)\) a 2D array you can look at as an image. Nothing important is lost;
the second axis behaves identically.

The paraxial angle follows from the two positions, so \((u,s)\) and (position, angle) are
the same information in different clothes:

$$\theta = \frac{s - u}{v_0}$$

where \(v_0\) is the distance from lens to reference plane.

## What a photograph is

A conventional sensor pixel at \(s\) collects *every* ray that lands there, whatever part
of the aperture it came through. So a photograph is an **integral over \(u\)**:

$$I(s) = \int L(u, s)\, \mathrm{d}u$$

That integral is the whole problem. Once you've summed over \(u\) you cannot undo it.
A light-field camera's only job is to **keep \(u\) and \(s\) separate** instead of summing.

> This also explains the eternal photographic trade: stopping down shrinks the range of
> \(u\), which deepens focus and darkens the image. Same integral, narrower limits.

## A scene plane is a straight line

Here is the fact that makes ray space worth drawing. Take a flat textured surface whose
image forms at distance \(v\). Define

$$\beta = \frac{v_0}{v}$$

A point on that surface sends rays to the image plane at

$$s = \bar{x} + u\,(1-\beta)$$

so in the \((u,s)\) plane **that point is a straight line of slope \(1-\beta\)**:

| where the surface is | \(\beta\) | slope | appearance |
| --- | --- | --- | --- |
| exactly in focus | \(=1\) | \(0\) | vertical line — every aperture point agrees |
| nearer than focus | \(<1\) | \(>0\) | tilted one way |
| farther than focus | \(>1\) | \(<0\) | tilted the other way |

**Depth becomes slope.** A ray-space image of a real scene looks like a bundle of streaks,
one tilt per depth. Photographers call the tilt "defocus blur"; here it is just geometry
you can measure. In the sub-aperture view the same fact reads as disparity: between the two
edges of the aperture a layer shifts by \((1-\beta)\cdot 2A\) for semi-aperture \(A\).

```
  s                      s                      s
  ^   in focus           ^   near               ^   far
  |   |  |  |            |   /  /  /            |   \  \  \
  |   |  |  |            |  /  /  /             |    \  \  \
  +---------> u          +---------> u          +---------> u
```

## Refocusing is shear, then sum

If a photograph is a sum over \(u\) on the plane at \(v_0\), a photograph on some *other*
plane is a sum along a **tilted** path. With \(\alpha = v_0/v\):

$$I_\alpha(x) = \int L\big(u,\; \alpha x + u(1-\alpha)\big)\,\mathrm{d}u$$

Read it as two steps: **shear** ray space, then **project** it. Choosing \(\alpha\) chooses
which slope gets straightened up — and a straightened streak sums coherently into a sharp
edge, while every other slope smears.

**Setting \(\alpha = \beta\) brings that layer into focus.** Refocusing after the shutter
is not magic; it is choosing the summation path you postponed.

Running the sharpness metric over a region while sweeping \(\alpha\) recovers each layer's
distance. In `calculate_light_field` this is the `refocus.regions` block, and it is
genuinely accurate:

| layer | true distance | recovered |
| --- | --- | --- |
| near texture | 1050 mm | 1058 mm |
| focus target | 1300 mm | 1290 mm |
| far backdrop | 2600 mm | 2553 mm |

Note the error grows with distance. That is not sloppiness — see below.

One wrinkle worth knowing, because it bites every depth-from-focus method: an **occlusion
edge looks sharpest when the occluder is in focus**, not the background. Measuring the
backdrop's sharpness in a sliver next to a near object returns the near object's distance.
`calculate_light_field` therefore shrinks each region away from its borders by the widest
defocus blur before measuring, and reports `edge_limited` when nothing survives.

## The catch: your baseline is the aperture

Slope is measured across the aperture, so a light-field camera is a stereo rig whose
**baseline is the lens diameter**. Disparity scales as

$$1-\beta \;\propto\; \frac{1}{Z}$$

so depth error grows like \(Z^2\). A 12 mm aperture is a 12 mm baseline. This is exactly
why light-field depth is excellent at 30 cm and poor at 10 m, and why a structured-light
or stereo system with a 60 mm baseline beats it outright at range. A plenoptic camera buys
you *post-capture* flexibility, not precision at distance.

---

## Check yourself

1. A layer's ray-space streaks are vertical. Where is it?
2. You refocus with \(\alpha = 1.02\). Are you focusing nearer or farther than the reference plane?
3. Why can't you refocus a normal photograph, given that defocus is "just" a blur?
4. You double the aperture diameter. What happens to depth precision, and what happens to depth of field?

<details>
<summary>Answers</summary>

1. Exactly on the reference image plane — \(\beta=1\), every aperture point agrees.
2. \(\alpha=v_0/v>1\) means \(v<v_0\): the new image plane is closer to the lens, which is
   conjugate to an object **farther away**.
3. Because the sensor already performed \(\int \mathrm{d}u\). The blur is a sum of many
   \(u\)-contributions, and the individual terms are gone. Deconvolution guesses them back;
   a light field never discarded them.
4. Depth precision roughly doubles (longer baseline, bigger disparity); depth of field
   halves. Same knob, opposite directions.

</details>

---

**In OWL:** `LightFieldSpec`, `calculate_light_field`, `sample_radiance`, `layer_beta`.
**Notebook:** `notebooks/light_field_ray_space.py`.
**Next:** [2 — Plenoptic 1.0](02-plenoptic-1.md) builds a camera that keeps \(u\) and \(s\) apart.
