const NS = "http://www.w3.org/2000/svg";
let studyId = 0;

function node(tag, attrs = {}, text = "") {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs))
    element.setAttribute(key, value);
  element.textContent = text;
  return element;
}
function svgNode(tag, attrs = {}, text = "") {
  const element = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs))
    element.setAttribute(key, value);
  element.textContent = text;
  return element;
}
const fmt = (value) => String(Number(Number(value).toPrecision(4)));
const pct = (value) => `${Math.round(100 * value)}%`;
const clone = (value) => JSON.parse(JSON.stringify(value));
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const finiteArray = (value) =>
  Array.isArray(value) && value.length > 0 && value.every(Number.isFinite);
const paired = (a, b) =>
  finiteArray(a) && finiteArray(b) && a.length === b.length;
const matrix = (value, rows, columns) =>
  Array.isArray(value) &&
  value.length === rows &&
  value.every((row) => finiteArray(row) && row.length === columns);

function inferno(value) {
  const stops = [
    [0, 0, 4],
    [31, 12, 72],
    [85, 15, 109],
    [136, 34, 106],
    [186, 54, 85],
    [227, 89, 51],
    [249, 140, 10],
    [249, 201, 50],
    [252, 255, 164],
  ];
  const position = clamp(value, 0, 1) * (stops.length - 1);
  const index = Math.min(stops.length - 2, Math.floor(position));
  const mix = position - index;
  return stops[index].map((channel, i) =>
    Math.round(channel + (stops[index + 1][i] - channel) * mix),
  );
}
function logColor(value) {
  const level = value > 0 ? clamp((Math.log10(value) + 3) / 3, 0, 1) : 0;
  return inferno(level);
}
// Matplotlib's cool map: low values cyan, high values magenta.
function cool(value) {
  const scalar = clamp(value, 0, 1);
  return `rgb(${Math.round(255 * scalar)},${Math.round(255 * (1 - scalar))},255)`;
}
function scale(domain, range) {
  const span = domain[1] - domain[0] || 1;
  return (value) =>
    range[0] + ((value - domain[0]) / span) * (range[1] - range[0]);
}
function ticks(domain, count = 5) {
  return Array.from(
    { length: count },
    (_, index) => domain[0] + ((domain[1] - domain[0]) * index) / (count - 1),
  );
}
function pathData(xs, ys, x, y) {
  return xs
    .map((value, index) => `${index ? "L" : "M"}${x(value)},${y(ys[index])}`)
    .join(" ");
}
function labelForRatio(ratio) {
  return ratio === null ? "No aperture" : `D = ${fmt(ratio)} wL`;
}

function drawRaster(canvas, raster) {
  const { values, xDomain, yDomain, displayXDomain, displayYDomain } = raster;
  const height = values.length;
  const width = values[0].length;
  const source = document.createElement("canvas");
  source.width = canvas.width = width;
  source.height = canvas.height = height;
  const sourceContext = source.getContext("2d");
  const image = sourceContext.createImageData(width, height);
  for (let row = 0; row < height; row++) {
    for (let column = 0; column < width; column++) {
      const [r, g, b] = logColor(values[row][column]);
      // Backend rows ascend in physical y/x; canvas rows descend visually.
      const offset = ((height - 1 - row) * width + column) * 4;
      image.data[offset] = r;
      image.data[offset + 1] = g;
      image.data[offset + 2] = b;
      image.data[offset + 3] = 255;
    }
  }
  sourceContext.putImageData(image, 0, 0);
  const xSpan = xDomain[1] - xDomain[0];
  const ySpan = yDomain[1] - yDomain[0];
  const sx = ((displayXDomain[0] - xDomain[0]) / xSpan) * width;
  const sw = ((displayXDomain[1] - displayXDomain[0]) / xSpan) * width;
  // Canvas source y=0 is the physical upper bound after the row flip.
  const sy = ((yDomain[1] - displayYDomain[1]) / ySpan) * height;
  const sh = ((displayYDomain[1] - displayYDomain[0]) / ySpan) * height;
  const context = canvas.getContext("2d");
  context.imageSmoothingEnabled = false;
  context.drawImage(source, sx, sy, sw, sh, 0, 0, width, height);
}

function plotFrame({
  label,
  description,
  square = false,
  illumination = false,
  raster = null,
}) {
  const figure = node("figure", { class: "owl-study-panel" });
  const caption = node("figcaption", { class: "owl-study-caption" }, label);
  const classes = [
    "owl-study-plot",
    square && "owl-study-plot-square",
    illumination && "owl-study-plot-illumination",
  ]
    .filter(Boolean)
    .join(" ");
  const plot = node("div", { class: classes });
  let canvas = null;
  if (raster) {
    canvas = node("canvas", { "aria-hidden": "true" });
    drawRaster(canvas, raster);
    plot.append(canvas);
  }
  const svg = svgNode("svg", {
    viewBox: square
      ? "0 0 300 300"
      : illumination
        ? "0 0 760 250"
        : "0 0 760 300",
    role: "img",
    "aria-label": description,
  });
  svg.append(svgNode("title", {}, description));
  plot.append(svg);
  figure.append(caption, plot);
  return { figure, plot, svg, canvas };
}

function axes(
  svg,
  xDomain,
  yDomain,
  {
    square = false,
    xLabel = "x (mm)",
    yLabel = "y (mm)",
    xCount = 5,
    yCount = 3,
  } = {},
) {
  const width = square ? 300 : 760;
  const height = square ? 300 : 300;
  const box = {
    left: square ? 48 : 58,
    right: width - 14,
    top: 16,
    bottom: height - 40,
  };
  const x = scale(xDomain, [box.left, box.right]);
  const y = scale(yDomain, [box.bottom, box.top]);
  for (const value of ticks(xDomain, xCount)) {
    svg.append(
      svgNode("line", {
        x1: x(value),
        x2: x(value),
        y1: box.top,
        y2: box.bottom,
        class: "owl-study-grid",
      }),
    );
    svg.append(
      svgNode(
        "text",
        { x: x(value), y: box.bottom + 16, "text-anchor": "middle" },
        fmt(value),
      ),
    );
  }
  for (const value of ticks(yDomain, yCount)) {
    svg.append(
      svgNode("line", {
        x1: box.left,
        x2: box.right,
        y1: y(value),
        y2: y(value),
        class: Math.abs(value) < 1e-12 ? "owl-study-axis" : "owl-study-grid",
      }),
    );
    svg.append(
      svgNode(
        "text",
        { x: box.left - 7, y: y(value) + 3, "text-anchor": "end" },
        fmt(value),
      ),
    );
  }
  svg.append(
    svgNode(
      "text",
      { x: (box.left + box.right) / 2, y: height - 7, "text-anchor": "middle" },
      xLabel,
    ),
    svgNode(
      "text",
      {
        x: 12,
        y: (box.top + box.bottom) / 2,
        transform: `rotate(-90 12 ${(box.top + box.bottom) / 2})`,
        "text-anchor": "middle",
      },
      yLabel,
    ),
  );
  return { ...box, x, y };
}

function circle(svg, geometry, cx, cy, radius, className) {
  svg.append(
    svgNode("ellipse", {
      cx: geometry.x(cx),
      cy: geometry.y(cy),
      rx: Math.abs(geometry.x(cx + radius) - geometry.x(cx)),
      ry: Math.abs(geometry.y(cy + radius) - geometry.y(cy)),
      class: className,
    }),
  );
}
function vertical(svg, geometry, value, className) {
  svg.append(
    svgNode("line", {
      x1: geometry.x(value),
      x2: geometry.x(value),
      y1: geometry.top,
      y2: geometry.bottom,
      class: className,
    }),
  );
}
function jaws(svg, geometry, z, radius) {
  const upper = clamp(geometry.y(radius), geometry.top, geometry.bottom);
  const lower = clamp(geometry.y(-radius), geometry.top, geometry.bottom);
  svg.append(
    svgNode("line", {
      x1: geometry.x(z),
      x2: geometry.x(z),
      y1: geometry.top,
      y2: upper,
      class: "owl-study-stop",
    }),
    svgNode("line", {
      x1: geometry.x(z),
      x2: geometry.x(z),
      y1: lower,
      y2: geometry.bottom,
      class: "owl-study-stop",
    }),
  );
}
function section(title, note, matrixClass) {
  const root = node("section", { class: "owl-study-section" });
  root.append(
    node("h2", {}, title),
    node("p", { class: "owl-study-note" }, note),
  );
  const scroll = node("div", {
    class: "owl-study-scroll",
    tabindex: "0",
    "aria-label": `${title}; scroll horizontally when needed`,
  });
  const content = node("div", { class: matrixClass });
  scroll.append(content);
  root.append(scroll);
  return { root, content, scroll };
}
function legend(items) {
  const root = node("div", {
    class: "owl-study-legend",
    "aria-label": "Plot legend",
  });
  for (const [className, text] of items)
    root.append(node("span", { class: `owl-study-key ${className}` }, text));
  return root;
}

function selectedItem(items, key, selection) {
  let index = items.findIndex((item) => Object.is(key(item), selection.value));
  if (index < 0) index = clamp(selection.index ?? 0, 0, items.length - 1);
  selection.index = index;
  selection.value = key(items[index]);
  return items[index];
}

function localSelector(
  sectionRoot,
  label,
  items,
  key,
  optionLabel,
  selection,
  redraw,
) {
  const selected = selectedItem(items, key, selection);
  const field = node("label", { class: "owl-study-view-selector" });
  const select = node("select", {
    "aria-label": label,
    "data-local-selector": label,
  });
  items.forEach((item, index) =>
    select.append(node("option", { value: index }, optionLabel(item))),
  );
  select.value = String(items.indexOf(selected));
  select.addEventListener("change", () => {
    selection.index = Number(select.value);
    selection.value = key(items[selection.index]);
    redraw();
  });
  field.append(node("span", {}, label), select);
  sectionRoot.insertBefore(
    field,
    sectionRoot.querySelector(".owl-study-scroll"),
  );
  return selected;
}

function validateAperture(result) {
  if (result?.schema_version !== 1) return "Unsupported aperture study schema.";
  const x = result?.grids?.x_mm,
    z = result?.grids?.z_mm,
    edges = result?.grids?.image_histogram_edges_mm;
  if (
    !finiteArray(x) ||
    !finiteArray(z) ||
    !finiteArray(edges) ||
    !Array.isArray(result.scenarios)
  )
    return "Aperture study coordinates are incomplete.";
  if (
    !finiteArray(result?.gaussian_reference?.radius_by_z_mm) ||
    result.gaussian_reference.radius_by_z_mm.length !== z.length
  )
    return "Aperture Gaussian reference is incomplete.";
  if (
    !result.scenarios.every(
      (item) =>
        matrix(item.longitudinal_intensity, x.length, z.length) &&
        matrix(item.brightest_spot_intensity, x.length, x.length),
    )
  )
    return "Aperture study intensity arrays do not match their coordinates.";
  const comparisons = result?.image_plane_comparison?.scenarios;
  const fans = result?.ray_fan?.scenarios;
  if (
    !Array.isArray(comparisons) ||
    !Array.isArray(fans) ||
    comparisons.length !== result.scenarios.length ||
    fans.length !== result.scenarios.length
  )
    return "Aperture comparison scenarios are incomplete.";
  const bins = edges.length - 1;
  if (
    !comparisons.every(
      (item) =>
        matrix(item.ray_histogram, bins, bins) &&
        matrix(item.wave_intensity, x.length, x.length),
    )
  )
    return "Aperture image-plane arrays do not match their coordinates.";
  return "";
}

function renderAperture(
  root,
  result,
  sectionName = "all",
  selections = {},
  redraw = () => {},
) {
  const error = validateAperture(result);
  if (error) throw new Error(error);
  const xGrid = result.grids.x_mm;
  const zGrid = result.grids.z_mm;
  const ref = result.gaussian_reference;
  const lensZ = result.spec.distance_mm;
  const focus = section(
    "Fresnel focus sweep",
    "Four aperture diameters on one shared three-decade logarithmic intensity scale. Heatmaps are normalized to the unclipped true-waist peak.",
    "owl-study-matrix owl-study-focus-matrix",
  );
  const focusScenarios =
    sectionName === "focus"
      ? [
          localSelector(
            focus.root,
            "Aperture case",
            result.scenarios,
            (scenario) => scenario.diameter_ratio,
            (scenario) => labelForRatio(scenario.diameter_ratio),
            selections.focus,
            redraw,
          ),
        ]
      : result.scenarios;
  for (const scenario of focusScenarios) {
    const aperture =
      scenario.aperture_radius_mm === null
        ? "100% transmission"
        : `${pct(scenario.analytic_transmission)} transmission · focal shift ${scenario.focal_shift_mm >= 0 ? "+" : ""}${fmt(scenario.focal_shift_mm)} mm`;
    const longitudinalLabel = `${labelForRatio(scenario.diameter_ratio)} · ${aperture}`;
    const longitudinalDescription = `${labelForRatio(scenario.diameter_ratio)} longitudinal Fresnel intensity from z ${fmt(zGrid[0])} to ${fmt(zGrid.at(-1))} millimetres and transverse coordinate ${fmt(xGrid[0])} to ${fmt(xGrid.at(-1))} millimetres. Shared logarithmic intensity scale 10 to the minus 3 through 1. Dashed white lines are the unclipped Gaussian radius; cyan marks the lens or aperture; green marks the brightest plane.`;
    const longitudinal = plotFrame({
      label: longitudinalLabel,
      description: longitudinalDescription,
      raster: {
        values: scenario.longitudinal_intensity,
        xDomain: [zGrid[0], zGrid.at(-1)],
        yDomain: [xGrid[0], xGrid.at(-1)],
        displayXDomain: [zGrid[0], zGrid.at(-1)],
        displayYDomain: [-0.75, 0.75],
      },
    });
    const geometry = axes(
      longitudinal.svg,
      [zGrid[0], zGrid.at(-1)],
      [-0.75, 0.75],
      { xLabel: "z (mm)", yLabel: "y (mm)" },
    );
    for (const sign of [-1, 1])
      longitudinal.svg.append(
        svgNode("path", {
          d: pathData(
            zGrid,
            ref.radius_by_z_mm.map((value) => sign * value),
            geometry.x,
            geometry.y,
          ),
          class: "owl-study-reference",
        }),
      );
    if (scenario.aperture_radius_mm === null)
      vertical(longitudinal.svg, geometry, lensZ, "owl-study-stop");
    else jaws(longitudinal.svg, geometry, lensZ, scenario.aperture_radius_mm);
    vertical(
      longitudinal.svg,
      geometry,
      ref.geometric_image_z_mm,
      "owl-study-image-plane",
    );
    vertical(
      longitudinal.svg,
      geometry,
      scenario.brightest_z_mm,
      "owl-study-brightest",
    );
    focus.content.append(longitudinal.figure);

    const crop = 0.22;
    const spotLabel = `Brightest plane z = ${fmt(scenario.brightest_z_mm)} mm · peak ${fmt(scenario.peak_ratio)}`;
    const spot = plotFrame({
      label: spotLabel,
      description: `${labelForRatio(scenario.diameter_ratio)} transverse intensity at its brightest plane, on the shared logarithmic scale. The dashed circle is the unclipped true-waist radius of ${fmt(ref.true_waist_radius_mm)} millimetres.`,
      square: true,
      raster: {
        values: scenario.brightest_spot_intensity,
        xDomain: [xGrid[0], xGrid.at(-1)],
        yDomain: [xGrid[0], xGrid.at(-1)],
        displayXDomain: [-crop, crop],
        displayYDomain: [-crop, crop],
      },
    });
    const spotGeometry = axes(spot.svg, [-crop, crop], [-crop, crop], {
      square: true,
    });
    circle(
      spot.svg,
      spotGeometry,
      0,
      0,
      ref.true_waist_radius_mm,
      "owl-study-reference",
    );
    focus.content.append(spot.figure);
  }
  focus.root.append(
    legend([
      ["owl-study-key-reference", "Dashed: unclipped Gaussian reference"],
      ["owl-study-key-blocked", "Shared |U|² log scale: 10⁻³ to 1"],
    ]),
  );
  if (sectionName !== "comparison") root.append(focus.root);

  const comparison = section(
    "Rays and waves at the image plane",
    "Rays cannot interfere. Fan colors encode launch height from cyan (lowest) to magenta (highest); blocked rays are red and stop at the aperture. Ray and wave columns each share their unclipped image-plane peak.",
    "owl-study-matrix owl-study-comparison-matrix",
  );
  const fanByRatio = new Map(
    result.ray_fan.scenarios.map((item) => [item.diameter_ratio, item]),
  );
  const imageByRatio = new Map(
    result.image_plane_comparison.scenarios.map((item) => [
      item.diameter_ratio,
      item,
    ]),
  );
  const comparisonScenarios =
    sectionName === "comparison"
      ? [
          localSelector(
            comparison.root,
            "Aperture case",
            result.scenarios,
            (scenario) => scenario.diameter_ratio,
            (scenario) => labelForRatio(scenario.diameter_ratio),
            selections.comparison,
            redraw,
          ),
        ]
      : result.scenarios;
  for (const scenario of comparisonScenarios) {
    const fan = fanByRatio.get(scenario.diameter_ratio);
    const image = imageByRatio.get(scenario.diameter_ratio);
    const blocked = fan.paths.length - fan.passing_count;
    const fanPlot = plotFrame({
      label: `${labelForRatio(scenario.diameter_ratio)} · ${fan.passing_count}/${fan.paths.length} pass · ${blocked} blocked`,
      description: `${labelForRatio(scenario.diameter_ratio)} ray fan. Rays are colored from cyan to magenta by launch height. ${blocked} blocked rays are red and terminate at the aperture. Dashed white lines show the Gaussian radius.`,
    });
    const geometry = axes(
      fanPlot.svg,
      [zGrid[0], zGrid.at(-1)],
      [-0.75, 0.75],
      { xLabel: "z (mm)", yLabel: "y (mm)" },
    );
    for (const ray of fan.paths)
      fanPlot.svg.append(
        svgNode("path", {
          d: pathData(ray.z_mm, ray.y_mm, geometry.x, geometry.y),
          class: `owl-study-ray${ray.blocked ? " owl-study-ray-blocked" : ""}`,
          stroke: ray.blocked ? "#ff4d4d" : cool(ray.color_scalar),
          "data-launch-height": ray.launch_height_mm,
          "data-blocked": ray.blocked,
        }),
      );
    for (const sign of [-1, 1])
      fanPlot.svg.append(
        svgNode("path", {
          d: pathData(
            zGrid,
            ref.radius_by_z_mm.map((value) => sign * value),
            geometry.x,
            geometry.y,
          ),
          class: "owl-study-reference",
        }),
      );
    if (scenario.aperture_radius_mm === null)
      vertical(fanPlot.svg, geometry, lensZ, "owl-study-stop");
    else jaws(fanPlot.svg, geometry, lensZ, scenario.aperture_radius_mm);
    vertical(
      fanPlot.svg,
      geometry,
      result.image_plane_comparison.z_mm,
      "owl-study-image-plane",
    );
    comparison.content.append(fanPlot.figure);

    const panels = [
      [
        "Rays",
        image.ray_histogram,
        result.grids.image_histogram_edges_mm,
        image.ray_encircled_incident_fraction,
      ],
      [
        "Wave",
        image.wave_intensity,
        xGrid,
        image.wave_encircled_incident_fraction,
      ],
    ];
    for (const [kind, values, coordinates, encircled] of panels) {
      const peak = Math.max(...values.flat());
      const crop = 0.55;
      const sourceDomain =
        kind === "Rays"
          ? [coordinates[0], coordinates.at(-1)]
          : [coordinates[0], coordinates.at(-1)];
      const spot = plotFrame({
        label: `${kind} · peak ${fmt(peak)} · in circle ${pct(encircled)}`,
        description: `${kind} image-plane intensity for ${labelForRatio(scenario.diameter_ratio)}, on a shared logarithmic scale from 10 to the minus 3 through 1. The dashed circle is the unclipped geometric image radius.`,
        square: true,
        raster: {
          values,
          xDomain: sourceDomain,
          yDomain: sourceDomain,
          displayXDomain: [-crop, crop],
          displayYDomain: [-crop, crop],
        },
      });
      const spotGeometry = axes(spot.svg, [-crop, crop], [-crop, crop], {
        square: true,
      });
      circle(
        spot.svg,
        spotGeometry,
        0,
        0,
        result.image_plane_comparison.reference_circle_radius_mm,
        "owl-study-reference",
      );
      spot.figure.dataset.coordinateCount = coordinates.length;
      comparison.content.append(spot.figure);
    }
  }
  comparison.root.append(
    legend([
      ["owl-study-key-gradient", "Cyan → magenta: low → high launch height"],
      ["owl-study-key-blocked", "Red: blocked ray"],
      ["owl-study-key-reference", "Dashed: Gaussian reference"],
    ]),
  );
  if (sectionName !== "focus") root.append(comparison.root);
}

function validateStop(result) {
  if (result?.schema_version !== 1) return "Unsupported stop study schema.";
  if (
    !Array.isArray(result.ray_diagrams) ||
    !Array.isArray(result.pupil_maps) ||
    !finiteArray(result?.plot?.z_limits_mm) ||
    !finiteArray(result?.plot?.y_limits_mm)
  )
    return "Stop study panels are incomplete.";
  if (
    !finiteArray(result?.illumination?.field_heights_mm) ||
    !Array.isArray(result?.illumination?.curves)
  )
    return "Stop study illumination is incomplete.";
  for (const diagram of result.ray_diagrams)
    for (const path of [
      ...(diagram.paths || []),
      ...(diagram.distinguished_paths || []),
    ])
      if (!paired(path.z_mm, path.y_mm))
        return "Stop study ray coordinates are inconsistent.";
  if (
    !result.illumination.curves.every(
      (curve) =>
        finiteArray(curve.relative) &&
        curve.relative.length === result.illumination.field_heights_mm.length,
    )
  )
    return "Stop study illumination coordinates are inconsistent.";
  for (const map of result.pupil_maps)
    if (
      !paired(map?.sample?.x_mm, map?.sample?.y_mm) ||
      map.sample.pass.length !== map.sample.x_mm.length
    )
      return "Stop study pupil samples are inconsistent.";
  return "";
}

function renderStop(
  root,
  result,
  sectionName = "all",
  selections = {},
  redraw = () => {},
) {
  const error = validateStop(result);
  if (error) throw new Error(error);
  const [zMin, zMax] = result.plot.z_limits_mm;
  const [yMin, yMax] = result.plot.y_limits_mm;
  const fieldValues = result.spec.diagram_field_heights_mm;
  const fieldMin = Math.min(...fieldValues),
    fieldMax = Math.max(...fieldValues);
  const fieldScalar = (value) =>
    (value - fieldMin) / (fieldMax - fieldMin || 1);
  const diagrams = section(
    "Stops, ray fans, and illumination",
    "Ray color encodes object field height from cyan (lowest) to magenta (highest). A red point marks the first stop that kills a ray. A and B are the pupil and field coefficients.",
    "owl-study-stop-stack",
  );
  const rayDiagrams =
    sectionName === "rays"
      ? [
          localSelector(
            diagrams.root,
            "Stop configuration",
            result.ray_diagrams,
            (diagram) => diagram.id,
            (diagram) => diagram.label,
            selections.rays,
            redraw,
          ),
        ]
      : result.ray_diagrams;
  for (const diagram of rayDiagrams) {
    const plot = plotFrame({
      label: diagram.label,
      description: `${diagram.label}. Rays are colored from cyan to magenta by field height. Red points mark where a stop first blocks a ray. The white dotted marginal ray runs from the axis to the aperture rim; the white dashed chief ray runs from the field edge through the aperture center.`,
    });
    const geometry = axes(plot.svg, [zMin, zMax], [yMin, yMax], {
      xLabel: "z (mm)",
      yLabel: "y (mm)",
    });
    for (const ray of diagram.paths) {
      plot.svg.append(
        svgNode("path", {
          d: pathData(ray.z_mm, ray.y_mm, geometry.x, geometry.y),
          class: "owl-study-ray",
          stroke: cool(fieldScalar(ray.color_scalar)),
          "data-field-height": ray.field_height_mm,
        }),
      );
      if (ray.first_blocked)
        plot.svg.append(
          svgNode("circle", {
            cx: geometry.x(ray.first_blocked.z_mm),
            cy: geometry.y(ray.first_blocked.y_mm),
            r: 3,
            class: "owl-study-death",
            "data-stop-id": ray.first_blocked.stop_id,
          }),
        );
    }
    for (const ray of diagram.distinguished_paths)
      plot.svg.append(
        svgNode("path", {
          d: pathData(ray.z_mm, ray.y_mm, geometry.x, geometry.y),
          class: `owl-study-distinguished owl-study-${ray.kind}`,
        }),
      );
    for (const stop of diagram.stops) {
      jaws(plot.svg, geometry, stop.z_mm, stop.radius_mm);
      plot.svg.append(
        svgNode(
          "text",
          {
            x: geometry.x(stop.z_mm),
            y: geometry.bottom - 6,
            "text-anchor": "middle",
            class: "owl-study-stop-label",
          },
          `z=${fmt(stop.z_mm)}  A=${stop.A_pupil >= 0 ? "+" : ""}${fmt(stop.A_pupil)}  B=${stop.B_field >= 0 ? "+" : ""}${fmt(stop.B_field)}`,
        ),
      );
    }
    vertical(
      plot.svg,
      geometry,
      2 * result.spec.relay_distance_mm,
      "owl-study-image-plane",
    );
    diagrams.content.append(plot.figure);
  }

  const illumination = result.illumination;
  const illumPlot = plotFrame({
    label: "Same aperture stop; only the second stop position differs",
    description:
      "Relative illumination versus object field height for aperture-only, field-stop, and vignetting configurations. The aperture-only curve stays flat, the field-stop curve cuts off sharply, and the vignetting curve rolls off gradually.",
    illumination: true,
  });
  const illumSvg = illumPlot.svg;
  illumSvg.setAttribute("viewBox", "0 0 760 250");
  const box = { left: 58, right: 746, top: 15, bottom: 210 };
  const ix = scale(
    [illumination.field_heights_mm[0], illumination.field_heights_mm.at(-1)],
    [box.left, box.right],
  );
  const iy = scale([-0.04, 1.1], [box.bottom, box.top]);
  for (const value of ticks(
    [illumination.field_heights_mm[0], illumination.field_heights_mm.at(-1)],
    5,
  )) {
    illumSvg.append(
      svgNode("line", {
        x1: ix(value),
        x2: ix(value),
        y1: box.top,
        y2: box.bottom,
        class: "owl-study-grid",
      }),
      svgNode(
        "text",
        { x: ix(value), y: box.bottom + 16, "text-anchor": "middle" },
        fmt(value),
      ),
    );
  }
  for (const value of [0, 0.5, 1])
    illumSvg.append(
      svgNode("line", {
        x1: box.left,
        x2: box.right,
        y1: iy(value),
        y2: iy(value),
        class: value === 0 ? "owl-study-axis" : "owl-study-grid",
      }),
      svgNode(
        "text",
        { x: box.left - 7, y: iy(value) + 3, "text-anchor": "end" },
        fmt(value),
      ),
    );
  illumSvg.append(
    svgNode(
      "text",
      { x: (box.left + box.right) / 2, y: 243, "text-anchor": "middle" },
      "object field height (mm)",
    ),
    svgNode(
      "text",
      {
        x: 12,
        y: (box.top + box.bottom) / 2,
        transform: `rotate(-90 12 ${(box.top + box.bottom) / 2})`,
        "text-anchor": "middle",
      },
      "relative illumination",
    ),
  );
  const curveColors = {
    aperture_only: "#1767b4",
    field_stop: "#d14a3a",
    vignette_stop: "#26865d",
  };
  for (const curve of illumination.curves)
    illumSvg.append(
      svgNode("path", {
        d: pathData(illumination.field_heights_mm, curve.relative, ix, iy),
        class: "owl-study-illumination-line",
        stroke: curveColors[curve.id] || "#1767b4",
        "data-curve-id": curve.id,
      }),
    );
  for (const edge of [
    -result.spec.field_stop_radius_mm,
    result.spec.field_stop_radius_mm,
  ])
    illumSvg.append(
      svgNode("line", {
        x1: ix(edge),
        x2: ix(edge),
        y1: box.top,
        y2: box.bottom,
        stroke: curveColors.field_stop,
        "stroke-dasharray": "2 4",
        opacity: "0.75",
      }),
    );
  diagrams.content.append(illumPlot.figure);
  diagrams.root.append(
    legend([
      ["owl-study-key-gradient", "Cyan → magenta: low → high field height"],
      ["owl-study-key-blocked", "Red dot: first blocking stop"],
      ["owl-study-key-reference", "Dotted marginal / dashed chief ray"],
    ]),
  );
  if (sectionName !== "pupils") root.append(diagrams.root);

  const pupils = section(
    "Exit pupil by field height",
    "Yellow samples pass both stops; dark red samples are rejected. Cyan is the aperture stop and dashed red is the vignette stop projected into pupil coordinates.",
    "owl-study-matrix owl-study-pupil-matrix",
  );
  const pupilMaps =
    sectionName === "pupils"
      ? [
          localSelector(
            pupils.root,
            "Field height",
            result.pupil_maps,
            (pupil) => pupil.field_height_mm,
            (pupil) => `${fmt(pupil.field_height_mm)} mm`,
            selections.pupils,
            redraw,
          ),
        ]
      : result.pupil_maps;
  for (const pupil of pupilMaps) {
    const frame = plotFrame({
      label: `field h = ${fmt(pupil.field_height_mm)} mm · passes ${pct(pupil.relative_pass)}`,
      description: `Exit pupil at field height ${fmt(pupil.field_height_mm)} millimetres. Yellow points pass and dark red points are rejected. Cyan outlines the aperture stop; dashed red outlines the projected vignette stop. Relative transmission is ${pct(pupil.relative_pass)}.`,
      square: true,
    });
    const geometry = axes(frame.svg, [-1, 1], [-1, 1], {
      square: true,
      xLabel: "pupil x (mm)",
      yLabel: "pupil y (mm)",
    });
    pupil.sample.x_mm.forEach((xValue, index) =>
      frame.svg.append(
        svgNode("circle", {
          cx: geometry.x(xValue),
          cy: geometry.y(pupil.sample.y_mm[index]),
          r: 1.25,
          fill: pupil.sample.pass[index] ? "#ffc844" : "#7d3030",
          class: pupil.sample.pass[index]
            ? "owl-study-pupil-pass"
            : "owl-study-pupil-blocked",
        }),
      ),
    );
    for (const projected of pupil.projected_stop_circles)
      circle(
        frame.svg,
        geometry,
        projected.center_x_mm,
        projected.center_y_mm,
        projected.radius_mm,
        projected.stop_id === "aperture"
          ? "owl-study-circle-aperture"
          : "owl-study-circle-vignette",
      );
    pupils.content.append(frame.figure);
  }
  pupils.root.append(
    legend([
      ["owl-study-key-gradient", "Yellow: passes"],
      ["owl-study-key-blocked", "Dark red: rejected"],
      ["owl-study-key-reference", "Cyan aperture / dashed red projected stop"],
    ]),
  );
  if (sectionName !== "rays") root.append(pupils.root);
}

const APERTURE_CONTROLS = [
  { key: "waist_mm", label: "Waist (mm)", step: 0.001, positive: true },
  { key: "wavelength_nm", label: "Wavelength (nm)", step: 1, positive: true },
  { key: "distance_mm", label: "Distance (mm)", positive: true },
  { key: "focal_length_mm", label: "Focal length (mm)", positive: true },
  { key: "grid_size", label: "FFT grid", choices: [64, 128, 256, 512] },
  { key: "window_mm", label: "FFT window (mm)", positive: true },
  {
    key: "longitudinal_samples",
    label: "Longitudinal samples",
    step: 1,
    integer: true,
    min: 16,
  },
  { key: "ray_count", label: "Ray count", step: 1, integer: true, min: 1 },
];
const STOP_CONTROLS = [
  { key: "focal_length_mm", label: "Focal length (mm)", positive: true },
  { key: "relay_distance_mm", label: "Relay distance (mm)", positive: true },
  { key: "aperture_stop_z_mm", label: "Aperture stop z (mm)", min: 0 },
  {
    key: "aperture_stop_radius_mm",
    label: "Aperture radius (mm)",
    positive: true,
  },
  { key: "field_stop_z_mm", label: "Field stop z (mm)", min: 0 },
  { key: "field_stop_radius_mm", label: "Field radius (mm)", positive: true },
  { key: "vignette_stop_z_mm", label: "Vignette stop z (mm)", min: 0 },
  {
    key: "vignette_stop_radius_mm",
    label: "Vignette radius (mm)",
    positive: true,
  },
  { key: "pupil_count", label: "Pupil rays", choices: [5000, 20000, 50000] },
];

function controlsFor(kind, sectionName) {
  const definitions =
    kind === "aperture_study" ? APERTURE_CONTROLS : STOP_CONTROLS;
  const hiddenKeys = {
    focus: new Set(["ray_count"]),
    comparison: new Set(["longitudinal_samples"]),
    rays: new Set(["pupil_count"]),
    pupils: new Set(["field_stop_z_mm", "field_stop_radius_mm"]),
  };
  const hidden = hiddenKeys[sectionName];
  return hidden
    ? definitions.filter((definition) => !hidden.has(definition.key))
    : definitions;
}

function mountControls(model, kind, sectionName, container, errorRegion) {
  const definitions = controlsFor(kind, sectionName);
  let localError = "";
  const showError = () => {
    errorRegion.textContent = localError || model.get("error") || "";
    errorRegion.hidden = !errorRegion.textContent;
  };
  const submit = (definition, input) => {
    const value = definition.choices
      ? Number(input.value)
      : input.valueAsNumber;
    const invalid =
      !input.validity.valid ||
      !Number.isFinite(value) ||
      (definition.positive && value <= 0) ||
      (definition.min !== undefined && value < definition.min) ||
      (definition.integer && !Number.isInteger(value));
    if (invalid) {
      const rule = definition.positive
        ? "a finite positive number"
        : definition.integer
          ? `an integer of at least ${definition.min}`
          : `a finite number of at least ${definition.min}`;
      localError = `${definition.label}: enter ${rule}.`;
      input.setAttribute("aria-invalid", "true");
      showError();
      return;
    }
    input.removeAttribute("aria-invalid");
    localError = "";
    const settings = clone(model.get("settings"));
    settings[definition.key] = value;
    model.set("settings", settings);
    model.save_changes();
    showError();
  };
  const draw = () => {
    const active = container.contains(document.activeElement)
      ? document.activeElement.dataset.key
      : null;
    const settings = model.get("settings") || {};
    const fields = definitions.map((definition) => {
      const wrapper = node("label", { class: "owl-study-field" });
      let input;
      if (definition.choices) {
        input = node("select", {
          "data-key": definition.key,
          "aria-label": definition.label,
        });
        for (const choice of definition.choices)
          input.append(
            node("option", { value: choice }, choice.toLocaleString()),
          );
        input.value = settings[definition.key];
      } else {
        input = node("input", {
          type: "number",
          step: definition.step ?? "any",
          "data-key": definition.key,
        });
        if (definition.positive) input.min = Number.MIN_VALUE;
        else if (definition.min !== undefined) input.min = definition.min;
        input.value = settings[definition.key] ?? "";
      }
      input.addEventListener("change", () => submit(definition, input));
      wrapper.append(node("span", {}, definition.label), input);
      return wrapper;
    });
    container.replaceChildren(...fields);
    if (kind === "aperture_study") {
      const ratios = (settings.aperture_diameter_ratios || [])
        .map((ratio) => (ratio === null ? "none" : `${fmt(ratio)} wL`))
        .join(" · ");
      container.append(
        node(
          "p",
          {
            class: "owl-study-fixed",
            "aria-label": "Fixed aperture diameter ratios",
          },
          `Apertures: ${ratios}`,
        ),
      );
    }
    if (active) container.querySelector(`[data-key="${active}"]`)?.focus();
    localError = "";
    showError();
  };
  model.on("change:settings", draw);
  model.on("change:error", showError);
  draw();
  showError();
  return () => {
    model.off("change:settings", draw);
    model.off("change:error", showError);
  };
}

export function render({ model, el }) {
  const kind = model.get("view_kind");
  const requestedSection = model.get("section") || "all";
  const allowedSections = {
    aperture_study: new Set(["focus", "comparison"]),
    stop_study: new Set(["rays", "pupils"]),
  };
  const sectionName = allowedSections[kind]?.has(requestedSection)
    ? requestedSection
    : "all";
  const names = {
    aperture_study: {
      all: [
        "Aperture study",
        "Fresnel diffraction and geometric-ray comparison",
      ],
      focus: ["Aperture focus", "Fresnel focus sweep"],
      comparison: ["Aperture comparison", "Rays and waves at the image plane"],
    },
    stop_study: {
      all: ["Stop study", "Aperture, field-stop, and vignetting geometry"],
      rays: ["Stop rays", "Stop geometry and relative illumination"],
      pupils: ["Exit pupils", "Pupil maps by field height"],
    },
  };
  const [title, subtitle] = names[kind]?.[sectionName] || [
    "Optics study",
    "Structured optical result",
  ];
  const root = node("section", {
    class: `owl-study owl-${kind.replaceAll("_", "-")}${sectionName === "all" ? "" : " owl-study-section-view"}`,
    "data-section": sectionName,
    "aria-labelledby": `owl-study-title-${++studyId}`,
  });
  const header = node("header", { class: "owl-study-header" });
  const heading = node("strong", { id: `owl-study-title-${studyId}` }, title);
  header.append(heading, node("span", {}, subtitle));
  const controls = node("div", {
    class: "owl-study-controls",
    "aria-label": `${title} settings`,
  });
  const errorRegion = node("p", {
    class: "owl-study-error",
    role: "alert",
    "aria-live": "polite",
  });
  const body = node("div");
  root.append(header, controls, errorRegion, body);
  el.append(root);
  const destroyControls = mountControls(
    model,
    kind,
    sectionName,
    controls,
    errorRegion,
  );
  const selections = {
    focus: {},
    comparison: {},
    rays: {},
    pupils: {},
  };
  function draw() {
    body.replaceChildren();
    try {
      if (kind === "aperture_study")
        renderAperture(
          body,
          model.get("result"),
          sectionName,
          selections,
          draw,
        );
      else if (kind === "stop_study")
        renderStop(body, model.get("result"), sectionName, selections, draw);
      else throw new Error(`Unsupported study view_kind: ${kind}`);
    } catch (error) {
      body.append(
        node(
          "p",
          { class: "owl-study-error", role: "alert" },
          error instanceof Error ? error.message : "Unable to render study.",
        ),
      );
    }
  }
  model.on("change:result", draw);
  draw();
  return () => {
    model.off("change:result", draw);
    destroyControls();
    root.remove();
  };
}

export default { render };
