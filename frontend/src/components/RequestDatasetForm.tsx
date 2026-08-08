"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function RequestDatasetForm({ selectedIndexes, dataSource }: { selectedIndexes: string[]; dataSource: string }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [org, setOrg] = useState("");
  const [aoi, setAoi] = useState("Kerala");
  const [start, setStart] = useState("2026-01-01");
  const [end, setEnd] = useState("2026-06-01");
  const [purpose, setPurpose] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("Submitting...");
    try {
      const r = await api.submitRequest({
        requester_name: name, requester_email: email, organization: org || null,
        aoi_name: aoi, data_source: dataSource, indexes: selectedIndexes,
        date_start: start, date_end: end, purpose: purpose || null,
      });
      setStatus(`Request ${r.id} submitted (status: ${r.status}). The Canopy technical team will review, validate, and release the dataset.`);
    } catch (err) {
      setStatus(`Failed: ${String(err)}`);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 text-sm">
      <p className="text-slate-500">
        Can&apos;t self-serve this dataset? Request it — the Canopy technical team will evaluate,
        validate, and release both spatial and Excel outputs once confirmed.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <input required placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} className="border rounded px-2 py-1" />
        <input required type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} className="border rounded px-2 py-1" />
        <input placeholder="Organization / Department" value={org} onChange={(e) => setOrg(e.target.value)} className="border rounded px-2 py-1 col-span-2" />
        <input required placeholder="AOI (e.g. Idukki district)" value={aoi} onChange={(e) => setAoi(e.target.value)} className="border rounded px-2 py-1" />
        <div className="flex gap-2">
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="border rounded px-2 py-1 w-full" />
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="border rounded px-2 py-1 w-full" />
        </div>
        <textarea placeholder="Purpose / notes" value={purpose} onChange={(e) => setPurpose(e.target.value)} className="border rounded px-2 py-1 col-span-2" rows={2} />
      </div>
      <p className="text-xs text-slate-500">
        Requested indexes: {selectedIndexes.length ? selectedIndexes.join(", ") : "(none selected above)"} · Source: {dataSource}
      </p>
      <button type="submit" className="bg-canopy-dark text-white px-4 py-2 rounded">Request dataset</button>
      {status && <p className="text-slate-600">{status}</p>}
    </form>
  );
}
