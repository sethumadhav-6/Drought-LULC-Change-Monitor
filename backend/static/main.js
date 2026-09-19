// Canopy GeoAI dashboard -- vanilla JS, no build step (same pattern as
// the Canopy Geospatial Solutions gps_accuracy_live_app reference app).

const $ = (id) => document.getElementById(id);

function isoDaysAgo(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

// --- Defaults for date inputs ---
$("pre-start").value = isoDaysAgo(365);
$("pre-end").value = isoDaysAgo(300);
$("post-start").value = isoDaysAgo(90);
$("post-end").value = isoDaysAgo(0);
$("tl-end").value = isoDaysAgo(0);
$("req-start").value = isoDaysAgo(0);
$("req-end").value = isoDaysAgo(-30);

// --- Health / GEE status ---
api("/api/health")
  .then((h) => {
    const pill = $("gee-status");
    pill.textContent = h.gee_available ? "Earth Engine connected" : "Earth Engine not configured";
    pill.classList.toggle("status-warn", !h.gee_available);
  })
  .catch(() => {
    $("gee-status").textContent = "Backend unreachable";
    $("gee-status").classList.add("status-warn");
  });

// --- Index catalog ---
let selectedIndexes = ["NDVI", "NDWI", "NDDI"];
let indexCatalogByCode = {};
api("/api/catalog/indexes")
  .then((indexes) => {
    indexes.forEach((i) => (indexCatalogByCode[i.code] = i));
    const byCategory = {};
    indexes.forEach((i) => (byCategory[i.category] ||= []).push(i));
    const container = $("index-list");
    container.innerHTML = "";
    const intro = document.createElement("p");
    intro.className = "muted";
    intro.innerHTML = 'Formulas per the <a href="https://www.indexdatabase.de/" target="_blank" rel="noreferrer">Index Database</a> and drought-monitoring literature (Gu 2007; Kogan 1995/1997).';
    container.appendChild(intro);
    Object.entries(byCategory).forEach(([cat, items]) => {
      const label = document.createElement("p");
      label.className = "category-label";
      label.textContent = cat.toUpperCase();
      container.appendChild(label);
      items.forEach((idx) => {
        const row = document.createElement("label");
        row.className = "checkbox-row";
        row.title = `${idx.formula} · ${idx.reference}`;
        row.innerHTML = `<input type="checkbox" value="${idx.code}" ${selectedIndexes.includes(idx.code) ? "checked" : ""}>
          <span><strong>${idx.code}</strong> — ${idx.name}<br><span class="muted small">${idx.formula} · ${idx.reference}</span></span>`;
        row.querySelector("input").addEventListener("change", (e) => {
          if (e.target.checked) selectedIndexes.push(idx.code);
          else selectedIndexes = selectedIndexes.filter((c) => c !== idx.code);
        });
        container.appendChild(row);
      });
    });
  })
  .catch((err) => ($("index-list").innerHTML = `<p class="status-warn">Could not load index catalog: ${err.message}</p>`));

// --- AOI (districts) ---
let districtNames = [];
function populateAreaSelect(select) {
  select.innerHTML = "";
  const opt = document.createElement("option");
  opt.value = "Kerala";
  opt.textContent = "Kerala (whole state)";
  select.appendChild(opt);
  districtNames.forEach((name) => {
    const o = document.createElement("option");
    o.value = name;
    o.textContent = name;
    select.appendChild(o);
  });
}

api("/api/catalog/aoi")
  .then((r) => {
    districtNames = r.districts || [];
    populateAreaSelect($("analysis-area"));
    populateAreaSelect($("tl-area"));
  })
  .catch(() => {
    populateAreaSelect($("analysis-area"));
    populateAreaSelect($("tl-area"));
  });

// --- Map ---
// Basemap gallery (leafmap/geemap-style basemap picker, via Leaflet's
// built-in collapsible layer control since this is a plain server-rendered
// page rather than a Jupyter widget).
const basemaps = {
  "Light (default)": L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
  }),
  "Dark": L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
  }),
  "OpenStreetMap": L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
  }),
  "Satellite (Esri)": L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    attribution: "Tiles &copy; Esri, Maxar, Earthstar Geographics",
  }),
};

const map = L.map("map", { layers: [basemaps["Light (default)"]] }).setView([10.5, 76.2], 8);

const layersControl = L.control.layers(basemaps, {}, { collapsed: true, position: "topright" }).addTo(map);

// Distance/area measurement tool -- same capability as leafmap's built-in
// measure tool (github.com/opengeos/leafmap), via the leaflet-measure plugin
// since we're not in a Jupyter/ipyleaflet context here.
L.control.measure({
  position: "topleft",
  primaryLengthUnit: "kilometers",
  secondaryLengthUnit: "meters",
  primaryAreaUnit: "hectares",
  secondaryAreaUnit: "sqmeters",
  activeColor: "#1a9850",
  completedColor: "#0f5c30",
}).addTo(map);

// Legend control -- shows a color ramp + min/max for each currently active
// GEE map layer. Updated by refreshLegend(), called whenever a layer
// checkbox toggles or a colormap gets customized.
const LegendControl = L.Control.extend({
  onAdd() {
    this._div = L.DomUtil.create("div", "legend-control");
    this._div.innerHTML = '<p class="muted small">No layers active</p>';
    return this._div;
  },
  update(entries) {
    if (!entries.length) {
      this._div.innerHTML = '<p class="muted small">No layers active</p>';
      return;
    }
    this._div.innerHTML = entries.map((e) => `
      <div class="legend-entry">
        <strong>${e.label}</strong>
        <div class="legend-ramp" style="background:linear-gradient(to right, ${e.palette.join(",")})"></div>
        <div class="legend-scale"><span>${e.min}</span><span>${e.max}</span></div>
      </div>
    `).join("");
  },
});
const legendControl = new LegendControl({ position: "bottomright" }).addTo(map);

// Tracks currently-added GEE tile layers, keyed by `${code}_pre` /
// `${code}_post`, so re-running Analysis or toggling a checkbox twice
// doesn't add duplicate Leaflet layers. Each entry is { layer, vis } so
// the legend control can read back the palette/min/max in use.
const activeLayers = {};

function refreshLegend() {
  const entries = Object.entries(activeLayers).map(([key, info]) => ({
    label: key.replace("_", " "),
    palette: info.vis.palette,
    min: info.vis.min,
    max: info.vis.max,
  }));
  legendControl.update(entries);
}

// Map text size customization (legend/tooltip font size).
$("map-font-size").addEventListener("change", (e) => {
  $("map").style.setProperty("--map-font-size", `${e.target.value}px`);
});

let geojsonLayer = null;
api("/api/catalog/kerala-geojson")
  .then((gj) => {
    if (!gj.features || !gj.features.length) return;
    geojsonLayer = L.geoJSON(gj, {
      style: () => ({ color: "#0f5c30", weight: 1, fillColor: "#a6d96a", fillOpacity: 0.15 }),
      onEachFeature: (feature, layer) => {
        const name = feature.properties?.NAME_2 || "";
        if (name) layer.bindTooltip(name);
      },
    }).addTo(map);
    map.fitBounds(geojsonLayer.getBounds());
    layersControl.addOverlay(geojsonLayer, "Kerala districts");
  })
  .catch(() => {});

function highlightDistrict(name) {
  if (!geojsonLayer) return;
  geojsonLayer.eachLayer((layer) => {
    const layerName = layer.feature?.properties?.NAME_2 || "";
    const selected = name !== "Kerala" && layerName.toLowerCase() === name.toLowerCase();
    layer.setStyle({
      fillColor: selected ? "#1a9850" : "#a6d96a",
      weight: selected ? 2 : 1,
      fillOpacity: selected ? 0.5 : 0.15,
    });
  });
}
$("tl-area").addEventListener("change", (e) => highlightDistrict(e.target.value));

// --- Analysis ---

const PALETTE_PRESETS = {
  "Default (by index category)": null,
  "Red-Yellow-Green": ["#a50026", "#ffffbf", "#1a9850"],
  "Green-Yellow-Red (drought)": ["#1a9850", "#ffffbf", "#a50026"],
  "Blue-White-Red": ["#2166ac", "#f7f7f7", "#b2182b"],
  "Brown-White-Green": ["#8c510a", "#f5f5f5", "#1a9850"],
  "Viridis-like": ["#440154", "#21918c", "#fde725"],
};

// Remembers the AOI/date-range params from the last successful Analysis run
// so the colormap-customization controls can re-request a layer without
// the user having to re-enter anything.
let lastAnalysisParams = null;

// Remove any previously-added GEE layers before a fresh run so stale
// Pre/Post overlays from an earlier AOI/date range don't linger on the map.
function clearActiveLayers() {
  Object.values(activeLayers).forEach((info) => map.removeLayer(info.layer));
  for (const key in activeLayers) delete activeLayers[key];
  refreshLegend();
}

function renderLayerPanel(stats, bounds) {
  const panel = $("layer-list");
  const codes = Object.keys(stats).filter((c) => c !== "drought_summary" && c !== "land_stress" && stats[c].pre_tile_url);
  if (!codes.length) {
    panel.innerHTML = '<p class="muted">Map layers require the Google Earth Engine backend (currently using the Planetary Computer fallback, or getMapId failed) -- the numeric results above are still valid.</p>';
    return;
  }
  panel.innerHTML = '<p class="muted small">Toggle a computed index onto the map above as a colored overlay. Use "Customize" to change its colormap or min/max range.</p>';
  codes.forEach((code) => {
    const vals = stats[code];
    let opacity = 0.75;
    const paletteOptions = Object.keys(PALETTE_PRESETS).map((name) => `<option value="${name}">${name}</option>`).join("");
    const row = document.createElement("div");
    row.className = "layer-row-wrap";
    row.innerHTML = `
      <div class="layer-row">
        <strong>${code}</strong>
        <label class="checkbox-row"><input type="checkbox" data-code="${code}" data-period="pre"> Pre</label>
        <label class="checkbox-row"><input type="checkbox" data-code="${code}" data-period="post"> Post</label>
        <label class="opacity-row small">Opacity
          <input type="range" class="layer-opacity" min="0" max="1" step="0.05" value="0.75">
        </label>
      </div>
      <details class="layer-customize">
        <summary>Customize colormap</summary>
        <div class="grid-3">
          <label>Palette
            <select class="cm-palette">${paletteOptions}</select>
          </label>
          <label>Min <input type="number" class="cm-min" value="${vals.vis?.min ?? -1}" step="0.1"></label>
          <label>Max <input type="number" class="cm-max" value="${vals.vis?.max ?? 1}" step="0.1"></label>
        </div>
        <button type="button" class="cm-apply small">Apply to this layer</button>
        <p class="cm-status muted small"></p>
      </details>
      <div class="publish-row">
        <select class="publish-period">
          <option value="pre">Pre</option>
          <option value="post">Post</option>
        </select>
        <button type="button" class="publish-btn small">Publish for web</button>
        <p class="publish-status muted small"></p>
      </div>
    `;
    panel.appendChild(row);

    row.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener("change", (e) => {
        const period = e.target.dataset.period;
        const key = `${code}_${period}`;
        if (e.target.checked) {
          const url = period === "pre" ? vals.pre_tile_url : vals.post_tile_url;
          activeLayers[key] = {
            layer: L.tileLayer(url, { opacity, attribution: "Google Earth Engine" }).addTo(map),
            vis: vals.vis || { min: -1, max: 1, palette: ["#a50026", "#ffffbf", "#1a9850"] },
          };
        } else if (activeLayers[key]) {
          map.removeLayer(activeLayers[key].layer);
          delete activeLayers[key];
        }
        refreshLegend();
      });
    });

    row.querySelector(".layer-opacity").addEventListener("input", (e) => {
      opacity = Number(e.target.value);
      ["pre", "post"].forEach((period) => {
        const key = `${code}_${period}`;
        if (activeLayers[key]) activeLayers[key].layer.setOpacity(opacity);
      });
    });

    row.querySelector(".cm-apply").addEventListener("click", async () => {
      if (!lastAnalysisParams) return;
      const status = row.querySelector(".cm-status");
      const paletteName = row.querySelector(".cm-palette").value;
      const palette = PALETTE_PRESETS[paletteName] || (vals.vis?.palette ?? ["#a50026", "#ffffbf", "#1a9850"]);
      const min = Number(row.querySelector(".cm-min").value);
      const max = Number(row.querySelector(".cm-max").value);
      const newVis = { min, max, palette };
      status.textContent = "Re-rendering…";
      try {
        for (const period of ["pre", "post"]) {
          const key = `${code}_${period}`;
          const r = await api("/api/analysis/layer-tile", {
            method: "POST",
            body: JSON.stringify({ ...lastAnalysisParams, index_code: code, period, ...newVis }),
          });
          if (period === "pre") vals.pre_tile_url = r.tile_url; else vals.post_tile_url = r.tile_url;
          vals.vis = newVis;
          if (activeLayers[key]) {
            map.removeLayer(activeLayers[key].layer);
            activeLayers[key] = {
              layer: L.tileLayer(r.tile_url, { opacity, attribution: "Google Earth Engine" }).addTo(map),
              vis: newVis,
            };
          }
        }
        refreshLegend();
        status.textContent = "Applied.";
      } catch (err) {
        status.textContent = err.message;
      }
    });

    row.querySelector(".publish-btn").addEventListener("click", async () => {
      if (!lastAnalysisParams) return;
      const status = row.querySelector(".publish-status");
      const period = row.querySelector(".publish-period").value;
      status.textContent = "Publishing…";
      try {
        const r = await api("/api/publish/analysis-layer", {
          method: "POST",
          body: JSON.stringify({
            ...lastAnalysisParams, index_code: code, period,
            min: vals.vis?.min, max: vals.vis?.max, palette: vals.vis?.palette,
          }),
        });
        status.innerHTML = `Published: <a href="${r.viewer_url}" target="_blank">preview</a> — folder on server: <code>${r.folder}</code>`;
      } catch (err) {
        status.textContent = err.message;
      }
    });
  });
  if (bounds) {
    map.fitBounds(L.latLngBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]]));
  }
}

const ANCILLARY_LABELS = {
  soil: "Soil (drainage class)",
  geomorphology: "Geomorphology",
  geology: "Geology (rock group)",
  drainage: "Drainage (stream order)",
};

function renderAncillaryHtml(data) {
  const avail = data.available || {};
  if (!Object.values(avail).some(Boolean)) {
    return '<p class="muted small">No ancillary layers configured yet (DEM/soil/drainage/geomorphology/geology).</p>';
  }
  let html = "";
  if (data.elevation) {
    const e = data.elevation;
    html += `<p><strong>Elevation</strong> — min ${e.min_m.toFixed(0)}m, max ${e.max_m.toFixed(0)}m, mean ${e.mean_m.toFixed(0)}m</p>`;
  }
  ["soil", "geomorphology", "geology", "drainage"].forEach((layer) => {
    const d = data[layer];
    if (!d) return;
    const top = Object.entries(d.categories || {})
      .slice(0, 3)
      .map(([k, v]) => `${k} (${(v * 100).toFixed(0)}%)`)
      .join(", ");
    html += `<p><strong>${ANCILLARY_LABELS[layer]}</strong> — ${top || "—"}`;
    if (d.total_length_km != null) html += ` · total length ${Math.round(d.total_length_km).toLocaleString()} km`;
    if (d.approximate) html += ' <span class="muted small">(approximate -- bbox-filtered, not exactly clipped)</span>';
    html += "</p>";
  });
  return html;
}

// Ties the ancillary (terrain) layers together with the index results so
// the analysis reads as one assessment instead of two disconnected
// sections. This is a descriptive synthesis, not a numeric one -- the
// terrain layers aren't folded into land_stress_index()'s score itself
// (that needs an explicit weighting decision, see docs/ANCILLARY_DATA.md),
// but the reader gets the physical context the index changes are
// happening in, in plain language, right next to the numbers.
function buildTerrainNarrative(data, stats) {
  const avail = data.available || {};
  if (!Object.values(avail).some(Boolean)) return "";
  const topCategory = (d) => {
    const entries = Object.entries(d?.categories || {});
    return entries.length ? entries[0] : null;
  };
  const parts = [];
  if (data.elevation) {
    parts.push(`mean elevation ${data.elevation.mean_m.toFixed(0)}m (range ${data.elevation.min_m.toFixed(0)}–${data.elevation.max_m.toFixed(0)}m)`);
  }
  const soilTop = topCategory(data.soil);
  if (soilTop) parts.push(`soil drainage predominantly "${soilTop[0]}" (${(soilTop[1] * 100).toFixed(0)}% of the area)`);
  const geoTop = topCategory(data.geomorphology);
  if (geoTop) parts.push(`geomorphology chiefly "${geoTop[0]}" (${(geoTop[1] * 100).toFixed(0)}%)`);
  const geolTop = topCategory(data.geology);
  if (geolTop) parts.push(`underlying geology mostly "${geolTop[0]}" (${(geolTop[1] * 100).toFixed(0)}%)`);
  if (!parts.length) return "";

  let tie = "";
  const ls = stats && stats.land_stress;
  if (ls) {
    tie = ` The land-stress score above (${ls.pre.class} → ${ls.post.class}) is currently calculated from NDVI/NDBI alone, not this terrain -- read the two together: poorly-drained soils and steep/hilly geomorphology tend to make the same vegetation or moisture decline show up more severely on the ground (more waterlogging, more runoff, higher landslide sensitivity) than the identical index change would on flat, well-drained land.`;
  }
  return `<p><strong>Terrain context for these results</strong> — this AOI has ${parts.join(", ")}.${tie} `
    + `<span class="muted small">Not yet folded into the numeric score itself — tell us how you'd like these layers weighted and we can wire that in.</span></p>`;
}

// Fetched separately (not part of /api/analysis) and best-effort: a slow
// or unconfigured ancillary endpoint shouldn't block the main analysis
// results from showing. See app/core/ancillary.py -- not yet factored
// into the drought/land-stress scoring math itself; `stats` (the same
// object rendered in the results table) is used here only to connect the
// terrain narrative to the land-stress class, not to recompute anything.
async function fetchAncillary(aoiName, stats) {
  const block = $("ancillary-block");
  if (!block) return;
  try {
    const data = await api(`/api/catalog/ancillary?aoi_name=${encodeURIComponent(aoiName)}`);
    block.innerHTML = renderAncillaryHtml(data) + buildTerrainNarrative(data, stats);
  } catch (err) {
    block.innerHTML = `<p class="muted small">Ancillary context unavailable: ${err.message}</p>`;
  }
}

// Describes what actually happened to a single index's own pre/post
// numbers in plain language (direction, size of change, % where the
// baseline supports one) -- this is what was missing before: the
// catalog's generic definition text was shown with no connection to the
// user's own computed values, which is what made it confusing.
function describeChange(pre, post) {
  if (pre == null || post == null) return "";
  const delta = post - pre;
  if (Math.abs(delta) < 0.0005) {
    return `stayed essentially flat, ${pre.toFixed(4)} → ${post.toFixed(4)}`;
  }
  const direction = delta > 0 ? "rose" : "fell";
  let pctText = "";
  if (Math.abs(pre) > 0.01) {
    const pct = (delta / Math.abs(pre)) * 100;
    pctText = ` (${pct > 0 ? "+" : ""}${pct.toFixed(0)}%)`;
  }
  return `${direction} from ${pre.toFixed(4)} to ${post.toFixed(4)}${pctText}`;
}

function renderExplanations(stats) {
  const codes = Object.keys(stats).filter((c) => c !== "drought_summary" && c !== "land_stress");
  const known = codes.filter((c) => indexCatalogByCode[c]);
  if (!known.length) return "";
  let html = '<details class="explain" open><summary>What do these results mean?</summary><div class="explain-body">';
  known.forEach((code) => {
    const i = indexCatalogByCode[code];
    const vals = stats[code] || {};
    const change = describeChange(vals.pre_mean, vals.post_mean);
    html += `<p><strong>${i.code}</strong>${change ? ` <span class="small">${change} between the two windows.</span>` : ""}<br>
      <span class="small">${i.interpretation || ""}</span><br>
      <span class="muted small">${i.name} · ${i.formula} · ${i.reference}</span></p>`;
  });
  html += "</div></details>";
  return html;
}

$("run-analysis").addEventListener("click", async () => {
  const out = $("analysis-results");
  out.innerHTML = '<p class="muted">Running analysis…</p>';
  clearActiveLayers();
  try {
    const requestBody = {
      aoi_name: $("analysis-area").value || "Kerala",
      data_source: document.querySelector('input[name="data-source"]:checked').value,
      pre_start: $("pre-start").value,
      pre_end: $("pre-end").value,
      post_start: $("post-start").value,
      post_end: $("post-end").value,
      indexes: selectedIndexes,
      user_name: $("analysis-user-name").value || null,
      user_email: $("analysis-user-email").value || null,
    };
    const result = await api("/api/analysis", {
      method: "POST",
      body: JSON.stringify(requestBody),
    });
    // Kept for the colormap-customization controls in renderLayerPanel,
    // which need to re-request a single layer's tile with new vis params.
    lastAnalysisParams = {
      aoi_name: requestBody.aoi_name,
      pre_start: requestBody.pre_start,
      pre_end: requestBody.pre_end,
      post_start: requestBody.post_start,
      post_end: requestBody.post_end,
    };
    let html = `<p class="muted">Source used: ${result.source_used}</p><table class="results-table"><thead><tr><th>Index</th><th>Pre</th><th>Post</th></tr></thead><tbody>`;
    Object.entries(result.stats).forEach(([code, vals]) => {
      if (code === "drought_summary" || code === "land_stress") return;
      const pre = vals.pre_mean != null ? vals.pre_mean.toFixed(4) : "—";
      const post = vals.post_mean != null ? vals.post_mean.toFixed(4) : "—";
      html += `<tr><td>${code}</td><td>${pre}</td><td>${post}</td></tr>`;
    });
    html += "</tbody></table>";
    if (result.stats.drought_summary) {
      const d = result.stats.drought_summary;
      html += `<p><strong>Drought summary</strong> — NDDI: ${d.NDDI_mean ?? "—"}`;
      if (d.VHI_mean != null) html += ` · VHI: ${d.VHI_mean} (${d.VHI_class})`;
      html += "</p>";
    }
    if (result.stats.land_stress) {
      const ls = result.stats.land_stress;
      html += `<p><strong>Land stress index</strong> (weighted NDVI+NDBI, replaces LULC classification) — `
        + `Pre: ${ls.pre.score} (${ls.pre.class}) → Post: ${ls.post.score} (${ls.post.class})`
        + `<br><span class="muted small">Weights: NDVI ${ls.post.weights.ndvi}, NDBI ${ls.post.weights.ndbi} — higher score = more vegetation loss / built-up pressure.</span></p>`;
    }
    html += renderExplanations(result.stats);
    html += '<details class="explain" open><summary>Ancillary context — DEM, soil, drainage, geomorphology, geology</summary>'
      + '<div class="explain-body" id="ancillary-block"><p class="muted small">Loading…</p></div></details>';
    out.innerHTML = html;
    renderLayerPanel(result.stats, result.bounds);
    $("layers-panel").open = true;
    fetchAncillary(requestBody.aoi_name, result.stats);
  } catch (err) {
    out.innerHTML = `<p class="status-warn">${err.message}</p>`;
  }
});

// --- Timelapse ---
$("run-timelapse").addEventListener("click", async () => {
  const progress = $("timelapse-progress");
  progress.textContent = "Generating timelapse (this can take a while -- each frame is a real Earth Engine render)…";
  try {
    const result = await api("/api/timelapse", {
      method: "POST",
      body: JSON.stringify({
        aoi_name: $("tl-area").value || "Kerala",
        index_code: $("tl-index").value,
        start: $("tl-start").value,
        end: $("tl-end").value,
        step_months: Number($("tl-step").value || 3),
        fps: 1,
      }),
    });
    progress.textContent = `Generated ${result.frame_count} frames — run ${result.run_id}`;
    $("timelapse-viewer").hidden = false;
    const img = $("timelapse-gif");
    img.src = result.gif_url;
    img.dataset.lastFrame = result.frame_urls[result.frame_urls.length - 1] || result.gif_url;
    img.dataset.runId = result.run_id;
    $("publish-timelapse-status").textContent = "";
  } catch (err) {
    progress.textContent = err.message;
  }
});

$("publish-timelapse").addEventListener("click", async () => {
  const runId = $("timelapse-gif").dataset.runId;
  const status = $("publish-timelapse-status");
  if (!runId) return;
  status.textContent = "Publishing…";
  try {
    const r = await api(`/api/publish/timelapse/${runId}`, {
      method: "POST",
      body: JSON.stringify({ aoi_name: $("tl-area").value || "Kerala" }),
    });
    status.innerHTML = `Published: <a href="${r.viewer_url}" target="_blank">preview</a> — folder on server: <code>${r.folder}</code>`;
  } catch (err) {
    status.textContent = err.message;
  }
});

$("print-frame").addEventListener("click", () => {
  const lastFrame = $("timelapse-gif").dataset.lastFrame;
  if (!lastFrame) return;
  const w = window.open(lastFrame, "_blank");
  if (w) w.onload = () => w.print();
});

// --- Dataset request form ---
$("request-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const statusEl = $("request-status");
  statusEl.textContent = "Submitting…";
  try {
    const result = await api("/api/requests", {
      method: "POST",
      body: JSON.stringify({
        requester_name: $("req-name").value,
        requester_email: $("req-email").value,
        organization: $("req-org").value || null,
        aoi_name: $("req-aoi").value || "Kerala",
        data_source: document.querySelector('input[name="data-source"]:checked').value,
        indexes: selectedIndexes,
        date_start: $("req-start").value,
        date_end: $("req-end").value,
        purpose: $("req-purpose").value || null,
      }),
    });
    statusEl.textContent = `Request ${result.id} submitted (status: ${result.status}). The Canopy technical team will review it.`;
    e.target.reset();
  } catch (err) {
    statusEl.textContent = err.message;
  }
});
