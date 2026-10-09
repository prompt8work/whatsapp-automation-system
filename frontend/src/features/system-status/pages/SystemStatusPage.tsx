/**
 * pages/: route-level. Connects api/ hooks to components/. Keep pages thin.
 */
import { useHealthQuery } from "../api/useHealthQuery";
import { HealthCard } from "../components/HealthCard";

export function SystemStatusPage() {
  const health = useHealthQuery();

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">System status</h1>
      <HealthCard health={health.data} failed={health.isError} />
    </div>
  );
}
