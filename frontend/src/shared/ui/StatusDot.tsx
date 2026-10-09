const TONE_CLASS = {
  good: "bg-emerald-500",
  bad: "bg-rose-500",
  unknown: "bg-slate-300",
} as const;

export type Tone = keyof typeof TONE_CLASS;

export function StatusDot({ tone, label }: { tone: Tone; label: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden className={`size-2.5 rounded-full ${TONE_CLASS[tone]}`} />
      <span>{label}</span>
    </span>
  );
}
