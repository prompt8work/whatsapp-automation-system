import { useLogout, useSession, useSwitchTenant } from "../api/session";
import { AccountMenu } from "../components/AccountMenu";

/** Header widget: wires the session hooks to the presentational AccountMenu. */
export function SessionMenu() {
  const session = useSession();
  const logout = useLogout();
  const switchTenant = useSwitchTenant();

  if (session.status !== "authenticated") return null;
  return (
    <AccountMenu
      me={session.me}
      busy={logout.isPending || switchTenant.isPending}
      onLogout={() => logout.mutate()}
      onSwitchTenant={(tenantId) => switchTenant.mutate(tenantId)}
    />
  );
}
