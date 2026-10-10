import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

const INPUT = "rounded-md border border-slate-300 bg-white px-3 py-2 text-sm";

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-slate-700">{label}</span>
      {children}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  // A className (e.g. "w-40") replaces the default full width.
  return <input {...props} className={`${INPUT} ${props.className ?? "w-full"}`} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${INPUT} ${props.className ?? "w-full"}`} />;
}
