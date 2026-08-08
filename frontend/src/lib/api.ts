const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${path} failed: ${res.status} ${text}`);
  }
  return res.json();
}

export const api = {
  indexes: () => request<import("./types").IndexDef[]>("/api/catalog/indexes"),
  dataSources: () => request<Record<string, unknown>>("/api/catalog/data-sources"),
  keralaAoi: () => request<{ state: string; districts: string[]; bbox: number[] }>("/api/catalog/aoi/kerala"),
  runAnalysis: (payload: Record<string, unknown>) =>
    request<{ aoi_name: string; source_used: string; stats: Record<string, unknown> }>("/api/analysis", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createTimelapse: (payload: Record<string, unknown>) =>
    request<{ run_id: string; frame_count: number; gif_path: string }>("/api/timelapse", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  submitRequest: (payload: Record<string, unknown>) =>
    request<{ id: string; status: string }>("/api/requests", { method: "POST", body: JSON.stringify(payload) }),
  requestStatus: (id: string) => request<Record<string, unknown>>(`/api/requests/${id}`),
  adminLogin: (username: string, password: string) =>
    request<{ token: string; username: string }>("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  adminLogout: (token: string) =>
    request("/api/admin/logout", { method: "POST", headers: { Authorization: `Bearer ${token}` } }),
  adminListRequests: (token: string, status?: string) =>
    request<import("./types").DatasetRequest[]>(`/api/admin/requests${status ? `?status=${status}` : ""}`, {
      headers: { Authorization: `Bearer ${token}` },
    }),
  adminApprove: (token: string, id: string, reviewed_by?: string, admin_notes?: string) =>
    request(`/api/admin/requests/${id}/approve`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify({ reviewed_by, admin_notes }),
    }),
  adminReject: (token: string, id: string, reviewed_by?: string, admin_notes?: string) =>
    request(`/api/admin/requests/${id}/reject`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify({ reviewed_by, admin_notes }),
    }),
  adminRelease: (token: string, id: string, paths: Record<string, string | undefined>) =>
    request(`/api/admin/requests/${id}/release`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(paths),
    }),
};
