import { formatTime } from "@/shared/lib/time";
import { Button } from "@/shared/ui/Button";

type Slot = { start: string };

/** Free times of one day as buttons. */
export function SlotPicker({
  slots,
  timeZone,
  disabled,
  onPick,
}: {
  slots: Slot[];
  timeZone: string;
  disabled: boolean;
  onPick: (start: string) => void;
}) {
  if (slots.length === 0) return <p className="text-sm text-slate-500">No free times that day.</p>;
  return (
    <div className="flex flex-wrap gap-2">
      {slots.map((s) => (
        <Button key={s.start} variant="ghost" disabled={disabled} onClick={() => onPick(s.start)} className="border border-slate-200">
          {formatTime(s.start, timeZone)}
        </Button>
      ))}
    </div>
  );
}
