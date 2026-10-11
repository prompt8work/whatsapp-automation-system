import { NavLink, Outlet } from "react-router";

import { SessionMenu, usePermission } from "@/features/auth";
import { useDeletionRequests } from "@/features/privacy";
import { useRequests } from "@/features/requests";

import { useLiveUpdates } from "./useLiveUpdates";

function RequestsLink() {
  const requests = useRequests();
  const count = requests.data?.length ?? 0;
  return (
    <>
      Requests
      {count > 0 && <span className="ml-1 rounded-full bg-amber-500 px-1.5 text-xs text-white">{count}</span>}
    </>
  );
}

function PrivacyLink() {
  const canDecide = usePermission("case.manage");
  const requests = useDeletionRequests(canDecide);
  const pending = requests.data?.filter((r) => r.status === "pending").length ?? 0;
  return (
    <>
      Privacy
      {pending > 0 && <span className="ml-1 rounded-full bg-rose-500 px-1.5 text-xs text-white">{pending}</span>}
    </>
  );
}

export function AppShell() {
  useLiveUpdates();
  const canManageDoctors = usePermission("doctor.manage");
  const canManageUsers = usePermission("users.manage");
  const nav = [
    { to: "/requests", label: <RequestsLink />, show: usePermission("appointment.approve") },
    { to: "/appointments", label: "Appointments", show: usePermission("appointment.read") },
    { to: "/inbox", label: "Inbox", show: usePermission("inbox.read") },
    { to: "/payments", label: "Payments", show: usePermission("payment.read") },
    { to: "/privacy", label: <PrivacyLink />, show: usePermission("retention.read") },
    {
      to: "/settings",
      label: "Settings",
      show: canManageDoctors || canManageUsers,
    },
    { to: "/system", label: "System", show: true },
  ];

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <span className="font-semibold text-brand">Clinic Dashboard</span>
          <nav className="flex flex-wrap gap-4 text-sm">
            {nav
              .filter((item) => item.show)
              .map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    isActive ? "font-medium text-slate-900" : "text-slate-500 hover:text-slate-900"
                  }
                >
                  {item.label}
                </NavLink>
              ))}
          </nav>
          <div className="ml-auto">
            <SessionMenu />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
