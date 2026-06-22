import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Impact ramp: map a CII in [0,1] to the warm intensity colour ([r,g,b] for deck.gl). */
export function ciiColor(cii: number): [number, number, number] {
  const stops: Array<[number, [number, number, number]]> = [
    [0.0, [31, 111, 235]],
    [0.35, [76, 195, 138]],
    [0.6, [227, 179, 65]],
    [0.8, [240, 136, 62]],
    [1.0, [248, 81, 73]],
  ];
  const c = Math.max(0, Math.min(1, cii));
  for (let i = 1; i < stops.length; i++) {
    if (c <= stops[i][0]) {
      const [t0, a] = stops[i - 1];
      const [t1, b] = stops[i];
      const f = (c - t0) / (t1 - t0 || 1);
      return [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * f)) as [number, number, number];
    }
  }
  return stops[stops.length - 1][1];
}

/** CSS rgb() string from the same ramp (for chips/legends). */
export function ciiCss(cii: number): string {
  const [r, g, b] = ciiColor(cii);
  return `rgb(${r} ${g} ${b})`;
}

export function ciiLabel(cii: number): string {
  if (cii >= 0.8) return "Critical";
  if (cii >= 0.6) return "High";
  if (cii >= 0.35) return "Moderate";
  return "Low";
}
