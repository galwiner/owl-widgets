// No project npm install needed:
// npm exec --yes --package=@playwright/test -- node --test tests/test_frontend.mjs
// First run, if needed: npm exec --yes --package=@playwright/test -- playwright install chromium
import { before, after, beforeEach, afterEach, test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { delimiter, resolve } from "node:path";

// npm exec exposes its ephemeral .bin on PATH, not Node's module search path.
function loadPlaywright() {
  for (const base of [
    import.meta.url,
    ...(process.env.PATH || "")
      .split(delimiter)
      .filter(Boolean)
      .map((bin) => resolve(bin, "..", "package.json")),
  ]) {
    try {
      return createRequire(base)("playwright");
    } catch (error) {
      if (error.code !== "MODULE_NOT_FOUND") throw error;
    }
  }
  throw new Error(
    "Run via npm exec --yes --package=@playwright/test -- node --test tests/test_frontend.mjs",
  );
}
const { chromium } = loadPlaywright();
const js = await readFile(
  new URL("../src/owl/static/bench.js", import.meta.url),
  "utf8",
);
const css = await readFile(
  new URL("../src/owl/static/bench.css", import.meta.url),
  "utf8",
);
let browser, page;
before(async () => {
  browser = await chromium.launch({ headless: true });
});
after(async () => {
  await browser?.close();
});
beforeEach(async () => {
  page = await browser.newPage({ viewport: { width: 900, height: 900 } });
  await page.setContent('<main><div id="a"></div><div id="b"></div></main>');
  await page.addStyleTag({ content: css });
  // AnyWidget loads ESM from a blob: exercise the default export with no base URL.
  await page.evaluate(async (source) => {
    const url = URL.createObjectURL(
      new Blob([source], { type: "text/javascript" }),
    );
    try {
      const module = await import(url);
      window.renderBench = module.default.render;
      window.mountCrossSection = module.mountCrossSection;
    } finally {
      URL.revokeObjectURL(url);
    }
  }, js);
  await page.waitForFunction(() => typeof window.renderBench === "function");
  await page.evaluate(() => {
    // A minimal AnyWidget model double; numerical traces are supplied fixtures,
    // not recalculated here. Python propagation has its own test suite.
    class Model {
      constructor() {
        this.state = {
          settings: {
            system: {
              schema_version: 1,
              elements: [
                { type: "free_space", distance_mm: 100 },
                { type: "thin_lens", focal_length_mm: 50 },
              ],
            },
            beam: { schema_version: 1, wavelength_nm: 550, waist_mm: 0.1 },
            ray_span_mm: 2,
            ray_count: 2,
          },
          result: {
            rays: {
              z_mm: [0, 100],
              y_mm: [
                [-2, 2],
                [-1, 1],
              ],
            },
            gaussian: { z_mm: [0, 100], radius_mm: [0.1, 0.2] },
            elements: [{ type: "thin_lens", z_mm: 100, label: "Lens" }],
            metrics: {
              length_mm: 100,
              output_radius_mm: 0.2,
              output_ray_half_span_mm: 1,
            },
          },
          error: "",
        };
        this.listeners = new Map();
        this.saves = 0;
      }
      get(key) {
        return this.state[key];
      }
      set(key, value) {
        this.state[key] = value;
        for (const fn of this.listeners.get(`change:${key}`) || []) fn();
      }
      on(event, fn) {
        if (!this.listeners.has(event)) this.listeners.set(event, new Set());
        this.listeners.get(event).add(fn);
      }
      off(event, fn) {
        this.listeners.get(event)?.delete(fn);
      }
      save_changes() {
        this.saves++;
      }
    }
    window.benches = ["a", "b"].map((id) => {
      const model = new Model();
      return {
        model,
        cleanup: window.renderBench({ model, el: document.getElementById(id) }),
      };
    });
  });
});
afterEach(async () => {
  await page?.close();
});
const first = () => page.locator("#a");
const field = (key) => first().locator(`[data-key="${key}"]`);
const state = () =>
  page.evaluate(() => ({
    settings: benches[0].model.get("settings"),
    saves: benches[0].model.saves,
  }));

// Use real browser pointer events: scrubbing must not invoke Python on every move.
test("paired sliders preview locally, commit on release, and keep focus", async () => {
  for (const [key, min, max, unit, property] of [
    ["wavelength", "200", "2000", "nm", "wavelength_nm"],
    ["waist", "0.01", "1", "mm", "waist_mm"],
  ]) {
    const slider = field(`${key}-slider`);
    assert.equal(await slider.getAttribute("min"), min);
    assert.equal(await slider.getAttribute("max"), max);
    const before = await state();
    const box = await slider.boundingBox();
    await page.mouse.move(box.x + box.width * 0.3, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.7, box.y + box.height / 2, {
      steps: 5,
    });
    const preview = await slider.inputValue();
    assert.equal((await state()).saves, before.saves);
    assert.equal(
      (await state()).settings.beam[property],
      before.settings.beam[property],
    );
    const formatted = Number(preview).toFixed(key === "wavelength" ? 0 : 3);
    assert.equal(await field(key).inputValue(), formatted);
    assert.equal(
      await slider.locator("..").locator("output").textContent(),
      `${formatted} ${unit}`,
    );
    await page.mouse.up();
    assert.equal((await state()).saves, before.saves + 1);
    assert.equal((await state()).settings.beam[property], Number(preview));
    assert.equal(
      await field(`${key}-slider`).evaluate(
        (el) => document.activeElement === el,
      ),
      true,
    );
  }
});

test("sliders support keyboard changes with focus preserved after redraw", async () => {
  for (const [key, property, step] of [
    ["wavelength", "wavelength_nm", 1],
    ["waist", "waist_mm", 0.001],
  ]) {
    const before = await state();
    await field(`${key}-slider`).focus();
    await field(`${key}-slider`).press("ArrowRight");
    const after = await state();
    assert.ok(
      Math.abs(
        after.settings.beam[property] - before.settings.beam[property] - step,
      ) < 1e-12,
    );
    assert.equal(after.saves, before.saves + 1);
    assert.equal(
      await field(`${key}-slider`).evaluate(
        (el) => el === document.activeElement,
      ),
      true,
    );
    assert.equal(
      Number(await field(key).inputValue()),
      after.settings.beam[property],
    );
  }
});

test("typed numbers and readouts round to nanometres and microns", async () => {
  for (const [key, value, bound, limit, thumb] of [
    ["wavelength", "2500.25", "max", "2500", "2500"],
    ["wavelength", "100.125", "min", "100", "100"],
    ["waist", "0.0054", "min", "0.005", "0.005"],
    ["waist", "2.2506", "max", "2.251", "2.251"],
  ]) {
    await field(key).fill(value);
    await field(key).press("Tab");
    assert.equal(await field(`${key}-slider`).getAttribute(bound), limit);
    assert.equal(await field(`${key}-slider`).inputValue(), thumb);
    const formatted = Number(value).toFixed(key === "wavelength" ? 0 : 3);
    assert.equal(await field(key).inputValue(), formatted);
    assert.equal(
      await field(`${key}-slider`)
        .locator("..")
        .locator("output")
        .textContent(),
      `${formatted} ${key === "wavelength" ? "nm" : "mm"}`,
    );
    const property = key === "wavelength" ? "wavelength_nm" : "waist_mm";
    assert.equal((await state()).settings.beam[property], Number(formatted));
    await field(`${key}-slider`).press("ArrowRight");
    const increment = key === "wavelength" ? 1 : 0.001;
    const updated = (await state()).settings.beam[property];
    assert.ok(
      Math.abs(updated / increment - Math.round(updated / increment)) < 1e-9,
    );
  }
});

test("backend reset and rollback refresh numeric fields, sliders and errors", async () => {
  await field("wavelength").fill("");
  await field("wavelength").press("Tab");
  assert.equal((await state()).saves, 0);
  assert.equal(await field("wavelength").getAttribute("aria-invalid"), "true");
  assert.match(await first().locator('[role="alert"]').textContent(), /finite/);
  await page.evaluate(() => {
    const model = benches[0].model;
    const reset = structuredClone(model.get("settings"));
    reset.beam.wavelength_nm = 780;
    reset.beam.waist_mm = 0.25;
    model.set("settings", reset);
  });
  assert.equal(await first().locator('[role="alert"]').isVisible(), false);
  assert.equal(await field("wavelength-slider").inputValue(), "780");
  assert.equal(await field("waist-slider").inputValue(), "0.25");
  // Simulate the Python validator returning the last valid settings and error.
  await field("waist").fill("0");
  await field("waist").press("Tab");
  await page.evaluate(() => {
    const model = benches[0].model;
    const valid = structuredClone(model.get("settings"));
    valid.beam.waist_mm = 0.25;
    model.set("settings", valid);
    model.set("error", "waist_mm must be positive");
  });
  assert.equal(await field("waist").inputValue(), "0.250");
  assert.equal(await field("waist-slider").inputValue(), "0.25");
  assert.match(
    await first().locator('[role="alert"]').textContent(),
    /must be positive/,
  );
  await page.evaluate(() => benches[0].model.set("error", ""));
  assert.equal(await first().locator('[role="alert"]').isVisible(), false);
});

test("reflected ray segments change color and arrows follow travel through repeated mirrors", async () => {
  await page.evaluate(() => {
    const model = benches[0].model;
    const result = structuredClone(model.get("result"));
    result.rays = {
      z_mm: [0, 100, 100, -40, -40, 60],
      y_mm: [[0], [1], [1], [-1], [-1], [0]],
    };
    model.set("result", result);
  });
  const rays = first().locator(".owl-bench-ray");
  assert.equal(await rays.count(), 3);
  assert.deepEqual(
    await rays.evaluateAll((nodes) => nodes.map((n) => n.dataset.direction)),
    ["right", "left", "right"],
  );
  const colors = await rays.evaluateAll((nodes) =>
    nodes.map((n) => getComputedStyle(n).stroke),
  );
  assert.equal(colors[0], colors[2]);
  assert.notEqual(colors[0], colors[1]);
  const arrows = first().locator(".owl-bench-ray-arrow");
  assert.equal(await arrows.count(), 3);
  for (const arrow of await arrows.all()) {
    const values = await arrow.evaluate((n) => {
      const p = n
        .getAttribute("d")
        .match(/-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/gi)
        .map(Number);
      return {
        direction: n.dataset.direction,
        delta: p[2] - (p[0] + p[4]) / 2,
      };
    });
    assert.equal(values.delta > 0, values.direction === "right");
  }
  assert.match(
    await first().locator(".owl-bench-return-key").textContent(),
    /left/,
  );
  await first()
    .getByRole("combobox", { name: "Trace view" })
    .selectOption("gaussian");
  assert.equal(await arrows.count(), 0);
  assert.equal(await first().locator(".owl-bench-return-key").count(), 0);
});

test("trace views use visible-trace extents and accurate legends without syncing", async () => {
  const select = first().getByRole("combobox", { name: "Trace view" });
  const ticks = () => first().locator('svg text[x="58"]').allTextContents();
  assert.equal(await first().locator(".owl-bench-ray").count(), 2);
  assert.equal(await first().locator(".owl-bench-beam").count(), 2);
  assert.deepEqual(await ticks(), ["-2", "0", "2"]);
  await select.selectOption("gaussian");
  assert.equal(await first().locator(".owl-bench-ray").count(), 0);
  assert.equal(await first().locator(".owl-bench-beam").count(), 2);
  assert.deepEqual(await ticks(), ["-0.2", "0", "0.2"]);
  assert.equal(await first().locator(".owl-bench-ray-key").count(), 0);
  assert.match(
    await first().locator(".owl-bench-legend").textContent(),
    /intensity 1\/e² radius/,
  );
  assert.match(
    await first().locator("svg").getAttribute("aria-label"),
    /Gaussian/,
  );
  await select.selectOption("rays");
  assert.equal(await first().locator(".owl-bench-beam").count(), 0);
  assert.equal(await first().locator(".owl-bench-beam-key").count(), 0);
  assert.deepEqual(await ticks(), ["-2", "0", "2"]);
  await page.evaluate(() => {
    const model = benches[0].model;
    const result = structuredClone(model.get("result"));
    result.rays.y_mm = [
      [-4, 4],
      [-2, 2],
    ];
    model.set("result", result);
    model.set("settings", structuredClone(model.get("settings")));
  });
  assert.equal(await select.inputValue(), "rays");
  assert.deepEqual(await ticks(), ["-4", "0", "4"]);
  await select.selectOption("both");
  assert.equal(await first().locator(".owl-bench-beam").count(), 2);
  assert.equal((await state()).saves, 0);
});

test("instances and views are independent; cleanup unregisters and remounts", async () => {
  await first()
    .getByRole("combobox", { name: "Trace view" })
    .selectOption("gaussian");
  await field("wavelength").fill("900");
  await field("wavelength").press("Tab");
  assert.equal(
    await page.locator('#b [data-key="wavelength"]').inputValue(),
    "550",
  );
  assert.equal(
    await page.locator('#b select[aria-label="Trace view"]').inputValue(),
    "both",
  );
  await page.evaluate(() => {
    // Two notebook views may also share a single model.
    const host = document.createElement("div");
    host.id = "shared";
    document.body.append(host);
    window.sharedCleanup = window.renderBench({
      model: benches[0].model,
      el: host,
    });
  });
  assert.equal(
    await page.locator('#shared select[aria-label="Trace view"]').inputValue(),
    "both",
  );
  await page.evaluate(() => benches[0].cleanup());
  assert.equal(await first().locator(".owl-bench").count(), 0);
  assert.deepEqual(
    await page.evaluate(() =>
      [...benches[0].model.listeners.values()].map((set) => set.size),
    ),
    [1, 1, 1],
  );
  await page.evaluate(() => {
    sharedCleanup();
    benches[0].model.set("error", "After disposal");
  });
  assert.deepEqual(
    await page.evaluate(() =>
      [...benches[0].model.listeners.values()].map((set) => set.size),
    ),
    [0, 0, 0],
  );
  await page.evaluate(() => {
    benches[0].cleanup = window.renderBench({
      model: benches[0].model,
      el: document.getElementById("a"),
    });
  });
  assert.equal(
    await first().getByRole("combobox", { name: "Trace view" }).inputValue(),
    "both",
  );
  assert.equal(await field("wavelength-slider").inputValue(), "900");
});

test("new element buttons, accessible parameters and Flat controls round-trip", async () => {
  const add = async (name) =>
    first().getByRole("button", { name, exact: true }).click();
  await add("+ Thin lens");
  await add("+ Mirror");
  await add("+ Interface");
  await add("+ Interface");
  await add("+ Thick lens");
  await add("+ Interface");
  assert.deepEqual((await state()).settings.system.elements.slice(2), [
    { type: "thin_lens", focal_length_mm: 100 },
    { type: "mirror", radius_mm: 100 },
    { type: "interface", radius_mm: 100, n1: 1, n2: 1.5 },
    { type: "interface", radius_mm: 100, n1: 1.5, n2: 1 },
    {
      type: "thick_lens",
      radius1_mm: 60,
      radius2_mm: -60,
      thickness_mm: 10,
      n: 1.5,
    },
    { type: "interface", radius_mm: 100, n1: 1, n2: 1.5 },
  ]);
  for (const [index, label, key, value] of [
    [3, "Radius (mm)", "radius_mm", "-125"],
    [4, "Radius (mm)", "radius_mm", "-80"],
    [4, "Incident refractive index (n1)", "n1", "1.2"],
    [4, "Exit refractive index (n2)", "n2", "1.7"],
    [6, "Entry radius (mm)", "radius1_mm", "70"],
    [6, "Exit radius (mm)", "radius2_mm", "-75"],
    [6, "Thickness (mm)", "thickness_mm", "0"],
    [6, "Lens refractive index (n)", "n", "1.6"],
  ]) {
    const input = first()
      .locator(".owl-bench-element")
      .nth(index)
      .getByRole("spinbutton", { name: label, exact: true });
    await input.fill(value);
    await input.press("Tab");
    assert.equal(
      (await state()).settings.system.elements[index][key],
      Number(value),
    );
  }
  for (const [index, key] of [
    [3, "radius_mm"],
    [4, "radius_mm"],
    [6, "radius1_mm"],
    [6, "radius2_mm"],
  ]) {
    const flat = field(`element-${index}-${key}-flat`);
    await flat.check();
    assert.equal((await state()).settings.system.elements[index][key], null);
    assert.equal(await field(`element-${index}-${key}`).isDisabled(), true);
  }
  await page.evaluate(() => {
    const model = benches[0].model;
    model.set("settings", JSON.parse(JSON.stringify(model.get("settings"))));
  });
  assert.equal(await field("element-6-radius2_mm-flat").isChecked(), true);
  await field("element-6-radius2_mm-flat").uncheck();
  assert.equal(await field("element-6-radius2_mm").isEnabled(), true);
  assert.equal((await state()).settings.system.elements[6].radius2_mm, 100);
  await page.setViewportSize({ width: 320, height: 900 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  assert.match(
    await first().locator(".owl-bench-header").textContent(),
    /input in air · M²=1/,
  );
  assert.match(
    await first().locator(".owl-bench-toolbar").textContent(),
    /mirror-return elements explicitly/,
  );
});

test("interface defaults scan the final medium; server rejects non-air thick lenses and zero radii", async () => {
  await first()
    .getByRole("button", { name: "+ Interface", exact: true })
    .click();
  await field("element-2-n2").fill("1.8");
  await field("element-2-n2").press("Tab");
  await first().getByRole("button", { name: "+ Gap", exact: true }).click();
  await first().getByRole("button", { name: "+ Mirror", exact: true }).click();
  const valid = (await state()).settings;
  await first()
    .getByRole("button", { name: "+ Thick lens", exact: true })
    .click();
  assert.equal(
    (await state()).settings.system.elements.at(-1).type,
    "thick_lens",
  );
  // Emulate the backend's rejected-edit rollback, without implementing physics here.
  await page.evaluate((settings) => {
    benches[0].model.set("settings", settings);
    benches[0].model.set("error", "thick_lens requires air on both sides");
  }, valid);
  assert.match(await first().getByRole("alert").textContent(), /requires air/);
  assert.equal(
    await first()
      .getByRole("group", { name: /Thick lens/ })
      .count(),
    0,
  );
  await page.evaluate(() => benches[0].model.set("error", ""));
  await first()
    .getByRole("button", { name: "+ Interface", exact: true })
    .click();
  assert.deepEqual((await state()).settings.system.elements.at(-1), {
    type: "interface",
    radius_mm: 100,
    n1: 1.8,
    n2: 1,
  });
  await field("element-4-radius_mm").fill("0");
  await field("element-4-radius_mm").press("Tab");
  assert.equal((await state()).settings.system.elements[4].radius_mm, 0);
  await page.evaluate(() => {
    const model = benches[0].model;
    const settings = structuredClone(model.get("settings"));
    settings.system.elements[4].radius_mm = 100;
    model.set("settings", settings);
    model.set("error", "radius_mm must be nonzero or null (flat)");
  });
  assert.equal(await field("element-4-radius_mm").inputValue(), "100");
  assert.match(await first().getByRole("alert").textContent(), /nonzero/);
  const before = (await state()).saves;
  await field("element-5-n2").fill("-1");
  await field("element-5-n2").press("Tab");
  assert.equal((await state()).saves, before);
  assert.equal(
    await field("element-5-n2").getAttribute("aria-invalid"),
    "true",
  );
});

test("backend thick and reversed traces fit all coordinates and retain view flags", async () => {
  await page.evaluate(() =>
    benches[0].model.set("result", {
      rays: {
        z_mm: [0, 100, 100, 90, 90, -50, -20],
        y_mm: [
          [-2, 2],
          [-1, 1],
          [-1, 1],
          [-0.8, 0.8],
          [-0.8, 0.8],
          [-1, 1],
          [-1.2, 1.2],
        ],
      },
      gaussian: {
        z_mm: [0, 120, 100, 90, -80, -20],
        radius_mm: [0.1, 0.2, 0.2, 0.3, 0.4, 0.3],
      },
      elements: [
        {
          type: "mirror",
          start_z_mm: 100,
          z_mm: 100,
          radius_mm: 100,
          label: "Return mirror",
        },
        {
          type: "thick_lens",
          start_z_mm: 100,
          z_mm: 90,
          radius1_mm: 60,
          radius2_mm: -60,
          thickness_mm: 10,
          n: 1.5,
          label: "Return thick lens",
        },
        {
          type: "interface",
          start_z_mm: -50,
          z_mm: -50,
          radius_mm: null,
          n1: 1,
          n2: 1.5,
          label: "Flat interface",
        },
      ],
      metrics: {
        length_mm: -20,
        output_radius_mm: 0.3,
        output_ray_half_span_mm: 1.2,
      },
    }),
  );
  const ticks = () => first().locator('svg text[y="282"]').allTextContents();
  assert.deepEqual(await ticks(), ["-80", "-30", "20", "70", "120"]);
  const rect = first().locator("rect.owl-bench-thick-lens");
  assert.ok(
    Math.abs(Number(await rect.getAttribute("x")) - (66 + (170 / 200) * 634)) <
      1e-9,
  );
  assert.ok(
    Math.abs(Number(await rect.getAttribute("width")) - (10 / 200) * 634) <
      1e-9,
  );
  assert.equal(await rect.locator("title").textContent(), "Return thick lens");
  assert.equal(
    await first().locator(".owl-bench-mirror title").textContent(),
    "Return mirror",
  );
  assert.equal(
    await first().locator(".owl-bench-interface title").textContent(),
    "Flat interface",
  );
  assert.notEqual(
    await first()
      .locator(".owl-bench-mirror")
      .evaluate((el) => getComputedStyle(el).strokeDasharray),
    await first()
      .locator(".owl-bench-interface")
      .evaluate((el) => getComputedStyle(el).strokeDasharray),
  );
  const paths = await first()
    .locator(".owl-bench-ray")
    .evaluateAll((nodes) => nodes.map((n) => n.getAttribute("d")));
  assert.equal(paths.length, 8);
  const segments = paths.map((path) =>
    [...path.matchAll(/[ML]([^,]+),/g)].map((match) => Number(match[1])),
  );
  assert.deepEqual(
    segments.slice(0, 4).map(([a, b]) => b > a),
    [true, false, false, true],
  );
  assert.ok(segments.flat().every((x) => x >= 66 && x <= 700));
  for (const view of ["rays", "gaussian", "both"]) {
    await first()
      .getByRole("combobox", { name: "Trace view" })
      .selectOption(view);
    await page.evaluate(() => {
      const model = benches[0].model;
      model.set("result", structuredClone(model.get("result")));
    });
    assert.deepEqual(await ticks(), ["-80", "-30", "20", "70", "120"]);
    assert.equal(
      await first().locator(".owl-bench-ray").count(),
      view === "gaussian" ? 0 : 8,
    );
    assert.equal(
      await first().locator(".owl-bench-beam").count(),
      view === "rays" ? 0 : 2,
    );
    assert.equal(await rect.count(), 1);
  }
  assert.equal((await state()).saves, 0);
});

test("empty and single-plane results have finite bounds; tiny metrics retain precision", async () => {
  for (const empty of [true, false]) {
    await page.evaluate(
      (empty) =>
        benches[0].model.set("result", {
          rays: { z_mm: empty ? [] : [0], y_mm: empty ? [] : [[0]] },
          gaussian: { z_mm: empty ? [] : [0], radius_mm: empty ? [] : [1e-8] },
          elements: [],
          metrics: {
            length_mm: 0,
            output_radius_mm: 1e-8,
            output_ray_half_span_mm: 0,
          },
        }),
      empty,
    );
    assert.deepEqual(
      await first().locator('svg text[y="282"]').allTextContents(),
      ["-0.5", "-0.25", "0", "0.25", "0.5"],
    );
    assert.doesNotMatch(
      await first().locator("svg").innerHTML(),
      /NaN|Infinity/,
    );
    assert.match(
      await first().locator(".owl-bench-metrics").textContent(),
      /1e-8/,
    );
  }
});

test("sequence edits and narrow layouts retain usable controls", async () => {
  await page.setViewportSize({ width: 320, height: 900 });
  await first().getByRole("button", { name: "+ Gap", exact: true }).click();
  assert.equal((await state()).settings.system.elements.length, 3);
  await first()
    .getByRole("button", { name: "Remove element 3", exact: true })
    .click();
  assert.equal((await state()).settings.system.elements.length, 2);
  assert.equal(
    await field("element-1").evaluate((el) => el === document.activeElement),
    true,
  );
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  for (const key of ["waist-slider", "wavelength-slider"]) {
    const box = await field(key).boundingBox();
    assert.ok(box.width >= 80);
    assert.ok(box.x >= 0 && box.x + box.width <= 320);
  }
});

test("FFT controls default legacy settings and sync canonical wave settings to linked views", async () => {
  const original = await state();
  assert.equal(original.settings.wave, undefined);
  const grid = first().getByRole("combobox", { name: "FFT grid", exact: true });
  assert.equal(await grid.inputValue(), "128");
  assert.deepEqual(
    await grid
      .locator("option")
      .evaluateAll((options) => options.map((option) => option.value)),
    ["64", "128", "256", "512"],
  );
  assert.equal(await field("wave-window-auto").isChecked(), true);
  assert.equal(await field("wave-window").isDisabled(), true);
  assert.equal((await state()).saves, 0);
  await page.evaluate(() => {
    const host = document.createElement("div");
    host.id = "linked";
    document.body.append(host);
    window.linkedCleanup = renderBench({ model: benches[0].model, el: host });
  });
  await grid.focus();
  await grid.selectOption("256");
  assert.equal(
    await grid.evaluate((el) => el === document.activeElement),
    true,
  );
  assert.deepEqual((await state()).settings, {
    ...original.settings,
    wave: { grid_size: 256, window_mm: null },
  });
  assert.equal((await state()).saves, 1);
  assert.equal(
    await page.locator('#linked [data-key="wave-grid"]').inputValue(),
    "256",
  );
  assert.equal(
    await page.locator('#b [data-key="wave-grid"]').inputValue(),
    "128",
  );
  for (const value of ["64", "512", "128"]) {
    await grid.selectOption(value);
    assert.equal((await state()).settings.wave.grid_size, Number(value));
  }
  await page.evaluate(() => {
    const model = benches[0].model;
    model.set("settings", {
      ...model.get("settings"),
      wave: { grid_size: 64, window_mm: 2.5 },
    });
  });
  assert.equal(await grid.inputValue(), "64");
  assert.equal(await field("wave-window").inputValue(), "2.5");
  assert.equal(await field("wave-window-auto").isChecked(), false);
  assert.equal(
    await page.locator('#linked [data-key="wave-window"]').inputValue(),
    "2.5",
  );
  await page.evaluate(() => linkedCleanup());
});

test("FFT window Auto and positive manual values commit once and reject invalid edits", async () => {
  await setSections(crossSections());
  const auto = field("wave-window-auto");
  const windowInput = first().getByRole("spinbutton", {
    name: "FFT window (mm)",
    exact: true,
  });
  await auto.focus();
  await auto.press("Space");
  assert.equal(
    await auto.evaluate((el) => el === document.activeElement),
    true,
  );
  assert.equal(await windowInput.isEnabled(), true);
  assert.equal(await windowInput.inputValue(), "3");
  assert.deepEqual((await state()).settings.wave, {
    grid_size: 128,
    window_mm: 3,
  });
  assert.equal((await state()).saves, 1);
  await windowInput.fill("0.00001");
  await windowInput.press("Tab");
  assert.deepEqual((await state()).settings.wave, {
    grid_size: 128,
    window_mm: 0.00001,
  });
  const saved = await state();
  for (const invalid of ["0", "-1", ""]) {
    await windowInput.fill(invalid);
    await windowInput.press("Tab");
    assert.deepEqual(await state(), saved);
    assert.equal(await windowInput.getAttribute("aria-invalid"), "true");
    assert.match(
      await first().locator(".owl-bench-error").textContent(),
      /finite positive number/,
    );
  }
  await windowInput.fill("4.25");
  await windowInput.press("Tab");
  assert.equal(await windowInput.getAttribute("aria-invalid"), null);
  assert.equal(await first().locator(".owl-bench-error").isHidden(), true);
  await field("wave-grid").selectOption("512");
  assert.deepEqual((await state()).settings.wave, {
    grid_size: 512,
    window_mm: 4.25,
  });
  await auto.check();
  assert.deepEqual((await state()).settings.wave, {
    grid_size: 512,
    window_mm: null,
  });
  assert.equal(await windowInput.isDisabled(), true);
  await page.setViewportSize({ width: 320, height: 900 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  for (const key of ["wave-grid", "wave-window", "wave-window-auto"]) {
    const box = await field(key).boundingBox();
    assert.ok(box.width > 0 && box.x >= 0 && box.x + box.width <= 320);
  }
});

test("FFT manual fallback works without cross sections and backend reset clears edits", async () => {
  await field("wave-window-auto").uncheck();
  assert.deepEqual((await state()).settings.wave, {
    grid_size: 128,
    window_mm: 1,
  });
  await field("wave-window").fill("0");
  await field("wave-window").press("Tab");
  await page.evaluate(() => {
    const model = benches[0].model;
    model.set("settings", {
      ...model.get("settings"),
      wave: { grid_size: 128, window_mm: null },
    });
  });
  assert.equal(await field("wave-window").isDisabled(), true);
  assert.equal(await field("wave-window").getAttribute("aria-invalid"), null);
  assert.equal(await field("wave-window-auto").isChecked(), true);
  assert.equal(await first().locator(".owl-bench-error").isHidden(), true);
  assert.equal((await state()).saves, 1);
});

const crossSections = () => ({
  x_mm: [-1, 0, 1],
  window_mm: 3,
  planes: [
    {
      label: "Input",
      z_mm: 0,
      intensity: [
        [0, 0, 0],
        [0.2, 1, 0.4],
        [0, 0.8, 0],
      ],
      transmission: 1,
    },
    {
      label: "After aperture",
      z_mm: 10,
      intensity: [
        [0, 0, 0],
        [0, 0.25, 0],
        [0, 0, 0],
      ],
      transmission: 0.125,
    },
    {
      label: "Return",
      z_mm: -10,
      intensity: [
        [0, 0, 0],
        [0, 2, 0],
        [0, 0, 0],
      ],
      transmission: 0.125,
    },
  ],
  warnings: [
    "Finite window: increase window_mm.",
    "Sampling: aperture spans few pixels.",
  ],
});
const setSections = (data) =>
  page.evaluate((cross_sections) => {
    const model = benches[0].model;
    model.set("result", { ...model.get("result"), cross_sections });
  }, data);

test("apertures edit and reorder every element with keyboard focus and bounds", async () => {
  await first()
    .getByRole("button", { name: "+ Aperture", exact: true })
    .click();
  assert.deepEqual((await state()).settings.system.elements[2], {
    type: "aperture",
    radius_mm: 0.1,
    x_mm: 0,
    y_mm: 0,
  });
  for (const [key, value] of [
    ["radius_mm", "0.2"],
    ["x_mm", "-0.12"],
    ["y_mm", "0.03"],
  ]) {
    await field(`element-2-${key}`).fill(value);
    await field(`element-2-${key}`).press("Tab");
  }
  assert.equal(
    await first()
      .getByRole("button", { name: "Move element 1 up", exact: true })
      .isDisabled(),
    true,
  );
  assert.equal(
    await first()
      .getByRole("button", { name: "Move element 3 down", exact: true })
      .isDisabled(),
    true,
  );
  const up = first().getByRole("button", {
    name: "Move element 3 up",
    exact: true,
  });
  await up.focus();
  await up.press("Enter");
  assert.deepEqual(
    (await state()).settings.system.elements.map((item) => item.type),
    ["free_space", "aperture", "thin_lens"],
  );
  assert.equal(
    await first()
      .getByRole("button", { name: "Move element 2 up", exact: true })
      .evaluate((el) => el === document.activeElement),
    true,
  );
  await page.keyboard.press("Enter");
  assert.equal(
    await field("element-0-radius_mm").evaluate(
      (el) => el === document.activeElement,
    ),
    true,
  );
  assert.deepEqual((await state()).settings.system.elements[0], {
    type: "aperture",
    radius_mm: 0.2,
    x_mm: -0.12,
    y_mm: 0.03,
  });
  await first()
    .getByRole("button", { name: "Move element 2 down", exact: true })
    .click();
  assert.deepEqual(
    (await state()).settings.system.elements.map((item) => item.type),
    ["aperture", "thin_lens", "free_space"],
  );
});

test("clipped rays reach the stop, never continue, and dead samples do not expand extents", async () => {
  await page.evaluate(() => {
    const model = benches[0].model;
    const result = structuredClone(model.get("result"));
    result.rays = {
      z_mm: [0, 10, 10, -10],
      y_mm: [
        [0.5, 0],
        [0.5, 0],
        [999, 0],
        [999, 0],
      ],
      alive: [
        [true, true],
        [false, true],
        [false, true],
        [false, true],
      ],
    };
    result.elements = [
      {
        type: "aperture",
        z_mm: 10,
        radius_mm: 1,
        x_mm: 0.6,
        y_mm: 0.2,
        label: "Stop",
      },
    ];
    model.set("result", result);
  });
  await first()
    .getByRole("combobox", { name: "Trace view" })
    .selectOption("rays");
  const rays = first().locator(".owl-bench-ray");
  assert.equal(await rays.count(), 3);
  assert.equal(
    await first()
      .locator(".owl-bench-ray-return")

      .count(),
    2,
  ); // segment + arrow
  assert.deepEqual(
    await first().locator('svg text[x="58"]').allTextContents(),
    ["-1.2", "0", "1.2"],
  );
  const bars = await first()
    .locator(".owl-bench-aperture")
    .evaluateAll((els) =>
      els.map((el) => ({
        y: +el.getAttribute("y"),
        h: +el.getAttribute("height"),
      })),
    );
  assert.equal(bars.length, 2);
  assert.ok(bars[1].y > bars[0].y + bars[0].h);
  assert.ok(
    Math.abs(
      bars[1].y - (bars[0].y + bars[0].h) - ((1.6 / 1.2) * 236) / 2 / 1.12,
    ) < 1e-8,
  );
  await first()
    .getByRole("combobox", { name: "Trace view" })
    .selectOption("both");
  assert.match(
    await first().locator(".owl-bench-beam-key").textContent(),
    /Unclipped Gaussian reference/,
  );
  await page.evaluate(() => {
    const model = benches[0].model;
    const result = structuredClone(model.get("result"));
    result.elements[0].x_mm = 2;
    model.set("result", result);
  });
  assert.equal(
    await first()
      .locator(".owl-bench-aperture")
      .evaluateAll((els) =>
        els.reduce((total, el) => total + +el.getAttribute("height"), 0),
      ),
    236,
  );
});

test("longitudinal physical optics is the default, log-colored, and keeps Gaussian explicit", async () => {
  await page.evaluate(() => {
    const model = benches[0].model;
    const result = structuredClone(model.get("result"));
    result.elements = [
      {
        type: "aperture",
        z_mm: 10,
        radius_mm: 0.5,
        x_mm: 0,
        y_mm: 0,
        label: "Stop",
      },
    ];
    result.longitudinal = {
      z_mm: [0, 10, 10.1, 20],
      path_mm: [0, 10, 10.1, 20],
      x_mm: [-1, 0, 1],
      intensity: [
        [0.001, 1, 0.001],
        [0.001, 1, 0.001],
        [0, 0.2, 0],
        [0, 0.1, 0],
      ],
      elements: [],
      window_mm: 2,
      warnings: ["Sampling: aperture spans few pixels."],
    };
    model.set("result", result);
  });
  const select = first().getByRole("combobox", { name: "Trace view" });
  assert.equal(await select.inputValue(), "physical-rays");
  assert.deepEqual(await select.locator("option").allTextContents(), [
    "Physical optics",
    "Rays + physical optics",
    "Rays",
    "Unclipped Gaussian reference",
  ]);
  const image = first().locator("image.owl-bench-pop");
  assert.equal(await image.count(), 1);
  assert.match(await image.getAttribute("href"), /^data:image\/png;base64,/);
  assert.equal(await first().locator("path.owl-bench-beam").count(), 0);
  assert.match(
    await first().locator(".owl-bench-pop-key").textContent(),
    /Physical optics \|U\|² \/ input peak · log scale/,
  );
  assert.match(
    await first().locator("svg").textContent(),
    /x \(mm\).*z \(mm\)/s,
  );
  const brightPixel = await image.evaluate(async (element) => {
    const bitmap = new Image();
    bitmap.src = element.getAttribute("href");
    await bitmap.decode();
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d");
    context.drawImage(bitmap, 0, 0);
    return Array.from(
      context.getImageData(Math.floor(bitmap.width / 4), 1, 1, 1).data,
    );
  });
  assert.ok(brightPixel[0] > brightPixel[1] && brightPixel[0] > 150);
  await select.selectOption("gaussian-reference");
  assert.equal(await first().locator("image.owl-bench-pop").count(), 0);
  assert.equal(await first().locator("path.owl-bench-beam").count(), 2);
  assert.match(
    await first().locator(".owl-bench-beam-key").textContent(),
    /Unclipped Gaussian reference/,
  );
});

test("cross-section pixels and center slices retain input normalization and plane selection", async () => {
  await setSections(crossSections());
  const panel = first().locator(".owl-cross-section");
  const select = panel.getByRole("combobox", { name: "Cross-section plane" });
  const pixel = (x, y) =>
    panel
      .locator("canvas")
      .evaluate(
        (el, [x, y]) =>
          Array.from(el.getContext("2d").getImageData(x, y, 1, 1).data),
        [x, y],
      );
  assert.deepEqual(await pixel(1, 1), [255, 205, 80, 255]);
  assert.deepEqual(await pixel(1, 0), [204, 164, 64, 255]); // positive y is up
  const inputPath = await panel
    .locator(".owl-cross-section-slice")
    .getAttribute("d");
  assert.match(inputPath, /L196,116/); // 1 on a shared 0–2 axis
  await select.focus();
  await select.selectOption("1");
  assert.equal(await select.inputValue(), "1");
  assert.deepEqual(await pixel(1, 1), [64, 51, 20, 255]);
  assert.match(await panel.locator("output").textContent(), /12.5%/);
  assert.match(
    await panel.locator(".owl-cross-section-slice").getAttribute("d"),
    /L196,180.5/,
  );
  assert.equal(await panel.locator("li").count(), 2);
  assert.match(await panel.locator("figcaption").textContent(), /x \(mm\)/);
  assert.match(
    await panel.locator(".owl-cross-section-y-axis").textContent(),
    /y \(mm\)/,
  );
  await setSections(crossSections());
  assert.equal(await select.inputValue(), "1");
  assert.equal(
    await select.evaluate((el) => el === document.activeElement),
    true,
  );
  assert.equal((await state()).saves, 0);
  assert.equal(await page.locator("#b .owl-cross-section canvas").count(), 0);
  await select.selectOption("2");
  assert.deepEqual(await pixel(1, 1), [255, 205, 80, 255]);
  const smaller = crossSections();
  smaller.planes.pop();
  smaller.warnings = [];
  await setSections(smaller);
  assert.equal(await select.inputValue(), "1");
  assert.equal(await panel.locator("li").count(), 0);
  await page.setViewportSize({ width: 320, height: 900 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await setSections({
    planes: [],
    x_mm: [],
    window_mm: 3,
    warnings: ["No planes"],
  });
  assert.equal(await panel.locator("canvas").count(), 0);
  assert.equal(await panel.locator(".owl-bench-empty").isVisible(), true);
});

test("standalone uses result directly and shared mount disposes independently", async () => {
  await page.evaluate((data) => {
    benches[0].cleanup();
    const model = benches[0].model;
    model.set("view_kind", "cross_section");
    model.set("result", data);
    benches[0].cleanup = renderBench({
      model,
      el: document.getElementById("a"),
    });
    window.direct = mountCrossSection(document.getElementById("b"));
    direct.update(data);
  }, crossSections());
  assert.equal(await first().locator(".owl-bench-controls").count(), 0);
  assert.equal(await first().locator("canvas").count(), 1);
  await first().getByRole("combobox").selectOption("1");
  const data = crossSections();
  data.planes[1].transmission = 0;
  data.planes[1].intensity = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ];
  await page.evaluate((data) => benches[0].model.set("result", data), data);
  assert.match(await first().locator("output").textContent(), /0.0%/);
  assert.equal(await first().getByRole("combobox").inputValue(), "1");
  assert.equal(
    await page.locator("#b .owl-cross-section select").inputValue(),
    "0",
  );
  await page.evaluate(() => {
    benches[0].cleanup();
    direct.destroy();
    direct.update({});
  });
  assert.equal(await first().locator("section").count(), 0);
  assert.equal(await page.locator("#b canvas").count(), 0);
  assert.deepEqual(
    await page.evaluate(() =>
      [...benches[0].model.listeners.values()].map((set) => set.size),
    ),
    [0, 0, 0],
  );
});
