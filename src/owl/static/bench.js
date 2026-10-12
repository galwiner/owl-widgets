// Rendering and editing only: every optical trace comes from owl.core.
const NS = "http://www.w3.org/2000/svg";
const fmt = (value) => String(Number(Number(value).toPrecision(4)));
const clone = (value) => JSON.parse(JSON.stringify(value));
let plotId = 0;

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
  const position = Math.max(0, Math.min(1, value)) * (stops.length - 1);
  const index = Math.min(stops.length - 2, Math.floor(position));
  const mix = position - index;
  return stops[index].map((channel, i) =>
    Math.round(channel + (stops[index + 1][i] - channel) * mix),
  );
}

function validLongitudinal(data) {
  return (
    Array.isArray(data?.z_mm) &&
    data.z_mm.length > 0 &&
    Array.isArray(data.x_mm) &&
    data.x_mm.length > 0 &&
    data.intensity?.length === data.z_mm.length &&
    data.intensity.every(
      (row) => Array.isArray(row) && row.length === data.x_mm.length,
    )
  );
}

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

export function render({ model, el }) {
  if (model.get("view_kind") === "cross_section") {
    const section = mountCrossSection(el);
    const refresh = () => section.update(model.get("result"));
    model.on("change:result", refresh);
    refresh();
    return () => {
      model.off("change:result", refresh);
      section.destroy();
    };
  }
  const root = node("section", {
    class: "owl-bench",
    "aria-label": "Optical bench",
  });
  const heading = node("header", { class: "owl-bench-header" });
  heading.append(
    node("strong", {}, "Optical bench"),
    node("span", {}, "Paraxial optics · input in air · M²=1"),
  );
  const controls = node("div", { class: "owl-bench-controls" });
  const elements = node("div", { class: "owl-bench-elements" });
  const toolbar = node("div", { class: "owl-bench-toolbar" });
  const error = node("p", {
    class: "owl-bench-error",
    role: "alert",
    "aria-live": "polite",
  });
  const plot = svgNode("svg", {
    viewBox: "0 0 720 310",
    role: "img",
    "aria-label":
      "Ray heights and Gaussian beam radius along the optical axis, in millimetres",
  });
  const legend = node("div", { class: "owl-bench-legend" });
  const viewControl = node("label", { class: "owl-bench-view" });
  const viewSelect = node("select", { "aria-label": "Trace view" });
  const clipId = `owl-bench-plot-${++plotId}`;
  let physicalModes = false;
  function setViewOptions(hasPhysical) {
    if (physicalModes === hasPhysical && viewSelect.options.length) return;
    const previous = viewSelect.value;
    physicalModes = hasPhysical;
    const options = hasPhysical
      ? [
          ["physical", "Physical optics"],
          ["physical-rays", "Rays + physical optics"],
          ["rays", "Rays"],
          ["gaussian-reference", "Unclipped Gaussian reference"],
        ]
      : [
          ["both", "Both traces"],
          ["rays", "Rays"],
          ["gaussian", "Gaussian"],
        ];
    viewSelect.replaceChildren(
      ...options.map(([value, label]) => node("option", { value }, label)),
    );
    viewSelect.value = options.some(([value]) => value === previous)
      ? previous
      : hasPhysical
        ? "physical-rays"
        : "both";
  }
  setViewOptions(false);
  viewControl.append(node("span", {}, "Show"), viewSelect);
  viewSelect.addEventListener("change", drawPlot);
  const metrics = node("p", {
    class: "owl-bench-metrics",
    "aria-live": "polite",
  });
  root.append(
    heading,
    controls,
    elements,
    toolbar,
    error,
    viewControl,
    plot,
    legend,
    metrics,
  );
  el.append(root);
  const crossSection = mountCrossSection(root);
  let localError = "";

  function showError() {
    error.textContent = localError || model.get("error") || "";
    error.hidden = !error.textContent;
  }
  function update(edit) {
    const settings = clone(model.get("settings"));
    edit(settings);
    localError = "";
    model.set("settings", settings);
    model.save_changes();
    showError();
  }
  function field(
    label,
    value,
    key,
    edit,
    { min, step = "any", positive = false } = {},
  ) {
    const wrapper = node("label", { class: "owl-bench-field" });
    const input = node("input", { type: "number", step, "data-key": key });
    if (min !== undefined) input.min = min;
    input.value = value;
    input.addEventListener("change", () => {
      if (
        !input.validity.valid ||
        !Number.isFinite(input.valueAsNumber) ||
        (positive && input.valueAsNumber <= 0)
      ) {
        localError = `${label}: enter a finite${positive ? " positive number" : min !== undefined ? ` number ≥ ${min}` : " number"}.`;
        input.setAttribute("aria-invalid", "true");
        showError();
        return;
      }
      input.removeAttribute("aria-invalid");
      update((settings) => edit(settings, input.valueAsNumber));
    });
    wrapper.append(node("span", {}, label), input);
    return wrapper;
  }
  function sliderField(label, value, key, edit, min, max, unit, step) {
    const group = node("div", { class: "owl-bench-slider-field" });
    const digits = step === 1 ? 0 : 3;
    const format = (number) => Number(number).toFixed(digits);
    const roundedEdit = (settings, number) =>
      edit(settings, Number(format(number)));
    const numeric = field(label, format(value), key, roundedEdit, { min: 0 });
    const sliderLabel = node("label", { class: "owl-bench-slider" });
    // Keep controls on a unit-aligned grid without rounding Python core inputs.
    const slider = node("input", {
      type: "range",
      min: Number(
        (Math.floor(Math.min(min, value) / step) * step).toPrecision(12),
      ),
      max: Number(
        (Math.ceil(Math.max(max, value) / step) * step).toPrecision(12),
      ),
      step,
      "data-key": `${key}-slider`,
      "aria-label": `${label} slider`,
    });
    slider.value = value;
    const indicator = node("output", {}, `${format(value)} ${unit}`);
    slider.addEventListener("input", () => {
      indicator.value = `${format(slider.value)} ${unit}`;
      numeric.querySelector("input").value = format(slider.value);
    });
    slider.addEventListener("change", () => {
      update((settings) => roundedEdit(settings, slider.valueAsNumber));
    });
    sliderLabel.append(slider, indicator);
    group.append(numeric, sliderLabel);
    return group;
  }
  function button(label, action) {
    const result = node("button", { type: "button" }, label);
    result.addEventListener("click", action);
    return result;
  }
  function drawControls() {
    const active = root.contains(document.activeElement)
      ? document.activeElement.dataset.key
      : null;
    const s = model.get("settings");
    localError = "";
    showError();
    controls.replaceChildren(
      sliderField(
        "Wavelength (nm)",
        s.beam.wavelength_nm,
        "wavelength",
        (s, v) => {
          s.beam.wavelength_nm = v;
        },
        200,
        2000,
        "nm",
        1,
      ),
      sliderField(
        "Input waist (mm)",
        s.beam.waist_mm,
        "waist",
        (s, v) => {
          s.beam.waist_mm = v;
        },
        0.01,
        1,
        "mm",
        0.001,
      ),
      field(
        "Ray half-span (mm)",
        s.ray_span_mm,
        "span",
        (s, v) => {
          s.ray_span_mm = v;
        },
        { min: 0 },
      ),
      field(
        "Ray count",
        s.ray_count,
        "count",
        (s, v) => {
          s.ray_count = v;
        },
        { min: 1, step: 1 },
      ),
    );
    const wave = { grid_size: 128, window_mm: null, ...s.wave };
    const editWave = (settings, key, value) => {
      settings.wave = {
        grid_size: 128,
        window_mm: null,
        ...settings.wave,
        [key]: value,
      };
    };
    const gridLabel = node("label", { class: "owl-bench-field" });
    const grid = node("select", { "data-key": "wave-grid" });
    for (const size of [64, 128, 256, 512])
      grid.append(node("option", { value: size }, `${size} × ${size}`));
    grid.value = wave.grid_size;
    grid.addEventListener("change", () =>
      update((s) => editWave(s, "grid_size", Number(grid.value))),
    );
    gridLabel.append(node("span", {}, "FFT grid"), grid);
    const windowGroup = node("div", { class: "owl-bench-wave-window" });

    const windowField = field(
      "FFT window (mm)",
      wave.window_mm ?? "",
      "wave-window",
      (s, v) => editWave(s, "window_mm", v),
      { min: 0, positive: true },
    );
    const windowInput = windowField.querySelector("input");
    windowInput.disabled = wave.window_mm === null;
    windowInput.placeholder = "Auto";
    const autoLabel = node("label", { class: "owl-bench-flat" });
    const auto = node("input", {
      type: "checkbox",
      "data-key": "wave-window-auto",
      "aria-label": "FFT window: Auto",
    });
    auto.checked = wave.window_mm === null;
    // Start manual sizing from the backend's current auto window when available.
    auto.addEventListener("change", () => {
      const computedWindow = model.get("result")?.cross_sections?.window_mm;
      const manualWindow =
        Number.isFinite(computedWindow) && computedWindow > 0
          ? computedWindow
          : 1;
      update((s) =>
        editWave(s, "window_mm", auto.checked ? null : manualWindow),
      );
    });
    autoLabel.append(auto, node("span", {}, "Auto"));
    windowGroup.append(windowField, autoLabel);
    controls.append(gridLabel, windowGroup);
    elements.replaceChildren();
    s.system.elements.forEach((item, index) => {
      const names = {
        free_space: "Gap",
        thin_lens: "Thin lens",
        mirror: "Mirror",
        interface: "Interface",
        thick_lens: "Thick lens",
        aperture: "Aperture",
      };
      const name = `${index + 1}. ${names[item.type]}`;
      const row = node("div", {
        class: "owl-bench-element",
        role: "group",
        "aria-label": name,
      });
      row.append(node("strong", { class: "owl-bench-element-title" }, name));
      const addField = (key, label, options = {}, radius = false) => {
        const dataKey = ["distance_mm", "focal_length_mm"].includes(key)
          ? `element-${index}`
          : `element-${index}-${key}`;
        const edit = (s, v) => {
          s.system.elements[index][key] = v;
        };
        const control = field(label, item[key] ?? "", dataKey, edit, options);
        if (radius) {
          const input = control.querySelector("input");
          input.disabled = item[key] === null;
          const flatLabel = node("label", { class: "owl-bench-flat" });
          const flat = node("input", {
            type: "checkbox",
            "data-key": `${dataKey}-flat`,
            "aria-label": `${label}: Flat`,
          });
          flat.checked = item[key] === null;
          flat.addEventListener("change", () =>
            update((s) => edit(s, flat.checked ? null : 100)),
          );
          flatLabel.append(flat, node("span", {}, "Flat"));
          const group = node("div", { class: "owl-bench-radius" });
          group.append(control, flatLabel);
          row.append(group);
        } else row.append(control);
      };
      if (item.type === "free_space")
        addField("distance_mm", "Gap distance (mm)", { min: 0 });
      if (item.type === "thin_lens")
        addField("focal_length_mm", "Thin lens focal length (mm)");
      if (["mirror", "interface"].includes(item.type))
        addField("radius_mm", "Radius (mm)", {}, true);
      if (item.type === "interface") {
        addField("n1", "Incident refractive index (n1)", { min: 0 });
        addField("n2", "Exit refractive index (n2)", { min: 0 });
      }
      if (item.type === "thick_lens") {
        addField("radius1_mm", "Entry radius (mm)", {}, true);
        addField("radius2_mm", "Exit radius (mm)", {}, true);
        addField("thickness_mm", "Thickness (mm)", { min: 0 });
        addField("n", "Lens refractive index (n)", { min: 0 });
      }
      if (item.type === "aperture") {
        addField("radius_mm", "Aperture radius (mm)", { min: 0 });
        addField("x_mm", "Transverse x offset (mm)");
        addField("y_mm", "Transverse y offset (mm)");
      }
      for (const [direction, delta] of [
        ["up", -1],
        ["down", 1],
      ]) {
        const destination = index + delta;
        const move = button(`Move ${direction}`, () => {
          update((s) => {
            const [element] = s.system.elements.splice(index, 1);
            s.system.elements.splice(destination, 0, element);
          });
          const moved = elements.children[destination];
          const same = moved.querySelector(`[data-move="${direction}"]`);
          (same.disabled
            ? moved.querySelector("input:not(:disabled)")
            : same
          ).focus();
        });
        move.dataset.move = direction;
        move.setAttribute(
          "aria-label",
          `Move element ${index + 1} ${direction}`,
        );
        move.disabled =
          destination < 0 || destination >= s.system.elements.length;
        row.append(move);
      }
      const remove = button("Remove", () => {
        update((s) => s.system.elements.splice(index, 1));
        const next = elements.children[
          Math.min(index, elements.children.length - 1)
        ]?.querySelector("input:not(:disabled)");
        (next || toolbar.firstElementChild).focus();
      });
      remove.setAttribute("aria-label", `Remove element ${index + 1}`);
      row.append(remove);
      elements.append(row);
    });
    if (!s.system.elements.length)
      elements.append(
        node(
          "p",
          { class: "owl-bench-empty" },
          "Input plane only. Add an element to start a sequence.",
        ),
      );
    if (active)
      Array.from(root.querySelectorAll("input, select"))
        .find((input) => input.dataset.key === active)
        ?.focus();
  }
  toolbar.append(
    button("+ Aperture", () =>
      update((s) =>
        s.system.elements.push({
          type: "aperture",
          radius_mm: 0.1,
          x_mm: 0,
          y_mm: 0,
        }),
      ),
    ),
    button("+ Gap", () =>
      update((s) =>
        s.system.elements.push({ type: "free_space", distance_mm: 100 }),
      ),
    ),
    button("+ Thin lens", () =>
      update((s) =>
        s.system.elements.push({ type: "thin_lens", focal_length_mm: 100 }),
      ),
    ),
    button("+ Mirror", () =>
      update((s) => s.system.elements.push({ type: "mirror", radius_mm: 100 })),
    ),
    button("+ Interface", () =>
      update((s) => {
        let n = 1;
        for (const item of s.system.elements) {
          if (item.type === "interface") n = item.n2;
          if (item.type === "thick_lens") n = 1;
        }
        s.system.elements.push({
          type: "interface",
          radius_mm: 100,
          n1: n,
          n2: n === 1 ? 1.5 : 1,
        });
      }),
    ),
    button("+ Thick lens", () =>
      update((s) =>
        s.system.elements.push({
          type: "thick_lens",
          radius1_mm: 60,
          radius2_mm: -60,
          thickness_mm: 10,
          n: 1.5,
        }),
      ),
    ),
    node(
      "span",
      {},
      "Encounter order: add mirror-return elements explicitly. Mirrors reverse the axial direction; no automatic intersection tracing. Negative focal length = diverging thin lens.",
    ),
  );

  function drawPlot() {
    const r = model.get("result");
    crossSection.update(r?.cross_sections);
    if (!r?.rays || !r?.gaussian) return;
    const hasPhysical = validLongitudinal(r.longitudinal);
    setViewOptions(hasPhysical);
    const showPhysical =
      hasPhysical && ["physical", "physical-rays"].includes(viewSelect.value);
    const showRays = hasPhysical
      ? ["physical-rays", "rays"].includes(viewSelect.value)
      : viewSelect.value !== "gaussian";
    const showGaussian = hasPhysical
      ? viewSelect.value === "gaussian-reference"
      : viewSelect.value !== "rays";
    const hasAperture = r.elements.some((item) => item.type === "aperture");
    const gaussianLabel = hasAperture
      ? "Unclipped Gaussian reference"
      : "Gaussian";
    const descriptionParts = [];
    if (showPhysical)
      descriptionParts.push(
        "physical-optics intensity relative to input peak on a three-decade logarithmic scale",
      );
    if (showRays)
      descriptionParts.push(
        "blue right-travelling and purple left-travelling rays with direction arrows",
      );
    if (showGaussian)
      descriptionParts.push(
        `orange ${gaussianLabel} intensity 1/e² radius (±w)`,
      );
    const description = `${descriptionParts.join(" and ")}; physical x-z coordinates in millimetres.`;
    plot.setAttribute("aria-label", description);
    plot.replaceChildren(svgNode("title", {}, description));
    legend.replaceChildren();
    if (showPhysical)
      legend.append(
        node(
          "span",
          { class: "owl-bench-pop-key" },
          "Physical optics |U|² / input peak · log scale",
        ),
      );
    if (showRays) {
      legend.append(
        node("span", { class: "owl-bench-ray-key" }, "→ Rays: right"),
      );
      if (r.rays.z_mm.some((z, i, zs) => i > 0 && z < zs[i - 1]))
        legend.append(
          node("span", { class: "owl-bench-return-key" }, "← Rays: left"),
        );
    }
    if (showGaussian)
      legend.append(
        node(
          "span",
          { class: "owl-bench-beam-key" },
          `┄ ${gaussianLabel} intensity 1/e² radius (±w)`,
        ),
      );
    const left = 66,
      right = 700,
      top = 26,
      bottom = 262;
    let minZ = 0,
      maxZ = 0;
    for (const zs of [
      r.rays.z_mm,
      r.gaussian.z_mm,
      ...(hasPhysical ? [r.longitudinal.z_mm] : []),
    ])
      for (const z of zs) {
        minZ = Math.min(minZ, z);
        maxZ = Math.max(maxZ, z);
      }
    for (const item of r.elements) {
      minZ = Math.min(minZ, item.start_z_mm ?? item.z_mm, item.z_mm);
      maxZ = Math.max(maxZ, item.start_z_mm ?? item.z_mm, item.z_mm);
    }
    if (minZ === maxZ) {
      minZ -= 0.5;
      maxZ += 0.5;
    }
    const zScale = Math.max(Math.abs(minZ), Math.abs(maxZ));
    const zMin = minZ / zScale,
      zMax = maxZ / zScale;
    let extent = 0.001;
    if (showRays)
      for (const [sample, row] of r.rays.y_mm.entries())
        for (const [ray, height] of row.entries())
          if (sample === 0 || r.rays.alive?.[sample - 1]?.[ray] !== false)
            extent = Math.max(extent, Math.abs(height));
    for (const item of r.elements)
      if (item.type === "aperture")
        extent = Math.max(extent, Math.abs(item.y_mm ?? 0) + item.radius_mm);
    if (showGaussian)
      for (const y of r.gaussian.radius_mm) extent = Math.max(extent, y);
    let minHeight = -extent,
      maxHeight = extent;
    if (showPhysical) {
      minHeight = Math.min(...r.longitudinal.x_mm);
      maxHeight = Math.max(...r.longitudinal.x_mm);
      if (minHeight === maxHeight) {
        const halfWindow = (r.longitudinal.window_mm || 1) / 2;
        minHeight -= halfWindow;
        maxHeight += halfWindow;
      }
    }
    // Normalize before multiplying so finite physical values stay finite in SVG.
    const x = (z) =>
      left + ((z / zScale - zMin) / (zMax - zMin)) * (right - left);
    const y = showPhysical
      ? (height) =>
          bottom -
          ((height - minHeight) / (maxHeight - minHeight)) * (bottom - top)
      : (height) =>
          (top + bottom) / 2 - ((height / extent) * (bottom - top)) / 2 / 1.12;
    if (showPhysical) {
      const width = Math.round(right - left);
      const height = r.longitudinal.x_mm.length;
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      context.fillStyle = "rgb(0, 0, 4)";
      context.fillRect(0, 0, width, height);
      for (let sample = 0; sample < r.longitudinal.z_mm.length; sample++) {
        const z0 = r.longitudinal.z_mm[sample];
        const z1 =
          r.longitudinal.z_mm[sample + 1] ??
          (sample ? z0 + (z0 - r.longitudinal.z_mm[sample - 1]) : maxZ);
        const start = Math.max(
          0,
          Math.min(
            width,
            Math.floor(((Math.min(z0, z1) - minZ) / (maxZ - minZ)) * width),
          ),
        );
        const end = Math.max(
          start + 1,
          Math.min(
            width,
            Math.ceil(((Math.max(z0, z1) - minZ) / (maxZ - minZ)) * width),
          ),
        );
        const row = r.longitudinal.intensity[sample];
        for (let transverse = 0; transverse < height; transverse++) {
          const intensity = Number.isFinite(row[transverse])
            ? Math.max(0, row[transverse])
            : 0;
          const level =
            intensity > 0
              ? Math.max(0, Math.min(1, (Math.log10(intensity) + 3) / 3))
              : 0;
          context.fillStyle = `rgb(${inferno(level).join(",")})`;
          context.fillRect(start, height - 1 - transverse, end - start, 1);
        }
      }
      const defs = svgNode("defs");
      const clip = svgNode("clipPath", { id: clipId });
      clip.append(
        svgNode("rect", {
          x: left,
          y: top,
          width: right - left,
          height: bottom - top,
        }),
      );
      defs.append(clip);
      plot.append(defs);
      const image = svgNode("image", {
        class: "owl-bench-pop",
        href: canvas.toDataURL(),
        x: left,
        y: top,
        width: right - left,
        height: bottom - top,
        preserveAspectRatio: "none",
        "clip-path": `url(#${clipId})`,
      });
      image.append(
        svgNode(
          "title",
          {},
          `Physical optics |U|² / input peak; log scale from 10⁻³ to 1; x ${fmt(minHeight)} to ${fmt(maxHeight)} mm`,
        ),
      );
      plot.append(image);
    }
    for (let tick = 0; tick <= 4; tick++) {
      const z = minZ * (1 - tick / 4) + maxZ * (tick / 4);
      plot.append(
        svgNode("line", {
          x1: x(z),
          x2: x(z),
          y1: top,
          y2: bottom,
          class: "owl-bench-grid",
        }),
      );
      plot.append(
        svgNode(
          "text",
          {
            x: x(z),
            y: bottom + 20,
            "text-anchor": tick === 4 ? "end" : "middle",
          },
          fmt(z),
        ),
      );
    }
    const heightTicks = showPhysical
      ? [minHeight, (minHeight + maxHeight) / 2, maxHeight]
      : [-extent, 0, extent];
    for (const height of heightTicks) {
      plot.append(
        svgNode("line", {
          x1: left,
          x2: right,
          y1: y(height),
          y2: y(height),
          class: Math.abs(height) < 1e-12 ? "owl-bench-axis" : "owl-bench-grid",
        }),
      );
      plot.append(
        svgNode(
          "text",
          { x: left - 8, y: y(height) + 4, "text-anchor": "end" },
          fmt(height),
        ),
      );
    }
    plot.append(
      svgNode(
        "text",
        { x: left, y: 15 },
        showPhysical ? "x (mm)" : "height (mm)",
      ),
      svgNode(
        "text",
        { x: (left + right) / 2, y: 303, "text-anchor": "middle" },
        "z (mm)",
      ),
    );
    for (const item of r.elements) {
      if (item.type === "aperture") {
        const offsetX = item.x_mm ?? 0;
        const offsetY = item.y_mm ?? 0;
        // Intersect the circular clear opening with the meridional x=0 plane.
        const halfOpening =
          Math.abs(offsetX) < item.radius_mm
            ? item.radius_mm * Math.sqrt(1 - (offsetX / item.radius_mm) ** 2)
            : 0;
        const upper = Math.max(top, Math.min(bottom, y(offsetY + halfOpening)));
        const lower = Math.max(top, Math.min(bottom, y(offsetY - halfOpening)));
        for (const [barTop, barBottom] of [
          [top, upper],
          [lower, bottom],
        ]) {
          const bar = svgNode("rect", {
            x: x(item.z_mm) - 3,
            y: barTop,
            width: 6,
            height: barBottom - barTop,
            class: "owl-bench-aperture",
          });
          bar.append(
            svgNode(
              "title",
              {},
              `${item.label ?? "Aperture"}: meridional x=0${halfOpening ? "" : "; no clear opening"}`,
            ),
          );
          plot.append(bar);
        }
        continue;
      }
      const classes = {
        thin_lens: "owl-bench-lens",
        mirror: "owl-bench-mirror",
        interface: "owl-bench-interface",
        thick_lens: "owl-bench-thick-lens",
      };
      if (!classes[item.type]) continue;
      const start = x(item.start_z_mm ?? item.z_mm),
        end = x(item.z_mm);
      const lens =
        item.type === "thick_lens"
          ? svgNode("rect", {
              x: Math.min(start, end),
              y: top,
              width: Math.abs(end - start),
              height: bottom - top,
              class: classes[item.type],
            })
          : svgNode("line", {
              x1: end,
              x2: end,
              y1: top,
              y2: bottom,
              class: classes[item.type],
            });
      lens.append(svgNode("title", {}, item.label));
      plot.append(lens);
    }
    const path = (zs, heights, className) => {
      const d = zs
        .map((z, i) => `${i ? "L" : "M"}${x(z)},${y(heights[i])}`)
        .join(" ");
      plot.append(svgNode("path", { d, class: className }));
    };
    if (showRays) {
      for (let ray = 0; ray < (r.rays.y_mm[0]?.length ?? 0); ray++) {
        for (let i = 1; i < r.rays.z_mm.length; i++) {
          // Keep the segment arriving at the stop; omit travel after interception.
          if (r.rays.alive?.[i - 1]?.[ray] === false) break;
          const z0 = r.rays.z_mm[i - 1],
            z1 = r.rays.z_mm[i];
          // Interfaces change angle at a single plane, not travel direction.
          if (z0 === z1) continue;
          const returning = z1 < z0;
          const direction = returning ? "left" : "right";
          const className = `owl-bench-ray${returning ? " owl-bench-ray-return" : ""}`;
          const x0 = x(z0),
            y0 = y(r.rays.y_mm[i - 1][ray]);
          const x1 = x(z1),
            y1 = y(r.rays.y_mm[i][ray]);
          plot.append(
            svgNode("path", {
              d: `M${x0},${y0} L${x1},${y1}`,
              class: className,
              "data-direction": direction,
            }),
          );
          const dx = x1 - x0,
            dy = y1 - y0;
          const length = Math.hypot(dx, dy);
          if (length < 16) continue;
          const ux = dx / length,
            uy = dy / length;
          // Offset from centre so retraced forward/return arrows remain distinct.
          const cx = x0 + 0.6 * dx,
            cy = y0 + 0.6 * dy;
          plot.append(
            svgNode("path", {
              d: `M${cx - 3 * ux - 2.5 * uy},${cy - 3 * uy + 2.5 * ux} L${cx + 3 * ux},${cy + 3 * uy} L${cx - 3 * ux + 2.5 * uy},${cy - 3 * uy - 2.5 * ux}`,
              class: `owl-bench-ray-arrow${returning ? " owl-bench-ray-return" : ""}`,
              "data-direction": direction,
              "aria-hidden": "true",
            }),
          );
        }
      }
    }
    if (showGaussian)
      for (const sign of [-1, 1])
        path(
          r.gaussian.z_mm,
          r.gaussian.radius_mm.map((v) => sign * v),
          "owl-bench-beam",
        );
    metrics.textContent = [
      `Length ${fmt(r.metrics.length_mm)} mm`,
      ...(showGaussian
        ? [
            `${hasAperture ? "Unclipped Gaussian reference output radius" : "Output Gaussian radius"} ${fmt(r.metrics.output_radius_mm)} mm`,
          ]
        : []),
      ...(showRays
        ? [`Output ray half-span ${fmt(r.metrics.output_ray_half_span_mm)} mm`]
        : []),
    ].join(" · ");
  }
  model.on("change:settings", drawControls);
  model.on("change:result", drawPlot);
  model.on("change:error", showError);
  drawControls();
  drawPlot();
  showError();
  return () => {
    model.off("change:settings", drawControls);
    model.off("change:result", drawPlot);
    model.off("change:error", showError);
    crossSection.destroy();
    root.remove();
  };
}

// Shared by the Bench and standalone AnyWidget views; no blob-relative imports.
export function mountCrossSection(container) {
  const root = node("section", {
    class: "owl-bench owl-cross-section",
    "aria-label": "Beam cross section",
  });
  const header = node("header", { class: "owl-cross-section-header" });
  const planeLabel = node("label", { class: "owl-bench-view" });
  const select = node("select", { "aria-label": "Cross-section plane" });
  planeLabel.append(node("span", {}, "Plane"), select);
  const transmission = node("output", { "aria-live": "polite" });
  header.append(
    node("strong", {}, "Beam cross section"),
    planeLabel,
    transmission,
  );
  const note = node(
    "p",
    { class: "owl-cross-section-note" },
    "Intensity / input peak · fixed heatmap scale 0–1 (values above 1 saturate). Center slice at y ≈ 0 mm.",
  );
  const empty = node(
    "p",
    { class: "owl-bench-empty" },
    "Cross-section data not available yet.",
  );
  const plots = node("div", { class: "owl-cross-section-plots" });
  const heatmap = node("figure", { class: "owl-cross-section-heatmap" });
  const canvas = node("canvas", {
    role: "img",
    "aria-label": "Transverse intensity heatmap",
  });
  const xAxis = node("figcaption");
  const yAxis = node("span", { class: "owl-cross-section-y-axis" });
  heatmap.append(yAxis, canvas, xAxis);
  const slice = svgNode("svg", {
    viewBox: "0 0 360 250",
    role: "img",
    "aria-label": "Center intensity slice",
  });
  const warnings = node("ul", {
    class: "owl-cross-section-warnings",
    "aria-live": "polite",
  });
  root.append(header, note, empty, plots, warnings);
  container.append(root);
  let data,
    selected = 0,
    disposed = false;

  function draw() {
    const planes = data?.planes ?? [];
    const plane = planes[selected];
    const xs = data?.x_mm ?? [];
    const values = plane?.intensity;
    const available =
      xs.length > 0 &&
      values?.length === xs.length &&
      values.every((row) => Array.isArray(row) && row.length === xs.length);
    empty.hidden = !!available;
    note.hidden = !available;
    transmission.textContent =
      plane && Number.isFinite(plane.transmission)
        ? `Transmission ${(100 * plane.transmission).toFixed(1)}%`
        : "";
    plots.replaceChildren();
    warnings.replaceChildren();
    for (const warning of data?.warnings ?? [])
      warnings.append(node("li", {}, warning));
    warnings.hidden = !warnings.childElementCount;
    if (!available) return;
    plots.append(heatmap, slice);
    const size = xs.length;
    canvas.width = canvas.height = size;
    const context = canvas.getContext("2d");
    const image = context.createImageData(size, size);
    for (let row = 0; row < size; row++) {
      for (let col = 0; col < size; col++) {
        // Backend values already use the input peak. Never rescale by this plane.
        const intensity = Number.isFinite(values[row][col])
          ? values[row][col]
          : 0;
        const v = Math.max(0, Math.min(1, intensity));
        const pixel = 4 * ((size - 1 - row) * size + col);
        image.data.set(
          [Math.round(255 * v), Math.round(205 * v), Math.round(80 * v), 255],
          pixel,
        );
      }
    }
    context.putImageData(image, 0, 0);
    const bounds = `${fmt(xs[0])} … ${fmt(xs[size - 1])}`;
    xAxis.textContent = `x (mm): ${bounds}`;
    yAxis.textContent = `y (mm): ${bounds}`;
    canvas.setAttribute(
      "aria-label",
      `${plane.label}, z = ${fmt(plane.z_mm)} mm: intensity heatmap, x and y ${bounds} mm; fixed input peak scale 0 to 1. ${transmission.textContent}`,
    );
    let center = 0;
    xs.forEach((value, i) => {
      if (Math.abs(value) < Math.abs(xs[center])) center = i;
    });
    // Share the slice's vertical scale across all planes, including focused peaks >1.
    let peak = 1;
    for (const entry of planes)
      for (const value of entry.intensity?.[center] ?? [])
        if (Number.isFinite(value)) peak = Math.max(peak, value);
    const left = 48,
      right = 344,
      top = 30,
      bottom = 202;
    const minX = size > 1 ? xs[0] : xs[0] - (data.window_mm || 1) / 2;
    const maxX = size > 1 ? xs[size - 1] : xs[0] + (data.window_mm || 1) / 2;
    const x = (v) => left + ((v - minX) / (maxX - minX)) * (right - left);
    const y = (v) => bottom - (Math.max(0, v) / peak) * (bottom - top);
    slice.replaceChildren(
      svgNode(
        "title",
        {},
        `Center slice at y = ${fmt(xs[center])} mm; intensity relative to input peak`,
      ),
    );
    for (const v of [0, peak / 2, peak]) {
      slice.append(
        svgNode("line", {
          x1: left,
          x2: right,
          y1: y(v),
          y2: y(v),
          class: "owl-bench-grid",
        }),
        svgNode(
          "text",
          { x: left - 6, y: y(v) + 4, "text-anchor": "end" },
          fmt(v),
        ),
      );
    }
    for (const v of [minX, (minX + maxX) / 2, maxX])
      slice.append(
        svgNode(
          "text",
          {
            x: x(v),
            y: bottom + 18,
            "text-anchor": v === maxX ? "end" : "start",
          },
          fmt(v),
        ),
      );
    slice.append(
      svgNode(
        "text",
        { x: left, y: 16 },
        `I / input peak · y = ${fmt(xs[center])} mm`,
      ),
      svgNode(
        "text",
        { x: (left + right) / 2, y: 244, "text-anchor": "middle" },
        "x (mm)",
      ),
      svgNode("path", {
        class: "owl-cross-section-slice",
        d: xs
          .map(
            (v, i) =>
              `${i ? "L" : "M"}${x(v)},${y(Number.isFinite(values[center][i]) ? values[center][i] : 0)}`,
          )
          .join(" "),
      }),
    );
  }
  function choose() {
    selected = select.selectedIndex;
    draw();
  }
  select.addEventListener("change", choose);
  return {
    update(next) {
      if (disposed) return;
      data = next;
      const planes = data?.planes ?? [];
      selected = Math.max(0, Math.min(selected, planes.length - 1));
      select.replaceChildren(
        ...planes.map((plane, i) =>
          node(
            "option",
            { value: i },
            `${plane.label} · z = ${fmt(plane.z_mm)} mm`,
          ),
        ),
      );
      select.selectedIndex = planes.length ? selected : -1;
      // Older Bench fixtures have no cross sections, but still show an empty panel.
      if (planes.length) {
        if (planeLabel.parentNode !== header)
          header.insertBefore(planeLabel, transmission);
      } else planeLabel.remove();
      draw();
    },
    destroy() {
      disposed = true;
      select.removeEventListener("change", choose);
      data = null;
      root.remove();
    },
  };
}

export default { render };
