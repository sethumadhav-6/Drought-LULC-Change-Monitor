"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { IndexDef } from "@/lib/types";

export default function IndexSelector({
  selected, onChange,
}: { selected: string[]; onChange: (codes: string[]) => void }) {
  const [indexes, setIndexes] = useState<IndexDef[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.indexes().then(setIndexes).catch((e) => setError(String(e)));
  }, []);

  function toggle(code: string) {
    onChange(selected.includes(code) ? selected.filter((c) => c !== code) : [...selected, code]);
  }

  if (error) {
    return <p className="text-sm text-red-600">Could not load index catalog from backend ({error}). Is the API running?</p>;
  }

  const byCategory = indexes.reduce<Record<string, IndexDef[]>>((acc, i) => {
    (acc[i.category] ||= []).push(i);
    return acc;
  }, {});

  return (
    <div className="space-y-3 text-sm">
      <p className="text-slate-500">
        Standard indices, formulas per the{" "}
        <a className="underline" href="https://www.indexdatabase.de/" target="_blank" rel="noreferrer">Index Database</a>
        {" "}and drought-monitoring literature (Gu 2007; Kogan 1995/1997).
      </p>
      {Object.entries(byCategory).map(([cat, items]) => (
        <div key={cat}>
          <div className="text-xs uppercase tracking-wide text-slate-400 mb-1">{cat}</div>
          {items.map((i) => (
            <label key={i.code} className="flex items-start gap-2 py-1">
              <input type="checkbox" checked={selected.includes(i.code)} onChange={() => toggle(i.code)} className="mt-1" />
              <span>
                <strong>{i.code}</strong> — {i.name}
                <span className="block text-slate-500 font-mono text-xs">{i.formula} · {i.reference}</span>
              </span>
            </label>
          ))}
        </div>
      ))}
    </div>
  );
}
