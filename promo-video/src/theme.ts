import { Easing } from "remotion";
import { loadFont as loadSans } from "@remotion/google-fonts/IBMPlexSans";
import { loadFont as loadSerif } from "@remotion/google-fonts/IBMPlexSerif";
import { loadFont as loadMono } from "@remotion/google-fonts/IBMPlexMono";

export const sans = loadSans("normal", {
  weights: ["400", "500", "600"],
  subsets: ["latin"],
}).fontFamily;
export const serif = loadSerif("normal", {
  weights: ["500", "600"],
  subsets: ["latin"],
}).fontFamily;
export const mono = loadMono("normal", {
  weights: ["400", "500"],
  subsets: ["latin"],
}).fontFamily;

// Palette taken from the StatEase frontend (frontend/src/index.css)
export const c = {
  paper: "#f6f3ec",
  paper2: "#eee8dc",
  line: "#ddd5c5",
  ink: "#14213a",
  ink2: "#4a5468",
  rust: "#b4532a",
  accent: "#1d4f91",
  accentSoft: "#eaf1fa",
  success: "#2f6b48",
  successSoft: "#e9f4ee",
  surface: "#ffffff",
  border: "#e1e4e9",
  chart2: "#b5523b",
};

export const ease = Easing.bezier(0.16, 1, 0.3, 1);
export const clamp = {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
} as const;
