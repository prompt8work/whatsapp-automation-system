import { ErrorText, Loading } from "@/shared/ui/Feedback";

import { usePaymentSettings, useSavePaymentSettings, useSaveRazorpaySecrets } from "../api/payments";
import { PaymentSettingsForm } from "../components/PaymentSettingsForm";

/** Settings → Payments tab (needs payment.settings.manage). */
export function PaymentSettingsPanel() {
  const settings = usePaymentSettings();
  const save = useSavePaymentSettings();
  const saveSecrets = useSaveRazorpaySecrets();
  if (settings.isLoading) return <Loading />;
  if (!settings.data) return <ErrorText error={settings.error} />;
  return (
    <div className="space-y-3">
      <ErrorText error={save.error ?? saveSecrets.error} />
      {(save.isSuccess || saveSecrets.isSuccess) && <p className="text-sm text-emerald-700">Saved.</p>}
      <PaymentSettingsForm
        key={JSON.stringify(settings.data)}
        settings={settings.data}
        busy={save.isPending || saveSecrets.isPending}
        onSave={(s) => save.mutate(s)}
        onSaveSecrets={(s) => saveSecrets.mutate(s)}
      />
    </div>
  );
}
