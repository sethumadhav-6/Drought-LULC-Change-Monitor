"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function TimelapseViewer() {
  const [districts, setDistricts] = useState<string[]>([]);
  const [aoiName, setAoiName] = useState("Kerala");
  const [indexCode, setIndexCode] = useState("NDVI");
  const [start, setStart] = useState("2019-01-01");
  const [end, setEnd] = useState("2026-01-01");
  const [stepMonths, setStepMonths] = useState(3);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ run_id: string; frame_count: number; gif_path: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.keralaAoi().then((r) => setDistricts(r.districts)).catch(() => {});
  }, []);

  async function run() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await api.createTimelapse({
        aoi_name: aoiName, index_code: indexCode, start, end, step_months: stepMonths, fps: 1,
      });
      setResult(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3 text-sm">
      <p className="text-slate-500">
        Renders a print-ready cartographic timelapse (graticule, north arrow, scale bar, legend) via
        geemap/cartoee — needs the Earth Engine backend configured.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <label className="block col-span-2">
          Area (whole state or one district)
          <select value={aoiName} onChange={(e) => setAoiName(e.target.value)} className="w-full border rounded px-2 py-1">
            <option value="Kerala">Kerala (whole state)</option>
            {districts.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </label>
        <label className="block">
          Index
          <select value={indexCode} onChange={(e) => setIndexCode(e.target.value)} className="w-full border rounded px-2 py-1">
            <option value="NDVI">NDVI</option>
            <option value="NDDI">NDDI (drought)</option>
            <option value="NDWI">NDWI</option>
          </select>
        </label>
        <label className="block">
          Step (months)
          <input type="number" min={1} max={12} value={stepMonths} onChange={(e) => setStepMonths(Number(e.target.value))} className="w-full border rounded px-2 py-1" />
        </label>
        <label className="block">
          Start
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="w-full border rounded px-2 py-1" />
        </label>
        <label className="block">
          End
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="w-full border rounded px-2 py-1" />
        </label>
      </div>
      <button onClick={run} disabled={loading} className="bg-canopy-green text-white px-4 py-2 rounded disabled:opacity-50">
        {loading ? "Generating..." : "Generate timelapse"}
      </button>
      {error && <p className="text-red-600">{error}</p>}
      {result && (
        <p className="text-slate-600">
          Generated {result.frame_count} frames for <strong>{aoiName}</strong> — run <code>{result.run_id}</code>.
          Server path: <code className="text-xs">{result.gif_path}</code>
        </p>
      )}
    </div>
  );
}
