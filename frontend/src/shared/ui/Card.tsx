import type { ReactNode } from "react";

/** Generic UI building block. shared/ui components know nothing about the business. */
export function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 text-sm font-medium text-slate-500">{title}</h2>
      {children}
    </section>
  );
}
