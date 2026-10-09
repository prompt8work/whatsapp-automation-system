/**
 * components/: presentational. Data arrives via props; no fetching, no routing.
 */
import { Card } from "@/shared/ui/Card";
import { StatusDot } from "@/shared/ui/StatusDot";

import { describeHealth, type Health } from "../model/health";

type Props = { health: Health | undefined; failed: boolean };

export function HealthCard({ health, failed }: Props) {
  const { label, tone } = failed
    ? { label: "API unreachable", tone: "bad" as const }
    : describeHealth(health);

  return (
    <Card title="Platform API">
      <StatusDot tone={tone} label={label} />
      {health && (
        <dl className="mt-4 grid grid-cols-2 gap-y-1 text-sm text-slate-600">
          <dt>Environment</dt>
          <dd>{health.environment}</dd>
          <dt>Version</dt>
          <dd>{health.version}</dd>
        </dl>
      )}
    </Card>
  );
}
