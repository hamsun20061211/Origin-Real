import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#050505",
          raised: "#121214",
          border: "#1F1F23",
        },
        accent: {
          DEFAULT: "#00E5FF",
          glow: "#66F0FF",
        },
        neon: {
          DEFAULT: "#00E5FF",
          muted: "rgba(0, 229, 255, 0.12)",
        },
      },
      fontFamily: {
        display: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
      boxShadow: {
        glass: "0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.06)",
        accent: "0 0 40px rgba(0, 229, 255, 0.22)",
      },
    },
  },
  plugins: [],
};

export default config;
