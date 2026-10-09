import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useRestoreSession } from "../api/session";

/** Route guard: restores the session from the refresh cookie, else sends to /login. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const session = useRestoreSession();
  const location = useLocation();

  if (session.status === "unknown") {
    return <p className="p-8 text-center text-sm text-slate-500">Loading…</p>;
  }
  if (session.status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}
