"use client";

import { useState } from "react";

/**
 * Print-ready view: shows the cartographic timelapse frame (already
 * rendered server-side with graticule / north arrow / scale bar /
 * legend by services/timelapse.py) full-page, so an official can hit
 * Ctrl/Cmd+P straight from the browser. Pass the served PNG/GIF path
 * via ?src=.
 */
export default function PrintPage({ searchParams }: { searchParams: { src?: string; title?: string } }) {
  const [src] = useState(searchParams.src || "");
  return (
    <div id="printable-map" className="p-6">
      <div className="no-print mb-4">
        <button onClick={() => window.print()} className="bg-canopy-dark text-white px-4 py-2 rounded">
          Print / Save as PDF
        </button>
      </div>
      <h2 className="text-lg font-semibold mb-2">{searchParams.title || "Canopy GeoAI — Timelapse Frame"}</h2>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="Cartographic timelapse frame" className="w-full border" />
      ) : (
        <p className="text-slate-500 text-sm">No frame source provided (append ?src=/path/to/frame.png).</p>
      )}
    </div>
  );
}
