import { useState } from "react";

import { useDoctors } from "@/features/appointments";
import { usePermission } from "@/features/auth";
import { ErrorText, Loading } from "@/shared/ui/Feedback";
import { PageHeader } from "@/shared/ui/PageHeader";

import {
  useAddDoctor,
  useAddLocation,
  useAddMember,
  useBookingRules,
  useLocations,
  useMembers,
  useSaveBookingRules,
  useSetHours,
  useUpdateDoctor,
} from "../api/settings";
import { BookingRulesForm } from "../components/BookingRulesForm";
import { DoctorsPanel } from "../components/DoctorsPanel";
import { LocationsPanel } from "../components/LocationsPanel";
import { UsersPanel } from "../components/UsersPanel";

type Tab = "doctors" | "locations" | "rules" | "users";

/** Clinic set-up (PRD AP-7.7). Tabs appear only with the matching permission. */
export function SettingsPage() {
  const tabs: { id: Tab; label: string; allowed: boolean }[] = [
    { id: "doctors", label: "Doctors & hours", allowed: usePermission("doctor.manage") },
    { id: "locations", label: "Locations", allowed: usePermission("locations.manage") },
    { id: "rules", label: "Booking rules", allowed: usePermission("appointment.settings.manage") },
    { id: "users", label: "Users", allowed: usePermission("users.manage") },
  ];
  const visible = tabs.filter((t) => t.allowed);
  const [tab, setTab] = useState<Tab | undefined>(visible[0]?.id);

  const doctors = useDoctors();
  const locations = useLocations();
  const rules = useBookingRules();
  const members = useMembers();
  const addDoctor = useAddDoctor();
  const updateDoctor = useUpdateDoctor();
  const setHours = useSetHours();
  const addLocation = useAddLocation();
  const saveRules = useSaveBookingRules();
  const addMember = useAddMember();
  const error = addDoctor.error ?? updateDoctor.error ?? setHours.error ?? addLocation.error ?? saveRules.error ?? addMember.error;

  if (visible.length === 0) return <p className="text-sm text-slate-500">You don't have access to settings.</p>;

  return (
    <div>
      <PageHeader title="Settings" />
      <nav className="mb-4 flex gap-1 border-b border-slate-200">
        {visible.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === t.id ? "border-brand font-medium" : "border-transparent text-slate-500"}`}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <ErrorText error={error} />

      {tab === "doctors" &&
        (doctors.data && locations.data ? (
          <DoctorsPanel
            doctors={doctors.data}
            locations={locations.data}
            busy={addDoctor.isPending || updateDoctor.isPending || setHours.isPending}
            onAdd={(d) => addDoctor.mutate(d)}
            onSaveHours={(id, hours) => setHours.mutate({ id, hours })}
            onToggleActive={(id, active) => updateDoctor.mutate({ id, body: { is_active: active } })}
          />
        ) : (
          <Loading />
        ))}
      {tab === "locations" &&
        (locations.data ? (
          <LocationsPanel locations={locations.data} busy={addLocation.isPending} onAdd={(l) => addLocation.mutate(l)} />
        ) : (
          <Loading />
        ))}
      {tab === "rules" &&
        (rules.data ? (
          <BookingRulesForm rules={rules.data} busy={saveRules.isPending} onSave={(r) => saveRules.mutate(r)} />
        ) : (
          <Loading />
        ))}
      {tab === "users" &&
        (members.data ? (
          <UsersPanel members={members.data} busy={addMember.isPending} onAdd={(m) => addMember.mutate(m)} />
        ) : (
          <Loading />
        ))}
      {saveRules.isSuccess && tab === "rules" && <p className="mt-2 text-sm text-emerald-700">Saved.</p>}
    </div>
  );
}
