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
const map = L.map("map").setView([10.5, 76.2], 8);
L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
}).addTo(map);

// Tracks currently-added GEE tile layers, keyed by `${code}_pre` /
// `${code}_post`, so re-running Analysis or toggling a checkbox twice
// doesn't add duplicate Leaflet layers.
const activeLayers = {};

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

// Remove any previously-added GEE layers before a fresh run so stale
// Pre/Post overlays from an earlier AOI/date range don't linger on the map.
function clearActiveLayers() {
  Object.values(activeLayers).forEach((layer) => map.removeLayer(layer));
  for (const key in activeLayers) delete activeLayers[key];
}

function renderLayerPanel(stats, bounds) {
  const panel = $("layer-list");
  const codes = Object.keys(stats).filter((c) => c !== "drought_summary" && stats[c].pre_tile_url);
  if (!codes.length) {
    panel.innerHTML = '<p class="muted">Map layers require the Google Earth Engine backend (currently using the Planetary Computer fallback, or getMapId failed) -- the numeric results above are still valid.</p>';
    return;
  }
  panel.innerHTML = '<p class="muted small">Toggle a computed index onto the map above as a colored overlay.</p>';
  codes.forEach((code) => {
    const vals = stats[code];
    const row = document.createElement("div");
    row.className = "layer-row";
    row.innerHTML = `
      <strong>${code}</strong>
      <label class="checkbox-row"><input type="checkbox" data-code="${code}" data-period="pre"> Pre</label>
      <label class="checkbox-row"><input type="checkbox" data-code="${code}" data-period="post"> Post</label>
    `;
    panel.appendChild(row);
    row.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener("change", (e) => {
        const period = e.target.dataset.period;
        const key = `${code}_${period}`;
        if (e.target.checked) {
          const url = period === "pre" ? vals.pre_tile_url : vals.post_tile_url;
          activeLayers[key] = L.tileLayer(url, { opacity: 0.75, attribution: "Google Earth Engine" }).addTo(map);
        } else if (activeLayers[key]) {
          map.removeLayer(activeLayers[key]);
          delete activeLayers[key];
        }
      });
    });
  });
  if (bounds) {
    map.fitBounds(L.latLngBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]]));
  }
}

function renderExplanations(stats) {
  const codes = Object.keys(stats).filter((c) => c !== "drought_summary");
  const known = codes.filter((c) => indexCatalogByCode[c]);
  if (!known.length) return "";
  let html = '<details class="explain"><summary>What do these values mean?</summary><div class="explain-body">';
  known.forEach((code) => {
    const i = indexCatalogByCode[code];
    html += `<p><strong>${i.code}</strong> — ${i.name}<br>
      <span class="muted small">${i.formula} · ${i.reference}</span><br>
      <span class="small">${i.interpretation || ""}</span></p>`;
  });
  html += "</div></details>";
  return html;
}

$("run-analysis").addEventListener("click", async () => {
  const out = $("analysis-results");
  out.innerHTML = '<p class="muted">Running analysis…</p>';
  clearActiveLayers();
  try {
    const result = await api("/api/analysis", {
      method: "POST",
      body: JSON.stringify({
        aoi_name: $("analysis-area").value || "Kerala",
        data_source: document.querySelector('input[name="data-source"]:checked').value,
        pre_start: $("pre-start").value,
        pre_end: $("pre-end").value,
        post_start: $("post-start").value,
        post_end: $("post-end").value,
        indexes: selectedIndexes,
      }),
    });
    let html = `<p class="muted">Source used: ${result.source_used}</p><table class="results-table"><thead><tr><th>Index</th><th>Pre</th><th>Post</th></tr></thead><tbody>`;
    Object.entries(result.stats).forEach(([code, vals]) => {
      if (code === "drought_summary") return;
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
    html += renderExplanations(result.stats);
    out.innerHTML = html;
    renderLayerPanel(result.stats, result.bounds);
    $("layers-panel").open = true;
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
  } catch (err) {
    progress.textContent = err.message;
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
