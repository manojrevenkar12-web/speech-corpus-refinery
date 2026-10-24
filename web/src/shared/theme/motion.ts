/** Motion constants (seconds, for framer-motion). Durations match --dur-* in tokens.css. */
export const motion = {
  fast: 0.12,
  base: 0.24,
  ease: [0.2, 0.8, 0.2, 1] as const,
  /** the hours tape fills once, kept hours first, then each loss in turn */
  tapeStep: 0.07,
  tapeStepCap: 12,
  rise: 8,
} as const;

export const tapeDelay = (i: number): number => Math.min(i, motion.tapeStepCap) * motion.tapeStep;
