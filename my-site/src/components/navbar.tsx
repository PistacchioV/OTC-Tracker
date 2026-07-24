"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { ThemeToggle } from "./theme-toggle";

const LINKS = [
  { label: "Product", href: "#product" },
  { label: "Features", href: "#features" },
  { label: "Pricing", href: "#pricing" },
  { label: "Docs", href: "#docs" },
];

export function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <motion.header
      initial={{ y: -24, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className="fixed inset-x-0 top-0 z-50 flex justify-center px-4 pt-4"
    >
      <nav
        className={`flex w-full max-w-5xl items-center justify-between gap-4 rounded-full border px-3 py-2 transition-all duration-300 ${
          scrolled
            ? "glass border-[var(--border-strong)] shadow-[0_8px_30px_rgba(0,0,0,0.12)]"
            : "border-transparent"
        }`}
      >
        {/* Brand */}
        <a href="#top" className="flex items-center gap-2 pl-2">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-sm font-bold text-white shadow-lg shadow-indigo-500/30">
            N
          </span>
          <span className="text-[15px] font-semibold tracking-tight">Nova</span>
        </a>

        {/* Desktop links */}
        <ul className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <li key={l.href}>
              <a
                href={l.href}
                className="rounded-full px-3.5 py-1.5 text-sm text-muted transition-colors hover:bg-[var(--card)] hover:text-foreground"
              >
                {l.label}
              </a>
            </li>
          ))}
        </ul>

        {/* Actions */}
        <div className="flex items-center gap-2 pr-1">
          <ThemeToggle />
          <a
            href="#get-started"
            className="hidden rounded-full bg-foreground px-4 py-1.5 text-sm font-medium text-background transition-transform hover:scale-[1.03] active:scale-95 sm:inline-block"
          >
            Get started
          </a>
          <button
            aria-label="Menu"
            onClick={() => setOpen((v) => !v)}
            className="grid h-9 w-9 place-items-center rounded-full border border-[var(--border)] md:hidden"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              {open ? <path d="M18 6 6 18M6 6l12 12" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
        </div>
      </nav>

      {/* Mobile menu */}
      {open && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass absolute top-20 w-[calc(100%-2rem)] max-w-5xl rounded-2xl border border-[var(--border-strong)] p-2 md:hidden"
        >
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className="block rounded-xl px-4 py-3 text-sm text-muted hover:bg-[var(--card)] hover:text-foreground"
            >
              {l.label}
            </a>
          ))}
        </motion.div>
      )}
    </motion.header>
  );
}
