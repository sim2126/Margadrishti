import { create } from "zustand";

export type Theme = "dark" | "light";

function apply(t: Theme) {
  const el = document.documentElement;
  el.classList.toggle("light", t === "light");
  el.classList.toggle("dark", t === "dark");
  document
    .querySelector<HTMLMetaElement>('meta[name="theme-color"]')
    ?.setAttribute("content", t === "dark" ? "#071e3b" : "#f4f6fa");
}

const stored = (localStorage.getItem("margadrishti-theme") as Theme | null) ?? "dark";
apply(stored); // apply immediately on module load to minimise flash

interface ThemeState {
  theme: Theme;
  toggle: () => void;
}

export const useTheme = create<ThemeState>((set, get) => ({
  theme: stored,
  toggle: () => {
    const next: Theme = get().theme === "dark" ? "light" : "dark";
    localStorage.setItem("margadrishti-theme", next);
    apply(next);
    set({ theme: next });
  },
}));
