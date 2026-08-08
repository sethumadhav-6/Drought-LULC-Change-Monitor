// Canopy GeoAI admin queue -- vanilla JS, session-cookie auth via Flask.

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function showQueue(username) {
  $("login-view").hidden = true;
  $("queue-view").hidden = false;
  $("who").hidden = false;
  $("who").textContent = `Logged in as ${username}`;
  $("logout-btn").hidden = false;
  loadQueue();
}

function showLogin() {
  $("login-view").hidden = false;
  $("queue-view").hidden = true;
  $("who").hidden = true;
  $("logout-btn").hidden = true;
}

api("/api/admin/session")
  .then((r) => (r.logged_in ? showQueue(r.username) : showLogin()))
  .catch(() => showLogin());

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("login-error").textContent = "";
  try {
    const r = await api("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({ username: $("login-username").value, password: $("login-password").value }),
    });
    showQueue(r.username);
  } catch (err) {
    $("login-error").textContent = "Invalid username or password.";
  }
});

$("logout-btn").addEventListener("click", async () => {
  await api("/api/admin/logout", { method: "POST" }).catch(() => {});
  showLogin();
});

$("status-filter").addEventListener("change", loadQueue);

async function loadQueue() {
  const list = $("queue-list");
  list.innerHTML = '<p class="muted">Loading…</p>';
  try {
    const status = $("status-filter").value;
    const reqs = await api(`/api/admin/requests${status ? `?status=${status}` : ""}`);
    if (!reqs.length) {
      list.innerHTML = '<p class="muted">No requests match this filter.</p>';
      return;
    }
    list.innerHTML = "";
    reqs.forEach((req) => list.appendChild(renderRequestCard(req)));
  } catch (err) {
    list.innerHTML = `<p class="status-warn">${err.message}</p>`;
  }
}

function renderRequestCard(req) {
  const card = document.createElement("details");
  card.className = "panel";
  card.innerHTML = `
    <summary>${req.aoi_name} — ${req.requester_name} (${req.status}) — ${new Date(req.created_at).toLocaleString()}</summary>
    <div class="panel-body">
      <div class="grid-2">
        <div>
          <p><strong>Requester:</strong> ${req.requester_name} (${req.requester_email})</p>
          <p><strong>Organization:</strong> ${req.organization || "—"}</p>
          <p><strong>AOI:</strong> ${req.aoi_name}</p>
          <p><strong>Data source:</strong> ${req.data_source}</p>
        </div>
        <div>
          <p><strong>Indexes:</strong> ${(req.indexes || []).join(", ")}</p>
          <p><strong>Window:</strong> ${req.date_start} → ${req.date_end}</p>
          <p><strong>Purpose:</strong> ${req.purpose || "—"}</p>
          <p><strong>Status:</strong> ${req.status}</p>
        </div>
      </div>
      ${req.admin_notes ? `<p><strong>Admin notes:</strong> ${req.admin_notes}</p>` : ""}
      <label>Notes (optional) <input type="text" class="notes-input"></label>
      <div class="actions" style="display:flex; gap:8px; flex-wrap:wrap;"></div>
      ${req.status === "released" ? `
        <p class="status-warn" style="color:#baf5d8;">Released to requester.</p>
        ${req.result_excel_path ? `<p>Excel: <code>${req.result_excel_path}</code></p>` : ""}
        ${req.result_spatial_path ? `<p>Spatial: <code>${req.result_spatial_path}</code></p>` : ""}
        ${req.result_timelapse_path ? `<p>Timelapse: <code>${req.result_timelapse_path}</code></p>` : ""}
      ` : ""}
    </div>
  `;

  const actions = card.querySelector(".actions");
  const notesInput = card.querySelector(".notes-input");

  if (req.status === "requested" || req.status === "under_review") {
    const approveBtn = document.createElement("button");
    approveBtn.textContent = "Approve";
    approveBtn.addEventListener("click", async () => {
      await api(`/api/admin/requests/${req.id}/approve`, {
        method: "POST",
        body: JSON.stringify({ admin_notes: notesInput.value || null }),
      });
      loadQueue();
    });
    const rejectBtn = document.createElement("button");
    rejectBtn.textContent = "Reject";
    rejectBtn.style.background = "var(--panel-2)";
    rejectBtn.style.color = "var(--text)";
    rejectBtn.addEventListener("click", async () => {
      await api(`/api/admin/requests/${req.id}/reject`, {
        method: "POST",
        body: JSON.stringify({ admin_notes: notesInput.value || null }),
      });
      loadQueue();
    });
    actions.appendChild(approveBtn);
    actions.appendChild(rejectBtn);
  }

  if (req.status === "approved") {
    const wrap = document.createElement("div");
    wrap.innerHTML = `
      <p class="muted">Release deliverables (paths already generated via Analysis/Timelapse on the main dashboard):</p>
      <label>Excel report path <input type="text" class="excel-path"></label>
      <label>Spatial export path (GeoTIFF/GeoPackage) <input type="text" class="spatial-path"></label>
      <label>Timelapse GIF/MP4 path <input type="text" class="tl-path"></label>
    `;
    card.querySelector(".panel-body").insertBefore(wrap, actions);
    const releaseBtn = document.createElement("button");
    releaseBtn.textContent = "Validate & Release";
    releaseBtn.addEventListener("click", async () => {
      await api(`/api/admin/requests/${req.id}/release`, {
        method: "POST",
        body: JSON.stringify({
          excel_path: wrap.querySelector(".excel-path").value || null,
          spatial_path: wrap.querySelector(".spatial-path").value || null,
          timelapse_path: wrap.querySelector(".tl-path").value || null,
        }),
      });
      loadQueue();
    });
    actions.appendChild(releaseBtn);
  }

  return card;
}
