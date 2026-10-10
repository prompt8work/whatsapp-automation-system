/** Loading / empty / error states, so every page shows them the same way. */
export function Loading() {
  return <p className="py-8 text-center text-sm text-slate-500">Loading…</p>;
}

export function Empty({ children }: { children: string }) {
  return <p className="rounded-lg border border-dashed border-slate-300 py-10 text-center text-sm text-slate-500">{children}</p>;
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <p role="alert" className="text-sm text-rose-600">
      {message}
    </p>
  );
}
