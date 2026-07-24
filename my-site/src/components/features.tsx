"use client";

import { Item, Reveal } from "./motion-primitives";

const FEATURES = [
  {
    title: "Blazing fast",
    body: "Every interaction is optimistic and local-first. No spinners, no waiting — just instant feedback.",
    icon: (
      <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z" />
    ),
  },
  {
    title: "Keyboard-first",
    body: "Command everything from anywhere. A thoughtful palette puts your whole workspace one keystroke away.",
    icon: (
      <>
        <rect x="2" y="6" width="20" height="12" rx="2" />
        <path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M8 14h8" />
      </>
    ),
  },
  {
    title: "Built for teams",
    body: "Real-time presence, shared views, and comments keep everyone aligned without the noise.",
    icon: (
      <>
        <circle cx="9" cy="7" r="4" />
        <path d="M17 11a4 4 0 1 0-2-7.5M2 21a7 7 0 0 1 14 0M16 21a7 7 0 0 0-3-5.7" />
      </>
    ),
  },
  {
    title: "Beautifully themed",
    body: "A refined dark and light mode with subtle gradients that adapt to your environment automatically.",
    icon: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4 12H2M22 12h-2M6 6 4.5 4.5M19.5 19.5 18 18M6 18l-1.5 1.5M19.5 4.5 18 6" />
      </>
    ),
  },
  {
    title: "Fully extensible",
    body: "A clean API and rich integrations let you wire Nova into the tools your team already loves.",
    icon: (
      <path d="M14.7 6.3a4 4 0 0 0-5.6 0l-3 3a4 4 0 0 0 5.6 5.6l1-1M9.3 17.7a4 4 0 0 0 5.6 0l3-3a4 4 0 0 0-5.6-5.6l-1 1" />
    ),
  },
  {
    title: "Private by design",
    body: "End-to-end encryption and granular permissions keep your most sensitive work exactly where it belongs.",
    icon: (
      <>
        <rect x="4" y="11" width="16" height="10" rx="2" />
        <path d="M8 11V7a4 4 0 0 1 8 0v4" />
      </>
    ),
  },
];

export function Features() {
  return (
    <section id="features" className="relative px-6 py-28">
      <Reveal className="mx-auto max-w-2xl text-center">
        <Item
          as="span"
          className="text-sm font-medium uppercase tracking-widest text-indigo-500 dark:text-indigo-400"
        >
          Why Nova
        </Item>
        <Item
          as="h2"
          className="mt-4 text-balance text-4xl font-semibold tracking-tight sm:text-5xl"
        >
          Everything you need, nothing you don&apos;t
        </Item>
        <Item as="p" className="mx-auto mt-5 max-w-lg text-lg text-muted">
          Purpose-built primitives that get out of your way and let your team do
          its best work.
        </Item>
      </Reveal>

      <Reveal className="mx-auto mt-16 grid max-w-5xl grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f) => (
          <Item
            key={f.title}
            className="group rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 transition-all duration-300 hover:-translate-y-1 hover:border-[var(--border-strong)]"
          >
            <div className="mb-5 grid h-11 w-11 place-items-center rounded-xl border border-[var(--border-strong)] bg-background text-indigo-500 transition-colors group-hover:text-fuchsia-500 dark:text-indigo-400">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                {f.icon}
              </svg>
            </div>
            <h3 className="text-lg font-semibold tracking-tight">{f.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">{f.body}</p>
          </Item>
        ))}
      </Reveal>
    </section>
  );
}
