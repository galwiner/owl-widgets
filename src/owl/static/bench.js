// Rendering and editing only: every optical trace comes from owl.core.
const fmt = (value) => String(Number(Number(value).toPrecision(4)));
const clone = (value) => JSON.parse(JSON.stringify(value));

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
  const drawer = node("details", { class: "owl-bench-drawer" });
  const drawerSummary = node("summary", {}, "Bench setup");
  const drawerBody = node("div", { class: "owl-bench-drawer-body" });
  drawer.append(drawerSummary, drawerBody);
  const controls = node("div", { class: "owl-bench-controls" });
  const elements = node("div", { class: "owl-bench-elements" });
  const toolbar = node("div", { class: "owl-bench-toolbar" });
  const error = node("p", {
    class: "owl-bench-error",
    role: "alert",
    "aria-live": "polite",
  });
  const plot = node("div", {
    class: "owl-bench-plotly",
    role: "region",
    "aria-label": "Optical system ray and intensity plot",
  });
  const viewControl = node("label", { class: "owl-bench-view" });
  const viewSelect = node("select", { "aria-label": "Trace view" });
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
  drawerBody.append(
    heading,
    controls,
    elements,
    toolbar,
    error,
    viewControl,
    metrics,
  );
  root.append(drawer, plot);
  el.append(root);
  const crossSection = mountCrossSection(drawerBody);
  let localError = "";

  function showError() {
    error.textContent = localError || model.get("error") || "";
    error.hidden = !error.textContent;
    if (error.textContent) drawer.open = true;
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
    const result = model.get("result");
    if (!result?.rays || !result?.gaussian) return;
    const hasPhysical = validLongitudinal(result.longitudinal);
    setViewOptions(hasPhysical);
    const mode = viewSelect.value;
    void renderBenchPlot(plot, result, mode).catch((cause) => {
      plot.replaceChildren(
        node("p", { class: "owl-bench-error" }, `Plot error: ${cause.message}`),
      );
    });
    metrics.textContent = [
      `Length ${fmt(result.metrics.length_mm)} mm`,
      ...(mode === "gaussian-reference" ||
      mode === "gaussian" ||
      mode === "both"
        ? [
            `${result.elements.some((item) => item.type === "aperture") ? "Unclipped Gaussian reference" : "Gaussian"} output radius ${fmt(result.metrics.output_radius_mm)} mm`,
          ]
        : []),
      ...(["physical-rays", "rays", "both"].includes(mode)
        ? [
            `Output ray half-span ${fmt(result.metrics.output_ray_half_span_mm)} mm`,
          ]
        : []),
    ].join(" · ");
  }
  const refreshCrossSection = () =>
    crossSection.update(model.get("result")?.cross_sections);
  model.on("change:settings", drawControls);
  model.on("change:result", drawPlot);
  model.on("change:result", refreshCrossSection);
  model.on("change:error", showError);
  drawControls();
  drawPlot();
  refreshCrossSection();
  showError();
  return () => {
    model.off("change:settings", drawControls);
    model.off("change:result", drawPlot);
    model.off("change:result", refreshCrossSection);
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
    "Intensity / input peak · heatmap values above 1 saturate. Hover for local intensity; use the mode bar to zoom, pan, or reset.",
  );
  const empty = node(
    "p",
    { class: "owl-bench-empty" },
    "Cross-section data not available yet.",
  );
  const plots = node("div", { class: "owl-cross-section-plots" });
  const heatHost = node("div", {
    class: "owl-cross-section-plot",
    role: "region",
    "aria-label": "Transverse intensity heatmap",
  });
  const sliceHost = node("div", {
    class: "owl-cross-section-plot",
    role: "region",
    "aria-label": "Center intensity slice",
  });
  plots.append(heatHost, sliceHost);
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
    plots.hidden = !available;
    transmission.textContent =
      plane && Number.isFinite(plane.transmission)
        ? `Transmission ${(100 * plane.transmission).toFixed(1)}%`
        : "";
    warnings.replaceChildren(
      ...(data?.warnings ?? []).map((warning) => node("li", {}, warning)),
    );
    warnings.hidden = !warnings.childElementCount;
    if (available) {
      void renderCrossSectionPlots(
        heatHost,
        sliceHost,
        data,
        plane,
        selected,
      ).catch((cause) => {
        plots.replaceChildren(
          node(
            "p",
            { class: "owl-bench-error" },
            `Plot error: ${cause.message}`,
          ),
        );
      });
    }
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
      if (planes.length) {
        if (planeLabel.parentNode !== header)
          header.insertBefore(planeLabel, transmission);
      } else planeLabel.remove();
      draw();
    },
    destroy() {
      disposed = true;
      select.removeEventListener("change", choose);
      Plotly.purge(heatHost);
      Plotly.purge(sliceHost);
      data = null;
      root.remove();
    },
  };
}

export default { render };
