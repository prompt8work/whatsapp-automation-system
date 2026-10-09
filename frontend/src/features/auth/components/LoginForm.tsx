import { useState, type FormEvent } from "react";

import { Button } from "@/shared/ui/Button";

import { loginSchema, type LoginInput } from "../model/session";

type Props = {
  onSubmit: (input: LoginInput) => void;
  pending: boolean;
  error: string | null;
};

export function LoginForm({ onSubmit, pending, error }: Props) {
  const [fieldError, setFieldError] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const parsed = loginSchema.safeParse({
      email: form.get("email"),
      password: form.get("password"),
    });
    if (!parsed.success) {
      setFieldError(parsed.error.issues[0]?.message ?? "Check the form");
      return;
    }
    setFieldError(null);
    onSubmit(parsed.data);
  }

  const message = fieldError ?? error;
  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <label className="block text-sm">
        <span className="mb-1 block font-medium">Email</span>
        <input
          name="email"
          type="email"
          autoComplete="username"
          className="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block font-medium">Password</span>
        <input
          name="password"
          type="password"
          autoComplete="current-password"
          className="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </label>
      {message && (
        <p role="alert" className="text-sm text-rose-600">
          {message}
        </p>
      )}
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
