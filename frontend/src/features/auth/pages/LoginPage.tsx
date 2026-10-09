import { Navigate, useLocation } from "react-router";

import { ApiError } from "@/shared/api/client";
import { Card } from "@/shared/ui/Card";

import { useLogin, useSession } from "../api/session";
import { LoginForm } from "../components/LoginForm";
import { loginErrorMessage } from "../model/session";

export function LoginPage() {
  const session = useSession();
  const login = useLogin();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  if (session.status === "authenticated") return <Navigate to={from} replace />;

  const error = login.error
    ? loginErrorMessage(login.error instanceof ApiError ? login.error.code : undefined)
    : null;

  return (
    <div className="mx-auto mt-24 max-w-sm px-4">
      <h1 className="mb-6 text-center text-xl font-semibold text-brand">Clinic Dashboard</h1>
      <Card title="Sign in">
        <LoginForm onSubmit={(input) => login.mutate(input)} pending={login.isPending} error={error} />
      </Card>
    </div>
  );
}
