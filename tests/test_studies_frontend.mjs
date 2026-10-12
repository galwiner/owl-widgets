// npm exec --yes --package=@playwright/test -- node --test tests/test_studies_frontend.mjs
import { after, afterEach, before, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { delimiter, resolve } from "node:path";

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
    "Run via npm exec --yes --package=@playwright/test -- node --test tests/test_studies_frontend.mjs",
  );
}
const { chromium } = loadPlaywright();
const js = await readFile(
  new URL("../src/owl/static/studies.js", import.meta.url),
  "utf8",
);
const css = await readFile(
  new URL("../src/owl/static/studies.css", import.meta.url),
  "utf8",
);

const raster = (peak = 1) => [
  [0, 0.001, 0.01],
  [0.1, peak, 0.1],
  [0.01, 0.001, 0],
];
const ratios = [null, 2, 1, 0.5];
function apertureFixture() {
  const x = [-1, 0, 1],
    z = [0, 100, 220];
  const scenarios = ratios.map((ratio, index) => ({
    diameter_ratio: ratio,
    aperture_radius_mm: ratio === null ? null : ratio * 0.14,
    analytic_transmission: ratio === null ? 1 : [0, 0.865, 0.393, 0.118][index],
    sampled_transmission: ratio === null ? 1 : [0, 0.86, 0.39, 0.12][index],
    fresnel_number: ratio === null ? null : ratio,
    brightest_z_mm: 153 - index * 5,
    focal_shift_mm: -index * 5,
    peak_ratio: 1 - index * 0.2,
    longitudinal_intensity: raster(1 - index * 0.2),
    brightest_spot_intensity: raster(1 - index * 0.2),
  }));
  const fanScenarios = ratios.map((ratio, index) => ({
    diameter_ratio: ratio,
    passing_count: index === 0 ? 2 : 1,
    paths: [
      {
        launch_height_mm: -0.25,
        launch_angle_rad: 0,
        color_scalar: 0,
        blocked: index > 0,
        z_mm: index > 0 ? [0, 100] : [0, 100, 200, 220],
        y_mm: index > 0 ? [-0.25, -0.4] : [-0.25, -0.4, 0.25, 0.3],
      },
      {
        launch_height_mm: 0.25,
        launch_angle_rad: 0,
        color_scalar: 1,
        blocked: false,
        z_mm: [0, 100, 200, 220],
        y_mm: [0.25, 0.1, -0.25, -0.3],
      },
    ],
  }));
  const comparisons = ratios.map((ratio, index) => ({
    diameter_ratio: ratio,
    passing_ray_count: index ? 50 : 100,
    ray_encircled_incident_fraction: 0.85 - index * 0.1,
    wave_encircled_incident_fraction: 0.84 - index * 0.15,
    ray_histogram: raster(1 - index * 0.2),
    wave_intensity: raster(1 - index * 0.25),
  }));
  return {
    schema_version: 1,
    coordinates: {
      units: { length: "mm", angle: "rad" },
      array_order: {
        longitudinal_intensity: "[x,z]",
        spots_and_histograms: "[y,x]",
      },
      origin: "input_waist",
    },
    spec: {
      waist_mm: 0.25,
      wavelength_nm: 1000,
      distance_mm: 100,
      focal_length_mm: 50,
      aperture_diameter_ratios: ratios,
      grid_size: 3,
      window_mm: 2,
      longitudinal_samples: 3,
      ray_count: 100,
      seed: 0,
    },
    grids: {
      x_mm: x,
      z_mm: z,
      image_histogram_edges_mm: [-0.6, -0.2, 0.2, 0.6],
    },
    normalization: {
      longitudinal_and_brightest_spots: "unclipped_true_waist_peak",
      unclipped_true_waist_peak: 1,
      image_plane_wave_peak: 1,
      image_plane_ray_histogram_peak: 1,
    },
    gaussian_reference: {
      rayleigh_range_mm: 196,
      lens_radius_mm: 0.28,
      radius_by_z_mm: [0.25, 0.28, 0.3],
      geometric_image_z_mm: 200,
      geometric_image_radius_mm: 0.25,
      true_waist_z_mm: 153,
      true_waist_radius_mm: 0.062,
      magnification: -1,
    },
    scenarios,
    ray_fan: {
      launch_heights_mm: [-0.25, 0.25],
      launch_angles_rad: [0],
      scenarios: fanScenarios,
    },
    image_plane_comparison: {
      z_mm: 200,
      reference_circle_radius_mm: 0.25,
      scenarios: comparisons,
    },
  };
}

function stopFixture() {
  const fields = [-2, 2];
  const stopTable = [
    {
      id: "aperture",
      label: "iris on the lens",
      z_mm: 100,
      radius_mm: 0.5,
      A_pupil: 1,
      B_field: 0,
      classification: "aperture",
    },
    {
      id: "field",
      label: "at the image plane",
      z_mm: 200,
      radius_mm: 1.2,
      A_pupil: 0,
      B_field: -1,
      classification: "field",
    },
    {
      id: "vignette",
      label: "halfway",
      z_mm: 150,
      radius_mm: 0.8,
      A_pupil: 0.5,
      B_field: -0.5,
      classification: "vignette",
    },
  ];
  const byId = Object.fromEntries(stopTable.map((item) => [item.id, item]));
  const configs = [
    ["aperture_only", "aperture stop only — iris on the lens", ["aperture"]],
    ["field_stop", "+ field stop at the image plane", ["aperture", "field"]],
    [
      "vignette_stop",
      "+ a stop halfway to the image",
      ["aperture", "vignette"],
    ],
  ];
  const rayDiagrams = configs.map(([id, label, stops], panel) => ({
    id,
    label,
    stops: stops.map((key) => byId[key]),
    paths: fields.map((height, index) => {
      const blocked = panel > 0 && index === 1;
      return {
        field_height_mm: height,
        pupil_height_mm: 0,
        color_scalar: height,
        z_mm: blocked
          ? [0, stops.at(-1) === "field" ? 200 : 150]
          : [0, 100, 240],
        y_mm: blocked ? [height, -height] : [height, 0, -height],
        first_blocked: blocked
          ? {
              z_mm: stops.at(-1) === "field" ? 200 : 150,
              y_mm: -height,
              stop_id: stops.at(-1),
              color: "#ff4d4d",
            }
          : null,
      };
    }),
    distinguished_paths: [
      {
        kind: "marginal",
        line_style: "dotted",
        z_mm: [0, 100, 240],
        y_mm: [0, 0.5, -0.7],
      },
      {
        kind: "chief",
        line_style: "dashed",
        z_mm: [0, 100, 240],
        y_mm: [2, 0, -2],
      },
    ],
  }));
  const pupilMaps = [0, 1.4, 1.8, 2.05].map((height, index) => ({
    field_height_mm: height,
    sample: {
      x_mm: [-0.5, 0, 0.5, 0.7],
      y_mm: [0, 0.4, -0.4, 0],
      pass: [true, true, index < 2, false],
    },
    projected_stop_circles: [
      { stop_id: "aperture", center_x_mm: 0, center_y_mm: 0, radius_mm: 0.5 },
      {
        stop_id: "vignette",
        center_x_mm: 0,
        center_y_mm: height,
        radius_mm: 1.6,
      },
    ],
    pass_fraction: 0.5,
    relative_pass: 1 - index * 0.2,
    metric_sample_count: 100,
    display_sample_count: 4,
  }));
  return {
    schema_version: 1,
    spec: {
      schema_version: 1,
      relay_distance_mm: 100,
      focal_length_mm: 50,
      pupil_sample_radius_mm: 0.9,
      aperture_stop_z_mm: 100,
      aperture_stop_radius_mm: 0.5,
      field_stop_z_mm: 200,
      field_stop_radius_mm: 1.2,
      vignette_stop_z_mm: 150,
      vignette_stop_radius_mm: 0.8,
      diagram_field_heights_mm: fields,
      diagram_pupil_heights_mm: [0],
      illumination_field_heights_mm: [-2, 0, 2],
      pupil_map_field_heights_mm: [0, 1.4, 1.8, 2.05],
      pupil_count: 100,
      seed: 1,
      display_pupil_count: 4,
      ray_z_count: 3,
    },
    ray_diagrams: rayDiagrams,
    illumination: {
      field_heights_mm: [-2, 0, 2],
      curves: configs.map(([id, label], index) => ({
        id,
        label,
        transmission: [1, 1, 1],
        relative:
          index === 0 ? [1, 1, 1] : index === 1 ? [0, 1, 0] : [0.3, 1, 0.3],
      })),
    },
    pupil_maps: pupilMaps,
    stop_table: stopTable,
    plot: { z_limits_mm: [0, 240], y_limits_mm: [-2.7, 2.7] },
  };
}

let browser, page;
before(async () => {
  browser = await chromium.launch({ headless: true });
});
after(async () => {
  await browser?.close();
});
beforeEach(async () => {
  page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  await page.setContent(
    '<main><div id="aperture"></div><div id="stop"></div></main>',
  );
  await page.addStyleTag({ content: css });
  await page.evaluate(async (source) => {
    const url = URL.createObjectURL(
      new Blob([source], { type: "text/javascript" }),
    );
    try {
      window.renderStudy = (await import(url)).default.render;
    } finally {
      URL.revokeObjectURL(url);
    }
  }, js);
  await page.evaluate(
    ({ aperture, stop }) => {
      class Model {
        constructor(viewKind, result, section = undefined) {
          const settings = structuredClone(result.spec);
          if (viewKind === "aperture_study") {
            settings.schema_version = 1;
            settings.grid_size = 64;
            settings.longitudinal_samples = 16;
          }
          this.state = {
            view_kind: viewKind,
            result,
            settings,
            error: "",
            section,
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
      window.StudyModel = Model;
      window.studyViews = [
        ["aperture", new Model("aperture_study", aperture)],
        ["stop", new Model("stop_study", stop)],
      ].map(([id, model]) => ({
        model,
        cleanup: window.renderStudy({ model, el: document.getElementById(id) }),
      }));
    },
    { aperture: apertureFixture(), stop: stopFixture() },
  );
});
afterEach(async () => {
  await page?.close();
});

const aperture = () => page.locator("#aperture");
const stop = () => page.locator("#stop");
const control = (host, key) => host().locator(`[data-key="${key}"]`);
const modelState = (index) =>
  page.evaluate(
    (position) => ({
      settings: studyViews[position].model.get("settings"),
      saves: studyViews[position].model.saves,
    }),
    index,
  );

test("aperture controls submit one complete settings object and preserve focus", async () => {
  const waist = control(aperture, "waist_mm");
  assert.equal(await waist.inputValue(), "0.25");
  assert.deepEqual(
    await control(aperture, "grid_size").locator("option").allTextContents(),
    ["64", "128", "256", "512"],
  );
  assert.match(
    await aperture().locator(".owl-study-fixed").textContent(),
    /none · 2 wL · 1 wL · 0.5 wL/,
  );
  await waist.focus();
  await waist.fill("0.325");
  await waist.press("Tab");
  const state = await modelState(0);
  assert.equal(state.saves, 1);
  assert.equal(state.settings.waist_mm, 0.325);
  assert.equal(state.settings.schema_version, 1);
  assert.deepEqual(state.settings.aperture_diameter_ratios, ratios);
  await control(aperture, "grid_size").focus();
  await control(aperture, "grid_size").selectOption("256");
  assert.equal((await modelState(0)).saves, 2);
  assert.equal((await modelState(0)).settings.grid_size, 256);
  assert.equal(
    await control(aperture, "grid_size").evaluate(
      (element) => element === document.activeElement,
    ),
    true,
  );
});

test("stop controls sync, save once, and retain untouched schema fields", async () => {
  assert.deepEqual(
    await control(stop, "pupil_count").locator("option").allTextContents(),
    ["5,000", "20,000", "50,000"],
  );
  await control(stop, "vignette_stop_radius_mm").fill("0.9");
  await control(stop, "vignette_stop_radius_mm").press("Tab");
  const state = await modelState(1);
  assert.equal(state.saves, 1);
  assert.equal(state.settings.vignette_stop_radius_mm, 0.9);
  assert.deepEqual(state.settings.diagram_field_heights_mm, [-2, 2]);
  assert.equal(state.settings.schema_version, 1);
});

test("frontend validation avoids saves and backend rollback and errors resync controls", async () => {
  const focal = control(aperture, "focal_length_mm");
  await focal.fill("0");
  await focal.press("Tab");
  assert.equal((await modelState(0)).saves, 0);
  assert.equal(await focal.getAttribute("aria-invalid"), "true");
  assert.match(await aperture().getByRole("alert").textContent(), /positive/);
  await page.evaluate(() => {
    const view = studyViews[0];
    const valid = structuredClone(view.model.get("settings"));
    valid.focal_length_mm = 45;
    view.model.set("settings", valid);
    view.model.set("error", "distance_mm must exceed focal_length_mm");
  });
  assert.equal(await control(aperture, "focal_length_mm").inputValue(), "45");
  assert.equal(
    await control(aperture, "focal_length_mm").getAttribute("aria-invalid"),
    null,
  );
  assert.match(
    await aperture().getByRole("alert").textContent(),
    /must exceed/,
  );
  await page.evaluate(() => studyViews[0].model.set("error", ""));
  assert.equal(await aperture().getByRole("alert").isHidden(), true);
});

test("result redraw leaves focused controls intact", async () => {
  await control(stop, "relay_distance_mm").focus();
  await page.evaluate(() => {
    const view = studyViews[1];
    view.model.set("result", structuredClone(view.model.get("result")));
  });
  assert.equal(
    await control(stop, "relay_distance_mm").evaluate(
      (element) => element === document.activeElement,
    ),
    true,
  );
});

test("section models render only relevant plots and controls", async () => {
  await page.evaluate(
    ({ apertureResult, stopResult }) => {
      const definitions = [
        ["focus", "aperture_study", apertureResult],
        ["comparison", "aperture_study", apertureResult],
        ["rays", "stop_study", stopResult],
        ["pupils", "stop_study", stopResult],
      ];
      window.sectionViews = definitions.map(([section, kind, result]) => {
        const el = document.createElement("div");
        el.id = section;
        document.querySelector("main").append(el);
        const model = new StudyModel(kind, result, section);
        return { model, cleanup: renderStudy({ model, el }) };
      });
    },
    { apertureResult: apertureFixture(), stopResult: stopFixture() },
  );

  const expected = {
    focus: {
      plots: 2,
      keys: [
        "waist_mm",
        "wavelength_nm",
        "distance_mm",
        "focal_length_mm",
        "grid_size",
        "window_mm",
        "longitudinal_samples",
      ],
      heading: "Aperture focus",
    },
    comparison: {
      plots: 3,
      keys: [
        "waist_mm",
        "wavelength_nm",
        "distance_mm",
        "focal_length_mm",
        "grid_size",
        "window_mm",
        "ray_count",
      ],
      heading: "Aperture comparison",
    },
    rays: {
      plots: 2,
      keys: [
        "focal_length_mm",
        "relay_distance_mm",
        "aperture_stop_z_mm",
        "aperture_stop_radius_mm",
        "field_stop_z_mm",
        "field_stop_radius_mm",
        "vignette_stop_z_mm",
        "vignette_stop_radius_mm",
      ],
      heading: "Stop rays",
    },
    pupils: {
      plots: 1,
      keys: [
        "focal_length_mm",
        "relay_distance_mm",
        "aperture_stop_z_mm",
        "aperture_stop_radius_mm",
        "vignette_stop_z_mm",
        "vignette_stop_radius_mm",
        "pupil_count",
      ],
      heading: "Exit pupils",
    },
  };
  for (const [id, details] of Object.entries(expected)) {
    const host = page.locator(`#${id}`);
    assert.equal(await host.locator("figure").count(), details.plots);
    assert.deepEqual(
      await host
        .locator("[data-key]")
        .evaluateAll((nodes) => nodes.map((element) => element.dataset.key)),
      details.keys,
    );
    assert.equal(
      await host.locator(".owl-study-header strong").textContent(),
      details.heading,
    );
    assert.equal(
      await host
        .locator(".owl-study")
        .evaluate((element) => getComputedStyle(element).maxWidth),
      "900px",
    );
  }
  assert.equal(
    await page.locator("#focus .owl-study-comparison-matrix").count(),
    0,
  );
  assert.equal(
    await page.locator("#comparison .owl-study-focus-matrix").count(),
    0,
  );
  assert.equal(await page.locator("#rays .owl-study-pupil-matrix").count(), 0);
  assert.equal(await page.locator("#pupils .owl-study-stop-stack").count(), 0);

  const selectors = {
    focus: "Aperture case",
    comparison: "Aperture case",
    rays: "Stop configuration",
    pupils: "Field height",
  };
  for (const [id, label] of Object.entries(selectors))
    assert.equal(
      await page.locator(`#${id}`).getByLabel(label, { exact: true }).count(),
      1,
      `${id} has its local display selector`,
    );

  await page
    .locator("#focus")
    .getByLabel("Aperture case", { exact: true })
    .selectOption("2");
  assert.match(
    await page
      .locator("#focus figure")
      .first()
      .locator("figcaption")
      .textContent(),
    /D = 1 wL/,
  );
  await page
    .locator("#comparison")
    .getByLabel("Aperture case", { exact: true })
    .selectOption("3");
  assert.match(
    await page
      .locator("#comparison figure")
      .first()
      .locator("figcaption")
      .textContent(),
    /D = 0.5 wL/,
  );
  await page
    .locator("#rays")
    .getByLabel("Stop configuration", { exact: true })
    .selectOption("2");
  assert.match(
    await page
      .locator("#rays figure")
      .first()
      .locator("figcaption")
      .textContent(),
    /halfway/,
  );
  await page
    .locator("#pupils")
    .getByLabel("Field height", { exact: true })
    .selectOption("2");
  assert.match(
    await page.locator("#pupils figcaption").textContent(),
    /field h = 1.8 mm/,
  );
  assert.deepEqual(
    await page.evaluate(() => sectionViews.map((view) => view.model.saves)),
    [0, 0, 0, 0],
  );

  await page.evaluate(() => {
    for (const view of sectionViews) {
      const result = structuredClone(view.model.get("result"));
      view.model.set("result", result);
    }
  });
  assert.equal(
    await page
      .locator("#focus")
      .getByLabel("Aperture case", { exact: true })
      .inputValue(),
    "2",
  );
  assert.equal(
    await page
      .locator("#rays")
      .getByLabel("Stop configuration", { exact: true })
      .inputValue(),
    "2",
  );
  assert.equal(
    await page
      .locator("#pupils")
      .getByLabel("Field height", { exact: true })
      .inputValue(),
    "2",
  );

  await page.evaluate(() => {
    const focusView = sectionViews[0];
    const result = structuredClone(focusView.model.get("result"));
    result.scenarios.splice(2, 1);
    result.ray_fan.scenarios.splice(2, 1);
    result.image_plane_comparison.scenarios.splice(2, 1);
    focusView.model.set("result", result);
  });
  assert.equal(
    await page
      .locator("#focus")
      .getByLabel("Aperture case", { exact: true })
      .inputValue(),
    "2",
  );
  assert.match(
    await page.locator("#focus figcaption").first().textContent(),
    /D = 0.5 wL/,
  );
  assert.deepEqual(
    await page.evaluate(() => sectionViews.map((view) => view.model.saves)),
    [0, 0, 0, 0],
  );
  await page.evaluate(() => sectionViews.forEach((view) => view.cleanup()));
});

test("aperture study renders faithful 4x2 and 4x3 matrices", async () => {
  assert.equal(
    await aperture().locator(".owl-study-focus-matrix > figure").count(),
    8,
  );
  assert.equal(
    await aperture().locator(".owl-study-comparison-matrix > figure").count(),
    12,
  );
  assert.equal(await aperture().locator("canvas").count(), 16);
  assert.equal(await aperture().locator(".owl-study-brightest").count(), 4);
  assert.equal(
    await aperture().locator(".owl-study-circle-aperture").count(),
    0,
  );
  assert.equal(
    await aperture().locator(".owl-study-ray[data-launch-height]").count(),
    8,
  );
  assert.equal(
    await aperture().locator('.owl-study-ray[data-blocked="true"]').count(),
    3,
  );
  assert.match(
    await aperture().textContent(),
    /shared three-decade logarithmic intensity scale/i,
  );
});

test("heatmap canvases fill the same plotting rectangle as their SVG axes", async () => {
  const geometry = await aperture()
    .locator(".owl-study-focus-matrix figure")
    .first()
    .locator(".owl-study-plot")
    .evaluate((plot) => {
      const canvas = plot.querySelector("canvas").getBoundingClientRect();
      const box = plot.getBoundingClientRect();
      const svg = plot.querySelector("svg");
      const point = (x, y) => {
        const p = new DOMPoint(x, y).matrixTransform(svg.getScreenCTM());
        return { x: p.x, y: p.y };
      };
      return {
        left: (canvas.left - box.left) / box.width,
        right: (canvas.right - box.left) / box.width,
        top: (canvas.top - box.top) / box.height,
        bottom: (canvas.bottom - box.top) / box.height,
        canvas: {
          left: canvas.left,
          right: canvas.right,
          top: canvas.top,
          bottom: canvas.bottom,
        },
        svgTopLeft: point(58, 16),
        svgBottomRight: point(746, 260),
      };
    });
  assert.ok(Math.abs(geometry.left - 58 / 760) < 0.005);
  assert.ok(Math.abs(geometry.right - 746 / 760) < 0.005);
  assert.ok(Math.abs(geometry.top - 16 / 300) < 0.005);
  assert.ok(Math.abs(geometry.bottom - 260 / 300) < 0.005);
  assert.ok(Math.abs(geometry.canvas.left - geometry.svgTopLeft.x) < 1);
  assert.ok(Math.abs(geometry.canvas.top - geometry.svgTopLeft.y) < 1);
  assert.ok(Math.abs(geometry.canvas.right - geometry.svgBottomRight.x) < 1);
  assert.ok(Math.abs(geometry.canvas.bottom - geometry.svgBottomRight.y) < 1);
});

test("launch and field colors are cyan-to-magenta and blocked/death marks are red", async () => {
  const apertureColors = await aperture()
    .locator(".owl-study-ray[data-launch-height]")
    .first()
    .locator("xpath=..")
    .locator(".owl-study-ray")
    .evaluateAll((nodes) =>
      nodes.slice(0, 2).map((node) => node.getAttribute("stroke")),
    );
  assert.deepEqual(apertureColors, ["rgb(0,255,255)", "rgb(255,0,255)"]);
  assert.equal(
    await aperture()
      .locator('.owl-study-ray[data-blocked="true"]')
      .first()
      .getAttribute("stroke"),
    "#ff4d4d",
  );
  const fieldColors = await stop()
    .locator(".owl-study-ray[data-field-height]")
    .evaluateAll((nodes) => [
      ...new Set(nodes.map((node) => node.getAttribute("stroke"))),
    ]);
  assert.deepEqual(fieldColors, ["rgb(0,255,255)", "rgb(255,0,255)"]);
  assert.equal(await stop().locator(".owl-study-death").count(), 2);
  assert.equal(
    await stop()
      .locator(".owl-study-death")
      .first()
      .evaluate((node) => getComputedStyle(node).fill),
    "rgb(255, 77, 77)",
  );
});

test("all heatmaps use the same log intensity color transform", async () => {
  const colors = await aperture()
    .locator("canvas")
    .evaluateAll((canvases) =>
      canvases.map((canvas) => {
        const data = canvas
          .getContext("2d")
          .getImageData(
            Math.floor(canvas.width / 2),
            Math.floor(canvas.height / 2),
            1,
            1,
          ).data;
        return [...data];
      }),
    );
  assert.deepEqual(colors[0], [252, 255, 164, 255]);
  assert.deepEqual(colors[0], colors[1]);
  assert.deepEqual(colors[0], colors[8]);
});

test("stop study renders three diagrams, illumination, and four pupil maps", async () => {
  assert.equal(
    await stop().locator(".owl-study-stop-stack > figure").count(),
    4,
  );
  assert.equal(await stop().locator(".owl-study-plot-illumination").count(), 1);
  assert.equal(await stop().locator(".owl-study-illumination-line").count(), 3);
  assert.equal(
    await stop().locator(".owl-study-pupil-matrix > figure").count(),
    4,
  );
  assert.equal(await stop().locator(".owl-study-marginal").count(), 3);
  assert.equal(await stop().locator(".owl-study-chief").count(), 3);
  assert.equal(await stop().locator(".owl-study-circle-aperture").count(), 4);
  assert.equal(await stop().locator(".owl-study-circle-vignette").count(), 4);
  assert.match(
    await stop().textContent(),
    /A and B are the pupil and field coefficients/,
  );
});

test("plots have accessible names that explain scientific encodings", async () => {
  const labels = await page
    .locator(".owl-study svg[role=img]")
    .evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute("aria-label")),
    );
  assert.ok(labels.length >= 28);
  assert.ok(labels.every(Boolean));
  assert.ok(
    labels.some((label) => /Shared logarithmic intensity scale/i.test(label)),
  );
  assert.ok(labels.some((label) => /blocked rays are red/i.test(label)));
  assert.ok(labels.some((label) => /Red points mark/i.test(label)));
  assert.ok(labels.some((label) => /Yellow points pass/i.test(label)));
  assert.equal(await page.locator("canvas:not([aria-hidden=true])").count(), 0);
});

test("narrow viewports scroll matrices without overflowing the document", async () => {
  await page.setViewportSize({ width: 320, height: 900 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  const dimensions = await page
    .locator(".owl-study-scroll")
    .evaluateAll((nodes) =>
      nodes.map((node) => ({
        client: node.clientWidth,
        scroll: node.scrollWidth,
      })),
    );
  assert.ok(
    dimensions.every(({ client, scroll }) => client > 0 && scroll > client),
  );
  assert.ok((await aperture().boundingBox()).width <= 320);
  assert.ok((await stop().boundingBox()).width <= 320);
});

test("result changes redraw and cleanup removes listeners and roots", async () => {
  await page.evaluate(() => {
    const view = studyViews[0];
    const changed = structuredClone(view.model.get("result"));
    changed.scenarios[0].brightest_z_mm = 149;
    view.model.set("result", changed);
  });
  assert.match(await aperture().textContent(), /z = 149 mm/);
  await page.evaluate(() => studyViews.forEach((view) => view.cleanup()));
  assert.equal(await page.locator(".owl-study").count(), 0);
  assert.deepEqual(
    await page.evaluate(() =>
      studyViews.map((view) =>
        [...view.model.listeners.values()].map((set) => set.size),
      ),
    ),
    [
      [0, 0, 0],
      [0, 0, 0],
    ],
  );
});

test("malformed schema produces an accessible error instead of throwing", async () => {
  await page.evaluate(() =>
    studyViews[1].model.set("result", { schema_version: 1 }),
  );
  assert.match(await stop().getByRole("alert").textContent(), /incomplete/i);
  assert.equal(await stop().locator("svg").count(), 0);
});
