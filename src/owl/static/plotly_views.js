// Plotly renderers for the optical bench. Input arrays remain owned by Python.
const Plotly = globalThis.moduleName;
const graphConfig = {
  responsive: true,
  displaylogo: false,
  displayModeBar: true,
  scrollZoom: true,
};
const fmtPlot = (value) => String(Number(Number(value).toPrecision(4)));

function renderBenchPlot(host, result, view) {
  const physical =
    ["physical", "physical-rays"].includes(view) && result.longitudinal;
  const showRays =
    ["physical-rays", "rays"].includes(view) ||
    (!result.longitudinal && view !== "gaussian");
  const showGaussian = ["gaussian-reference", "gaussian", "both"].includes(
    view,
  );
  const traces = [];
  if (physical) {
    const data = result.longitudinal;
    const turns = [];
    let direction = 0;
    for (let i = 1; i < data.z_mm.length; i++) {
      const delta = data.z_mm[i] - data.z_mm[i - 1];
      if (delta === 0) continue;
      const nextDirection = Math.sign(delta);
      if (direction && nextDirection !== direction) {
        let turn = i - 1;
        while (turn > 0 && data.z_mm[turn] === data.z_mm[turn - 1]) turn--;
        turns.push(turn);
      }
      direction = nextDirection;
    }
    const segments = [];
    let start = 0;
    for (const turn of turns) {
      if (turn + 1 - start > 1) segments.push([start, turn + 1]);
      start = data.z_mm[turn + 1] === data.z_mm[turn] ? turn + 1 : turn;
    }
    if (data.z_mm.length - start > 1) segments.push([start, data.z_mm.length]);
    for (const [from, to] of segments) {
      const z = data.z_mm.slice(from, to);
      traces.push({
        type: "heatmap",
        name: "Physical optics |U|² / input peak",
        showlegend: false,
        showscale: from === 0,
        x: z,
        y: data.x_mm,
        z: data.x_mm.map((_, xi) =>
          data.intensity
            .slice(from, to)
            .map((row) => Math.log10(Math.max(1e-3, row[xi]))),
        ),
        customdata: data.x_mm.map((_, xi) =>
          data.intensity.slice(from, to).map((row) => row[xi]),
        ),
        zmin: -3,
        zmax: 0,
        colorscale: [
          [0, "#000004"],
          [0.13, "#1b0c41"],
          [0.25, "#4a0c6b"],
          [0.38, "#781c6d"],
          [0.5, "#a52c60"],
          [0.63, "#cf4446"],
          [0.75, "#ed6925"],
          [0.88, "#fb9b06"],
          [1, "#fcffa4"],
        ],
        colorbar: {
          title: "|U|² / input peak",
          tickvals: [-3, -2, -1, 0],
          ticktext: ["0.001", "0.01", "0.1", "1"],
        },
        hovertemplate:
          "z %{x:.5g} mm<br>x %{y:.5g} mm<br>|U|² / input peak %{customdata:.5g}<extra></extra>",
      });
    }
  }
  if (showRays) {
    const shownDirections = new Set();
    for (let ray = 0; ray < (result.rays.y_mm[0]?.length ?? 0); ray++) {
      for (let sample = 1; sample < result.rays.z_mm.length; sample++) {
        if (result.rays.alive?.[sample - 1]?.[ray] === false) break;
        const x = [result.rays.z_mm[sample - 1], result.rays.z_mm[sample]];
        if (x[0] === x[1]) continue;
        const returning = x[1] < x[0];
        const group = returning ? "return" : "forward";
        traces.push({
          type: "scatter",
          mode: "lines",
          name: returning ? "Returning rays" : "Rays",
          legendgroup: group,
          showlegend: !shownDirections.has(group),
          x,
          y: [result.rays.y_mm[sample - 1][ray], result.rays.y_mm[sample][ray]],
          line: { color: returning ? "#8741a6" : "#1767b4", width: 1.4 },
          hovertemplate:
            "z %{x:.5g} mm<br>height %{y:.5g} mm<extra>%{fullData.name}</extra>",
        });
        shownDirections.add(group);
      }
    }
  }
  if (showGaussian) {
    const stop = Number.isInteger(result.gaussian.aperture_stop_index)
      ? result.gaussian.aperture_stop_index + 1
      : result.gaussian.z_mm.length;
    const z = result.gaussian.z_mm.slice(0, stop);
    const w = result.gaussian.radius_mm.slice(0, stop);
    for (const sign of [-1, 1])
      traces.push({
        type: "scatter",
        mode: "lines",
        name: "Unclipped Gaussian reference",
        legendgroup: "gaussian",
        showlegend: sign === 1,
        x: z,
        y: w.map((radius) => sign * radius),
        line: { color: "#ad510c", dash: "dash", width: 2 },
        hovertemplate:
          "z %{x:.5g} mm<br>±w %{y:.5g} mm<extra>Unclipped Gaussian reference</extra>",
      });
  }
  const shapes = [];
  const annotations = [];
  const yValues = traces.flatMap((trace) =>
    Array.isArray(trace.y) ? trace.y.flat(Infinity) : [],
  );
  const finiteY = yValues.filter(Number.isFinite);
  const yMin = finiteY.length ? Math.min(...finiteY) : -1;
  const yMax = finiteY.length ? Math.max(...finiteY) : 1;
  for (const element of result.elements ?? []) {
    const z = element.z_mm;
    if (element.type === "aperture") {
      const half =
        Math.abs(element.x_mm ?? 0) < element.radius_mm
          ? element.radius_mm *
            Math.sqrt(1 - ((element.x_mm ?? 0) / element.radius_mm) ** 2)
          : 0;
      const center = element.y_mm ?? 0;
      shapes.push({
        type: "line",
        x0: z,
        x1: z,
        y0: yMin,
        y1: center - half,
        line: { color: "#202936", width: 4 },
      });
      shapes.push({
        type: "line",
        x0: z,
        x1: z,
        y0: center + half,
        y1: yMax,
        line: { color: "#202936", width: 4 },
      });
    } else if (
      ["thin_lens", "interface", "mirror", "thick_lens"].includes(element.type)
    ) {
      shapes.push({
        type: "line",
        x0: z,
        x1: z,
        y0: 0,
        y1: 1,
        yref: "paper",
        line: {
          color: "#748294",
          width: element.type === "mirror" ? 3 : 1,
          dash: element.type === "interface" ? "dot" : "solid",
        },
      });
      if (element.type === "thin_lens") {
        const outward = element.focal_length_mm > 0;
        for (const top of [false, true]) {
          const tip = outward ? (top ? 1 : 0) : top ? 0.82 : 0.18;
          const tail = outward ? (top ? 0.82 : 0.18) : top ? 1 : 0;
          annotations.push({
            x: z,
            y: tip,
            ax: z,
            ay: tail,
            xref: "x",
            yref: "paper",
            axref: "x",
            ayref: "paper",
            text: "",
            showarrow: true,
            arrowhead: 2,
            arrowsize: 1,
            arrowwidth: 1.5,
            arrowcolor: "#748294",
          });
        }
      }
    }
  }
  return Plotly.react(
    host,
    traces,
    {
      autosize: true,
      margin: { l: 64, r: physical ? 72 : 24, t: 12, b: 52 },
      paper_bgcolor: "#fff",
      plot_bgcolor: "#fff",
      font: { family: "system-ui, sans-serif", size: 12, color: "#202936" },
      hovermode: "closest",
      uirevision: `owl-${view}`,
      xaxis: { title: "z (mm)", showgrid: true, zeroline: false },
      yaxis: {
        title: physical ? "x (mm)" : "height (mm)",
        showgrid: true,
        zeroline: true,
      },
      showlegend: traces.some(
        (trace) => trace.showlegend !== false && trace.name,
      ),
      legend: { orientation: "h", y: -0.2 },
      shapes,
      annotations,
    },
    graphConfig,
  );
}

function renderCrossSectionPlots(heatHost, sliceHost, data, plane, selected) {
  const xs = data.x_mm;
  const values = plane.intensity;
  let center = 0;
  xs.forEach((value, i) => {
    if (Math.abs(value) < Math.abs(xs[center])) center = i;
  });
  let peak = 1;
  for (const entry of data.planes ?? [])
    for (const value of entry.intensity?.[center] ?? [])
      if (Number.isFinite(value)) peak = Math.max(peak, value);
  const heat = Plotly.react(
    heatHost,
    [
      {
        type: "heatmap",
        x: xs,
        y: xs,
        z: values,
        zmin: 0,
        zmax: 1,
        colorscale: "Inferno",
        showscale: false,
        hovertemplate:
          "x %{x:.5g} mm<br>y %{y:.5g} mm<br>|U|² / input peak %{z:.5g}<extra></extra>",
      },
    ],
    {
      autosize: true,
      margin: { l: 58, r: 12, t: 12, b: 50 },
      paper_bgcolor: "#fff",
      plot_bgcolor: "#000004",
      font: { family: "system-ui, sans-serif", size: 11, color: "#202936" },
      xaxis: { title: "x (mm)", scaleanchor: "y", scaleratio: 1 },
      yaxis: { title: "y (mm)" },
      uirevision: `owl-heat-${selected}`,
    },
    graphConfig,
  );
  const slice = Plotly.react(
    sliceHost,
    [
      {
        type: "scatter",
        mode: "lines",
        x: xs,
        y: values[center],
        line: { color: "#1767b4", width: 2 },
        customdata: xs.map(() => xs[center]),
        hovertemplate:
          "x %{x:.5g} mm<br>y %{customdata:.5g} mm<br>|U|² / input peak %{y:.5g}<extra></extra>",
      },
    ],
    {
      autosize: true,
      margin: { l: 58, r: 12, t: 12, b: 48 },
      paper_bgcolor: "#fff",
      plot_bgcolor: "#fff",
      font: { family: "system-ui, sans-serif", size: 11, color: "#202936" },
      xaxis: { title: "x (mm)" },
      yaxis: {
        title: `I / input peak · y ≈ ${fmtPlot(xs[center])} mm`,
        range: [0, peak],
      },
      uirevision: `owl-slice-${selected}`,
    },
    graphConfig,
  );
  return Promise.all([heat, slice]);
}
