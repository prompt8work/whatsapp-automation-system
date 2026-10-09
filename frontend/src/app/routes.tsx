import { createBrowserRouter, Navigate } from "react-router";

import { LoginPage, RequireAuth } from "@/features/auth";
import { SystemStatusPage } from "@/features/system-status";

import { AppShell } from "./layout/AppShell";

/** Route table. New pages: add a route here, importing from the feature's index.ts. */
export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/system" replace /> },
      { path: "system", element: <SystemStatusPage /> },
    ],
  },
]);
