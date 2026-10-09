import type { ButtonHTMLAttributes } from "react";

const VARIANT = {
  primary: "bg-brand text-white hover:opacity-90",
  ghost: "text-slate-600 hover:bg-slate-100",
} as const;

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof VARIANT };

export function Button({ variant = "primary", className = "", type = "button", ...rest }: Props) {
  return (
    <button
      type={type}
      className={`rounded-md px-4 py-2 text-sm font-medium disabled:opacity-50 ${VARIANT[variant]} ${className}`}
      {...rest}
    />
  );
}
