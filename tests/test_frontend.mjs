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
const plotly = await readFile(
  new URL("../src/owl/static/plotly.min.js", import.meta.url),
  "utf8",
);
const plotlyViews = await readFile(
  new URL("../src/owl/static/plotly_views.js", import.meta.url),
  "utf8",
);
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
  await page.addScriptTag({ content: plotly });
  // AnyWidget loads ESM from a blob: exercise the default export with no base URL.
  await page.evaluate(
    async ([views, source]) => {
      const url = URL.createObjectURL(
        new Blob([views, "\n", source], { type: "text/javascript" }),
      );
      try {
        const module = await import(url);
        window.renderBench = module.default.render;
        window.mountCrossSection = module.mountCrossSection;
      } finally {
        URL.revokeObjectURL(url);
      }
    },
    [plotlyViews, js],
  );
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
    document.querySelectorAll(".owl-bench-drawer").forEach((drawer) => {
      drawer.open = true;
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
test("bench details are folded by default and keyboard-expandable", async () => {
  await page.evaluate(() => {
    benches[0].cleanup();
    benches[0].cleanup = window.renderBench({
      model: benches[0].model,
      el: document.getElementById("a"),
    });
  });
  const drawer = first().locator(".owl-bench-drawer");
  const summary = drawer.locator("summary");
  assert.equal(await drawer.getAttribute("open"), null);
  assert.equal(await first().locator(".owl-bench-plotly").isVisible(), true);
  assert.equal(await first().locator(".owl-bench-controls").isVisible(), false);
  await summary.focus();
  await summary.press("Enter");
  assert.equal(await drawer.getAttribute("open"), "");
  assert.equal(await first().locator(".owl-bench-controls").isVisible(), true);
});

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

test("Plotly separates forward and returning ray segments", async () => {
  await page.evaluate(() => {
    const model = benches[0].model;
    const result = structuredClone(model.get("result"));
    result.rays = {
      z_mm: [0, 100, 100, -40, -40, 60],
      y_mm: [[0], [1], [1], [-1], [-1], [0]],
    };
    model.set("result", result);
  });
  const graph = first().locator(".owl-bench-plotly");
  await page.waitForFunction(
    () => document.querySelector(".owl-bench-plotly")?.data?.length,
  );
  const traces = await graph.evaluate((el) =>
    el.data
      .filter((trace) => ["Rays", "Returning rays"].includes(trace.name))
      .map((trace) => ({
        name: trace.name,
        x: trace.x,
        color: trace.line.color,
      })),
  );
  assert.deepEqual(
    traces.map((trace) => trace.name),
    ["Rays", "Returning rays", "Rays"],
  );
  assert.deepEqual(
    traces.map((trace) => trace.x),
    [
      [0, 100],
      [100, -40],
      [-40, 60],
    ],
  );
  assert.equal(traces[0].color, traces[2].color);
  assert.notEqual(traces[0].color, traces[1].color);
  await first()
    .getByRole("combobox", { name: "Trace view" })
    .selectOption("gaussian");
  await page.waitForFunction(() =>
    [...document.querySelector(".owl-bench-plotly").data].every(
      (trace) => trace.name === "Unclipped Gaussian reference",
    ),
  );
});

test("trace views choose expected Plotly traces without syncing settings", async () => {
  const select = first().getByRole("combobox", { name: "Trace view" });
  const graph = first().locator(".owl-bench-plotly");
  await page.waitForFunction(
    () => document.querySelector(".owl-bench-plotly")?.data?.length,
  );
  assert.equal(
    await graph.evaluate(
      (el) => el.data.filter((trace) => trace.name === "Rays").length,
    ),
    2,
  );
  assert.equal(
    await graph.evaluate(
      (el) =>
        el.data.filter((trace) => trace.name === "Unclipped Gaussian reference")
          .length,
    ),
    2,
  );
  await select.selectOption("gaussian");
  await page.waitForFunction(() =>
    [...document.querySelector(".owl-bench-plotly").data].every(
      (trace) => trace.name === "Unclipped Gaussian reference",
    ),
  );
  await select.selectOption("rays");
  await page.waitForFunction(() =>
    [...document.querySelector(".owl-bench-plotly").data].every(
      (trace) => trace.name === "Rays",
    ),
  );
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
  await page.waitForFunction(() =>
    document
      .querySelector(".owl-bench-plotly")
      .data.some((trace) => trace.y.includes(-4)),
  );
  assert.equal(await select.inputValue(), "rays");
  await select.selectOption("both");
  await page.waitForFunction(() =>
    document
      .querySelector(".owl-bench-plotly")
      .data.some((trace) => trace.name === "Unclipped Gaussian reference"),
  );
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
    [1, 2, 1],
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

test("Plotly represents thick elements and reverse ray segments in physical coordinates", async () => {
  const graph = first().locator(".owl-bench-plotly");
  await page.evaluate((result) => benches[0].model.set("result", result), {
    rays: { z_mm: [0, 20, 20, -30, -30], y_mm: [[0], [1], [1], [0.5], [0.5]] },
    gaussian: {
      z_mm: [0, 20, 20, -30, -30],
      radius_mm: [0.1, 0.2, 0.2, 0.3, 0.3],
    },
    elements: [
      {
        type: "thick_lens",
        start_z_mm: 20,
        z_mm: 30,
        radius1_mm: 60,
        radius2_mm: -60,
        thickness_mm: 10,
        n: 1.5,
        label: "Return thick lens",
      },
      {
        type: "mirror",
        start_z_mm: 30,
        z_mm: -30,
        radius_mm: null,
        label: "Return mirror",
      },
      {
        type: "interface",
        start_z_mm: -30,
        z_mm: -30,
        radius_mm: null,
        label: "Flat interface",
      },
    ],
    metrics: {
      length_mm: 10,
      output_radius_mm: 0.3,
      output_ray_half_span_mm: 1.2,
    },
  });
  await page.waitForFunction(
    () => document.querySelector(".owl-bench-plotly")?.data?.length,
  );
  const specs = await graph.evaluate((el) => ({
    data: el.data.map((trace) => ({ name: trace.name, x: trace.x })),
    shapes: el.layout.shapes,
  }));
  assert.ok(
    specs.data.some(
      (trace) => trace.name === "Returning rays" && trace.x[0] > trace.x[1],
    ),
  );
  assert.equal(specs.shapes.length, 3);
  assert.equal((await state()).saves, 0);
});

test("Plotly draws thin lenses with standard converging and diverging arrows", async () => {
  await page.evaluate(() => {
    const model = benches[0].model;
    const result = structuredClone(model.get("result"));
    result.elements = [
      { type: "thin_lens", z_mm: 20, focal_length_mm: 100 },
      { type: "thin_lens", z_mm: 40, focal_length_mm: -100 },
    ];
    model.set("result", result);
  });
  const graph = first().locator(".owl-bench-plotly");
  await page.waitForFunction(
    () =>
      document.querySelector(".owl-bench-plotly")?.layout?.annotations
        ?.length === 4,
  );
  const arrows = await graph.evaluate((el) =>
    el.layout.annotations.map(({ x, y, ay, arrowhead }) => ({
      x,
      y,
      ay,
      arrowhead,
    })),
  );
  assert.deepEqual(arrows, [
    { x: 20, y: 0, ay: 0.18, arrowhead: 2 },
    { x: 20, y: 1, ay: 0.82, arrowhead: 2 },
    { x: 40, y: 0.18, ay: 0, arrowhead: 2 },
    { x: 40, y: 0.82, ay: 1, arrowhead: 2 },
  ]);
});

test("empty and single-plane results are safe; tiny metrics retain precision", async () => {
  for (const empty of [true, false]) {
    await page.evaluate(
      (isEmpty) =>
        benches[0].model.set("result", {
          rays: { z_mm: isEmpty ? [] : [0], y_mm: isEmpty ? [] : [[0]] },
          gaussian: {
            z_mm: isEmpty ? [] : [0],
            radius_mm: isEmpty ? [] : [1e-8],
          },
          elements: [],
          metrics: {
            length_mm: 0,
            output_radius_mm: 1e-8,
            output_ray_half_span_mm: 0,
          },
        }),
      empty,
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

test("Plotly ray traces stop at blocked samples and display aperture shapes", async () => {
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
    result.gaussian.aperture_stop_index = 2;
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
  const graph = first().locator(".owl-bench-plotly");
  await page.waitForFunction(
    () => document.querySelector(".owl-bench-plotly")?.data?.length,
  );
  const data = await graph.evaluate((el) => ({
    traces: el.data.map((trace) => trace.x),
    shapes: el.layout.shapes,
    yRange: el._fullLayout.yaxis.range,
  }));
  assert.deepEqual(data.traces, [
    [0, 10],
    [0, 10],
    [10, -10],
  ]);
  assert.equal(data.shapes.length, 2);
  assert.ok(data.yRange.every((value) => Math.abs(value) < 10));
  assert.equal(data.traces.flat().includes(999), false);
});

test("Plotly longitudinal heatmap exposes local normalized intensity and Gaussian mode", async () => {
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
      z_mm: [0, 10, 20],
      x_mm: [-1, 0, 1],
      intensity: [
        [0.001, 1, 0.001],
        [0.001, 1, 0.001],
        [0, 0.2, 0],
      ],
      window_mm: 2,
    };
    model.set("result", result);
  });
  const select = first().getByRole("combobox", { name: "Trace view" });
  assert.equal(await select.inputValue(), "physical-rays");
  const graph = first().locator(".owl-bench-plotly");
  await page.waitForFunction(
    () => document.querySelector(".owl-bench-plotly")?.data?.length,
  );
  const heat = await graph.evaluate((el) =>
    el.data.find((trace) => trace.type === "heatmap"),
  );
  assert.deepEqual(heat.x, [0, 10, 20]);
  assert.deepEqual(heat.y, [-1, 0, 1]);
  assert.equal(heat.customdata[1][0], 1);
  assert.match(heat.hovertemplate, /input peak/);
  assert.equal(heat.z[0][0], -3);
  assert.deepEqual(heat.colorbar.ticktext, ["0.001", "0.01", "0.1", "1"]);
  assert.equal(heat.colorscale.at(-1)[1], "#fcffa4");
  await select.selectOption("gaussian-reference");
  await page.waitForFunction(
    () => document.querySelector(".owl-bench-plotly").data.length === 2,
  );
  assert.ok(
    await graph.evaluate((el) =>
      el.data.every((trace) => trace.name === "Unclipped Gaussian reference"),
    ),
  );
});

test("Plotly splits physical heatmaps at mirror reversals", async () => {
  await page.evaluate(() => {
    const model = benches[0].model;
    const result = structuredClone(model.get("result"));
    result.longitudinal = {
      z_mm: [0, 10, 20, 20, 10, 0],
      x_mm: [-1, 0, 1],
      intensity: [
        [0.1, 0.5, 0.1],
        [0.2, 0.6, 0.2],
        [0.3, 0.7, 0.3],
        [0.3, 0.7, 0.3],
        [0.2, 0.6, 0.2],
        [0.1, 0.5, 0.1],
      ],
    };
    model.set("result", result);
  });
  await first()
    .getByRole("combobox", { name: "Trace view" })
    .selectOption("physical");
  const graph = first().locator(".owl-bench-plotly");
  await page.waitForFunction(
    () => document.querySelector(".owl-bench-plotly")?.data?.length,
  );
  const segments = await graph.evaluate((el) =>
    el.data.filter((trace) => trace.type === "heatmap").map((trace) => trace.x),
  );
  assert.deepEqual(segments, [
    [0, 10, 20],
    [20, 10, 0],
  ]);
});

test("Plotly cross-section heatmap and center slice expose local intensities", async () => {
  await setSections(crossSections());
  const panel = first().locator(".owl-cross-section");
  const select = panel.getByRole("combobox", { name: "Cross-section plane" });
  const heat = panel.locator(".owl-cross-section-plot").nth(0);
  const slice = panel.locator(".owl-cross-section-plot").nth(1);
  await page.waitForFunction(
    () =>
      document.querySelectorAll(".owl-cross-section-plot.js-plotly-plot")
        .length === 2,
  );
  let heatData = await heat.evaluate((el) => el.data[0]);
  assert.equal(heatData.colorscale, "Inferno");
  assert.equal(heatData.z[1][1], 1);
  assert.match(heatData.hovertemplate, /input peak/);
  const sliceData = await slice.evaluate((el) => el.data[0]);
  assert.equal(sliceData.y.length, 3);
  assert.match(sliceData.hovertemplate, /input peak/);
  await select.focus();
  await select.selectOption("1");
  assert.equal(await select.inputValue(), "1");
  assert.match(
    await panel.locator('output[aria-live="polite"]').textContent(),
    /12.5%/,
  );
  heatData = await heat.evaluate((el) => el.data[0]);
  assert.equal(heatData.z[1][1], 0.25);
  assert.equal((await state()).saves, 0);
  await setSections({
    planes: [],
    x_mm: [],
    window_mm: 3,
    warnings: ["No planes"],
  });
  assert.equal(await panel.locator(".owl-bench-empty").isVisible(), true);
});

test("Plotly Gaussian reference stops visually at the first aperture", async () => {
  const data = structuredClone(
    await page.evaluate(() => benches[0].model.get("result")),
  );
  data.rays = { z_mm: [0, 10, 10, 20], y_mm: [[0], [0], [0], [0]] };
  data.gaussian = {
    z_mm: [0, 10, 10, 20],
    radius_mm: [0.1, 0.2, 0.2, 0.3],
    aperture_stop_index: 2,
  };
  data.elements = [{ type: "aperture", z_mm: 10, radius_mm: 0.1 }];
  await page.evaluate((result) => benches[0].model.set("result", result), data);
  await first()
    .getByRole("combobox", { name: "Trace view" })
    .selectOption("gaussian");
  const graph = first().locator(".owl-bench-plotly");
  await page.waitForFunction(
    () => document.querySelector(".owl-bench-plotly")?.data?.length === 2,
  );
  assert.deepEqual(
    await graph.evaluate((el) => el.data.map((trace) => trace.x.at(-1))),
    [10, 10],
  );
});

test("Plotly modebar provides axis zoom, pan, reset, and local intensity hover", async () => {
  await page.evaluate(() => {
    const model = benches[0].model;
    const result = structuredClone(model.get("result"));
    result.longitudinal = {
      z_mm: [0, 20],
      x_mm: [-1, 0, 1],
      intensity: [
        [0.1, 0.5, 0.2],
        [0.3, 0.7, 0.4],
      ],
      window_mm: 2,
    };
    result.cross_sections = {
      x_mm: [-1, 0, 1],
      window_mm: 2,
      warnings: [],
      planes: [
        {
          label: "Output",
          z_mm: 20,
          transmission: 0.8,
          intensity: [
            [0.1, 0.2, 0.1],
            [0.3, 0.9, 0.3],
            [0.1, 0.2, 0.1],
          ],
        },
      ],
    };
    model.set("result", result);
  });
  const graph = first().locator(".owl-bench-plotly");
  await page.waitForFunction(() =>
    document.querySelector(".owl-bench-plotly .modebar"),
  );
  const titles = await graph
    .locator(".modebar-btn")
    .evaluateAll((buttons) =>
      buttons.map((button) => button.getAttribute("data-title")),
    );
  assert.ok(titles.some((title) => /zoom/i.test(title)));
  assert.ok(titles.some((title) => /pan/i.test(title)));
  assert.ok(titles.some((title) => /reset|autoscale/i.test(title)));
  const heat = await graph.evaluate((el) =>
    el.data.find((trace) => trace.type === "heatmap"),
  );
  assert.equal(heat.customdata[1][1], 0.7);
  assert.match(heat.hovertemplate, /input peak/);
  const sectionPlots = first().locator(".owl-cross-section-plot");
  await page.waitForFunction(() =>
    document.querySelector(".owl-cross-section-plot .modebar"),
  );
  assert.equal(await sectionPlots.count(), 2);
  assert.ok(
    await sectionPlots.nth(0).evaluate((el) => el.data[0].z[1][1] === 0.9),
  );
});

test("standalone uses result directly and shared mount disposes independently", async () => {
  await page.evaluate((data) => {
    benches[0].cleanup();
    benches[1].cleanup();
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
  await page.waitForFunction(
    () =>
      document.querySelectorAll(".owl-cross-section-plot.js-plotly-plot")
        .length === 4,
  );
  await first().getByRole("combobox").selectOption("1");
  const data = crossSections();
  data.planes[1].transmission = 0;
  data.planes[1].intensity = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ];
  await page.evaluate((data) => benches[0].model.set("result", data), data);
  assert.match(
    await first().locator('output[aria-live="polite"]').textContent(),
    /0.0%/,
  );
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
  assert.equal(await page.locator("#b .owl-cross-section-plot").count(), 0);
  assert.deepEqual(
    await page.evaluate(() =>
      [...benches[0].model.listeners.values()].map((set) => set.size),
    ),
    [0, 0, 0],
  );
});
