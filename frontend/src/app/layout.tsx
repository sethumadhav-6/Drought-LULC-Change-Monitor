import type { Metadata } from "next";
import Image from "next/image";
import "leaflet/dist/leaflet.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Canopy GeoAI - Drought & LULC Monitor | Canopy Geospatial Solutions",
  description: "Drought and land use/land cover change monitoring for tropical countries, piloted on Kerala. By Canopy Geospatial Solutions.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-canopy-bg text-slate-800 antialiased">
        <header className="no-print bg-canopy-dark text-white px-6 py-3 flex items-center justify-between">
          <a href="https://www.canopygs.in" target="_blank" rel="noreferrer" className="flex items-center gap-3">
            <Image src="/logo.png" alt="Canopy Geospatial Solutions logo" width={32} height={48} className="h-9 w-auto" priority />
            <span>
              <span className="block font-semibold text-lg leading-tight">Canopy Geospatial Solutions</span>
              <span className="block text-xs text-emerald-100 leading-tight">
                Canopy GeoAI — Drought & LULC Change Monitor · Kerala Pilot · www.canopygs.in
              </span>
            </span>
          </a>
          <nav className="text-sm space-x-4">
            <a href="/" className="hover:underline">Dashboard</a>
            <a href="/admin" className="hover:underline">Admin</a>
          </nav>
        </header>
        <main className="min-h-[calc(100vh-52px)]">{children}</main>
      </body>
    </html>
  );
}
