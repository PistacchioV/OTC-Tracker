"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useTheme } from "./theme-provider";

function SunIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme();

  return (
    <button
      onClick={toggle}
      aria-label="Toggle theme"
      className="relative grid h-9 w-9 place-items-center rounded-full border border-[var(--border)] text-foreground/80 transition-colors hover:bg-[var(--card)] hover:text-foreground"
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          initial={{ y: -8, opacity: 0, rotate: -30 }}
          animate={{ y: 0, opacity: 1, rotate: 0 }}
          exit={{ y: 8, opacity: 0, rotate: 30 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className="absolute grid place-items-center"
        >
          {theme === "dark" ? <MoonIcon /> : <SunIcon />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
