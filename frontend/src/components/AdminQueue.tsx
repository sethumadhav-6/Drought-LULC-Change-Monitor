"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { DatasetRequest } from "@/lib/types";

export default function AdminQueue() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [loggedInAs, setLoggedInAs] = useState<string | null>(null);
  const [requests, setRequests] = useState<DatasetRequest[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.adminLogin(username, password);
      setToken(r.token);
      setLoggedInAs(r.username);
      setRequests(await api.adminListRequests(r.token));
    } catch (e) {
      setError("Login failed — check username/password.");
    }
  }

  function logout() {
    if (token) api.adminLogout(token).catch(() => {});
    setToken(null);
    setLoggedInAs(null);
    setRequests([]);
  }

  async function load() {
    if (!token) return;
    setError(null);
    try {
      setRequests(await api.adminListRequests(token));
    } catch (e) {
      setError(String(e));
    }
  }

  async function act(id: string, action: "approve" | "reject") {
    if (!token) return;
    try {
      if (action === "approve") await api.adminApprove(token, id);
      else await api.adminReject(token, id);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function release(id: string) {
    if (!token) return;
    const excel = prompt("Excel report path (server-side, from /api/analysis + services/reports.py)") || undefined;
    const spatial = prompt("Spatial export path (GeoTIFF/GeoPackage)") || undefined;
    const timelapse = prompt("Timelapse GIF/MP4 path") || undefined;
    try {
      await api.adminRelease(token, id, { excel_path: excel, spatial_path: spatial, timelapse_path: timelapse });
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  if (!token) {
    return (
      <div className="max-w-sm mx-auto p-6 mt-16 space-y-4 border rounded-lg bg-white shadow-sm">
        <h1 className="text-xl font-semibold">Admin Login</h1>
        <p className="text-sm text-slate-500">Canopy Geospatial Solutions — dataset request review queue.</p>
        <form onSubmit={login} className="space-y-3">
          <input required placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} className="w-full border rounded px-2 py-1" />
          <input required type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full border rounded px-2 py-1" />
          <button type="submit" className="w-full bg-canopy-dark text-white px-4 py-2 rounded">Log in</button>
        </form>
        {error && <p className="text-red-600 text-sm">{error}</p>}
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Admin — Dataset Request Queue</h1>
        <div className="text-sm">
          Logged in as <strong>{loggedInAs}</strong> ·{" "}
          <button onClick={logout} className="underline text-slate-600">Log out</button>
        </div>
      </div>
      <p className="text-sm text-slate-500">
        Review requested datasets → approve/reject → validate and release (spatial + Excel).
      </p>
      <button onClick={load} className="bg-canopy-dark text-white px-4 py-1 rounded text-sm">Refresh queue</button>
      {error && <p className="text-red-600 text-sm">{error}</p>}
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left border-b">
            <th className="py-1">Requester</th><th>AOI</th><th>Indexes</th><th>Window</th><th>Status</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {requests.map((r) => (
            <tr key={r.id} className="border-b">
              <td className="py-1">{r.requester_name}<br /><span className="text-xs text-slate-400">{r.requester_email}</span></td>
              <td>{r.aoi_name}</td>
              <td>{r.indexes?.join(", ")}</td>
              <td>{r.date_start} → {r.date_end}</td>
              <td>{r.status}</td>
              <td className="space-x-2">
                <button onClick={() => act(r.id, "approve")} className="text-emerald-700 underline">Approve</button>
                <button onClick={() => act(r.id, "reject")} className="text-red-600 underline">Reject</button>
                <button onClick={() => release(r.id)} className="text-slate-700 underline">Release</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
