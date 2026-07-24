"use client";

import { motion } from "framer-motion";
import { Item, Reveal } from "./motion-primitives";

export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden px-6 pt-40 pb-28">
      {/* Decorative background layers */}
      <div className="hero-glow pointer-events-none absolute inset-0 -z-10" />
      <div className="bg-grid pointer-events-none absolute inset-0 -z-10 [mask-image:radial-gradient(70%_60%_at_50%_0%,black,transparent)]" />

      <div className="mx-auto max-w-3xl text-center">
        <Reveal>
          <Item
            as="a"
            className="mx-auto mb-8 inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--card)] px-4 py-1.5 text-sm text-muted transition-colors hover:text-foreground"
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-indigo-500" />
            </span>
            Nova 2.0 is now in public beta
            <span aria-hidden>→</span>
          </Item>

          <Item
            as="h1"
            className="text-balance text-5xl font-semibold leading-[1.05] tracking-tight sm:text-6xl md:text-7xl"
          >
            The workspace that <span className="text-gradient">moves at</span> the
            speed of thought
          </Item>

          <Item
            as="p"
            className="mx-auto mt-7 max-w-xl text-balance text-lg leading-relaxed text-muted"
          >
            Plan, build, and ship in one calm, fast interface. Nova keeps your
            team in flow with keyboard-first navigation and thoughtfully
            designed workflows.
          </Item>

          <Item className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a
              href="#get-started"
              className="group inline-flex items-center gap-2 rounded-full bg-foreground px-6 py-3 text-sm font-medium text-background transition-transform hover:scale-[1.03] active:scale-95"
            >
              Start for free
              <span className="transition-transform group-hover:translate-x-0.5" aria-hidden>
                →
              </span>
            </a>
            <a
              href="#demo"
              className="inline-flex items-center gap-2 rounded-full border border-[var(--border-strong)] px-6 py-3 text-sm font-medium text-foreground/90 transition-colors hover:bg-[var(--card)]"
            >
              Book a demo
            </a>
          </Item>
        </Reveal>
      </div>

      {/* Floating product preview */}
      <motion.div
        initial={{ opacity: 0, y: 60, rotateX: 12 }}
        whileInView={{ opacity: 1, y: 0, rotateX: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 1, ease: [0.22, 1, 0.36, 1], delay: 0.15 }}
        style={{ perspective: 1200 }}
        className="mx-auto mt-20 max-w-5xl"
      >
        <div className="relative rounded-2xl border border-[var(--border-strong)] bg-[var(--card)] p-2 shadow-2xl shadow-indigo-500/10">
          <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-background">
            {/* Fake window chrome */}
            <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3">
              <span className="h-3 w-3 rounded-full bg-red-400/80" />
              <span className="h-3 w-3 rounded-full bg-yellow-400/80" />
              <span className="h-3 w-3 rounded-full bg-green-400/80" />
              <span className="ml-4 h-5 w-64 rounded-md bg-[var(--card)]" />
            </div>
            {/* Fake app body */}
            <div className="grid grid-cols-[180px_1fr] gap-0">
              <div className="hidden flex-col gap-2 border-r border-[var(--border)] p-4 sm:flex">
                {["Inbox", "Roadmap", "Sprints", "Views", "Team"].map((s, i) => (
                  <div
                    key={s}
                    className={`h-8 rounded-lg px-3 text-sm leading-8 text-muted ${
                      i === 1 ? "bg-[var(--card)] text-foreground" : ""
                    }`}
                  >
                    {s}
                  </div>
                ))}
              </div>
              <div className="space-y-3 p-6">
                {[92, 76, 84, 60, 70].map((w, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="h-4 w-4 rounded border border-[var(--border-strong)]" />
                    <span
                      className="h-4 rounded bg-[var(--card)]"
                      style={{ width: `${w}%` }}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </section>
  );
}
