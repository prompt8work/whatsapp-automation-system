import { Button } from "@/shared/ui/Button";

import { activeTenantName, roleLabel, type Me } from "../model/session";

type Props = {
  me: Me;
  onSwitchTenant: (tenantId: string) => void;
  onLogout: () => void;
  busy: boolean;
};

/** Who is signed in, which clinic is active, switch clinic, sign out. */
export function AccountMenu({ me, onSwitchTenant, onLogout, busy }: Props) {
  return (
    <div className="flex items-center gap-3 text-sm">
      {me.memberships.length > 1 ? (
        <select
          aria-label="Clinic"
          value={me.active_tenant_id ?? ""}
          disabled={busy}
          onChange={(e) => onSwitchTenant(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1"
        >
          {me.memberships.map((m) => (
            <option key={m.tenant_id} value={m.tenant_id}>
              {m.tenant_name}
            </option>
          ))}
        </select>
      ) : (
        <span className="font-medium">{activeTenantName(me) ?? "Platform"}</span>
      )}
      <span className="text-slate-500">
        {me.full_name} · {roleLabel(me.role)}
      </span>
      <Button variant="ghost" onClick={onLogout} disabled={busy}>
        Sign out
      </Button>
    </div>
  );
}
