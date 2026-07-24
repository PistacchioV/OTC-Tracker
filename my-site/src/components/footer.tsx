"use client";

import { Item, Reveal } from "./motion-primitives";

const COLUMNS = [
  {
    title: "Product",
    links: ["Features", "Integrations", "Pricing", "Changelog", "Roadmap"],
  },
  {
    title: "Company",
    links: ["About", "Careers", "Blog", "Customers", "Contact"],
  },
  {
    title: "Resources",
    links: ["Docs", "Guides", "API", "Community", "Status"],
  },
];

export function Footer() {
  return (
    <footer className="relative px-6 pb-12">
      {/* CTA band */}
      <Reveal className="mx-auto max-w-5xl">
        <Item className="relative overflow-hidden rounded-3xl border border-[var(--border-strong)] bg-[var(--card)] px-8 py-16 text-center">
          <div className="hero-glow pointer-events-none absolute inset-0 -z-10" />
          <h2 className="text-balance text-4xl font-semibold tracking-tight sm:text-5xl">
            Ready to move faster?
          </h2>
          <p className="mx-auto mt-4 max-w-md text-lg text-muted">
            Join thousands of teams building their best work in Nova. Free to
            start, no card required.
          </p>
          <a
            id="get-started"
            href="#top"
            className="mt-8 inline-flex items-center gap-2 rounded-full bg-foreground px-6 py-3 text-sm font-medium text-background transition-transform hover:scale-[1.03] active:scale-95"
          >
            Get started free <span aria-hidden>→</span>
          </a>
        </Item>
      </Reveal>

      {/* Footer nav */}
      <div className="mx-auto mt-20 grid max-w-5xl grid-cols-2 gap-10 sm:grid-cols-4">
        <div className="col-span-2 sm:col-span-1">
          <a href="#top" className="flex items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-sm font-bold text-white">
              N
            </span>
            <span className="text-[15px] font-semibold tracking-tight">Nova</span>
          </a>
          <p className="mt-4 max-w-[15rem] text-sm text-muted">
            The workspace that moves at the speed of thought.
          </p>
        </div>

        {COLUMNS.map((col) => (
          <div key={col.title}>
            <h4 className="text-sm font-semibold">{col.title}</h4>
            <ul className="mt-4 space-y-3">
              {col.links.map((l) => (
                <li key={l}>
                  <a
                    href="#"
                    className="text-sm text-muted transition-colors hover:text-foreground"
                  >
                    {l}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="mx-auto mt-14 flex max-w-5xl flex-col items-center justify-between gap-4 border-t border-[var(--border)] pt-8 sm:flex-row">
        <p className="text-sm text-muted">
          © {new Date().getFullYear()} Nova Labs, Inc. All rights reserved.
        </p>
        <div className="flex items-center gap-5 text-sm text-muted">
          <a href="#" className="transition-colors hover:text-foreground">Privacy</a>
          <a href="#" className="transition-colors hover:text-foreground">Terms</a>
          <a href="#" className="transition-colors hover:text-foreground">Security</a>
        </div>
      </div>
    </footer>
  );
}
