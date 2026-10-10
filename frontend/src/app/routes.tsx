import { createBrowserRouter, Navigate } from "react-router";

import { AppointmentDetailPage, AppointmentsPage } from "@/features/appointments";
import { LoginPage, RequireAuth } from "@/features/auth";
import { InboxPage } from "@/features/inbox";
import { PrivacyPage } from "@/features/privacy";
import { RequestsPage } from "@/features/requests";
import { SettingsPage } from "@/features/settings";
import { SystemStatusPage } from "@/features/system-status";

import { AppShell } from "./layout/AppShell";
import { HomeRedirect } from "./layout/HomeRedirect";

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
      { index: true, element: <HomeRedirect /> },
      { path: "requests", element: <RequestsPage /> },
      { path: "appointments", element: <AppointmentsPage /> },
      { path: "appointments/:appointmentId", element: <AppointmentDetailPage /> },
      { path: "inbox", element: <InboxPage /> },
      { path: "inbox/:contactId", element: <InboxPage /> },
      { path: "privacy", element: <PrivacyPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "system", element: <SystemStatusPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
