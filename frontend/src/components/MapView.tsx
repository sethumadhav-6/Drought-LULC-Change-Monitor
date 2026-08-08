"use client";

import { MapContainer, TileLayer, GeoJSON, ScaleControl } from "react-leaflet";

const KERALA_BBOX: [[number, number], [number, number]] = [
  [8.29, 74.86],
  [12.82, 77.42],
];

export default function MapView({ id = "map" }: { id?: string }) {
  return (
    <div id={id} className="h-full w-full">
      <MapContainer bounds={KERALA_BBOX} className="h-full w-full" scrollWheelZoom>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ScaleControl position="bottomleft" />
      </MapContainer>
    </div>
  );
}
