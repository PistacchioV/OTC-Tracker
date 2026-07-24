"use client";

import { motion, type Variants } from "framer-motion";
import type { ReactNode } from "react";

const ease = [0.22, 1, 0.36, 1] as const;

/** Container that staggers its children as it scrolls into view. */
export function Reveal({
  children,
  className,
  delay = 0,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "section" | "header" | "footer";
}) {
  const MotionTag = motion[as];
  return (
    <MotionTag
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-80px" }}
      variants={{
        hidden: {},
        show: { transition: { staggerChildren: 0.08, delayChildren: delay } },
      }}
    >
      {children}
    </MotionTag>
  );
}

/** A single item that fades + rises. Use inside <Reveal>. */
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 22, filter: "blur(6px)" },
  show: {
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { duration: 0.7, ease },
  },
};

export function Item({
  children,
  className,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "span" | "p" | "h1" | "h2" | "h3" | "li" | "a";
}) {
  const MotionTag = motion[as];
  return (
    <MotionTag variants={fadeUp} className={className}>
      {children}
    </MotionTag>
  );
}
