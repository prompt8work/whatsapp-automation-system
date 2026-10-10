const TONES = {
  neutral: "bg-slate-100 text-slate-700",
  info: "bg-sky-100 text-sky-800",
  good: "bg-emerald-100 text-emerald-800",
  warn: "bg-amber-100 text-amber-800",
  bad: "bg-rose-100 text-rose-800",
} as const;

export type BadgeTone = keyof typeof TONES;

export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: string }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}
