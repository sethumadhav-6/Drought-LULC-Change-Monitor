import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        canopy: {
          green: "#1a9850",
          dark: "#0f5c30",
          bg: "#f4f7f5",
        },
      },
    },
  },
  plugins: [],
};
export default config;
