"use client";

export default function DataSourceSelector({
  value, onChange,
}: { value: "sentinel-2" | "landsat"; onChange: (v: "sentinel-2" | "landsat") => void }) {
  return (
    <div className="space-y-2 text-sm">
      <label className="flex items-center gap-2">
        <input type="radio" name="source" checked={value === "sentinel-2"} onChange={() => onChange("sentinel-2")} />
        <span>
          <strong>Sentinel-2</strong> — 10 m, L2A surface reflectance, ~5-day revisit.
          <span className="block text-slate-500">Primary source (COPERNICUS/S2_SR_HARMONIZED). No thermal band.</span>
        </span>
      </label>
      <label className="flex items-center gap-2">
        <input type="radio" name="source" checked={value === "landsat"} onChange={() => onChange("landsat")} />
        <span>
          <strong>Landsat 8/9</strong> — 30 m, Collection 2 Level-2, ~16-day revisit.
          <span className="block text-slate-500">Includes thermal band — required for TCI / VHI.</span>
        </span>
      </label>
    </div>
  );
}
