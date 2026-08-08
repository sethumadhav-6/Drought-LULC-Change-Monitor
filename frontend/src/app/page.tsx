"use client";

import { useState } from "react";
import CollapsibleSection from "@/components/CollapsibleSection";
import DataSourceSelector from "@/components/DataSourceSelector";
import IndexSelector from "@/components/IndexSelector";
import TimelapseViewer from "@/components/TimelapseViewer";
import RequestDatasetForm from "@/components/RequestDatasetForm";
import MapViewClient from "@/components/MapViewClient";

export default function DashboardPage() {
  const [dataSource, setDataSource] = useState<"sentinel-2" | "landsat">("sentinel-2");
  const [selectedIndexes, setSelectedIndexes] = useState<string[]>(["NDVI", "NDWI", "NDDI"]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[420px_1fr] h-[calc(100vh-52px)]">
      <aside className="overflow-y-auto p-4 border-r border-slate-200 bg-canopy-bg">
        <h1 className="text-lg font-semibold mb-1">Kerala Drought & LULC Monitor</h1>
        <p className="text-sm text-slate-500 mb-4">
          Pre- vs post-monsoon shrinkage watch — flags large land-cover loss now that could raise
          runoff/landslide risk once the monsoon arrives.
        </p>

        <CollapsibleSection title="Sentinel-2 dataset" defaultOpen>
          <DataSourceSelector value={dataSource} onChange={setDataSource} />
        </CollapsibleSection>

        <CollapsibleSection title="Indexes (indexdatabase.de + literature)" defaultOpen>
          <IndexSelector selected={selectedIndexes} onChange={setSelectedIndexes} />
        </CollapsibleSection>

        <CollapsibleSection title="Timelapse (with graticule / north arrow / scale bar / legend)">
          <TimelapseViewer />
        </CollapsibleSection>

        <CollapsibleSection title="Need a dataset that isn't here? Request it">
          <RequestDatasetForm selectedIndexes={selectedIndexes} dataSource={dataSource} />
        </CollapsibleSection>
      </aside>

      <section className="relative">
        <MapViewClient />
      </section>
    </div>
  );
}
