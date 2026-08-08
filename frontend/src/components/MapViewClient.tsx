"use client";

import dynamic from "next/dynamic";

// react-leaflet needs `window`, so load it client-side only.
const MapView = dynamic(() => import("./MapView"), { ssr: false });

export default function MapViewClient() {
  return <MapView />;
}
