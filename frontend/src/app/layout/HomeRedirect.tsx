import { Navigate } from "react-router";

import { usePermission } from "@/features/auth";

/** Staff land on the request queue; doctors on their appointments. */
export function HomeRedirect() {
  const canApprove = usePermission("appointment.approve");
  return <Navigate to={canApprove ? "/requests" : "/appointments"} replace />;
}
