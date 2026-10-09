import { fireEvent, render, screen } from "@testing-library/react";

import { LoginForm } from "./LoginForm";

function fill(email: string, password: string) {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("LoginForm", () => {
  it("submits valid credentials", () => {
    const onSubmit = vi.fn();
    render(<LoginForm onSubmit={onSubmit} pending={false} error={null} />);

    fill("dr@clinic.com", "secret-password");

    expect(onSubmit).toHaveBeenCalledWith({ email: "dr@clinic.com", password: "secret-password" });
  });

  it("does not submit an invalid email", () => {
    const onSubmit = vi.fn();
    render(<LoginForm onSubmit={onSubmit} pending={false} error={null} />);

    fill("not-an-email", "x");

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid email address");
  });

  it("shows the server error and disables the button while pending", () => {
    render(<LoginForm onSubmit={vi.fn()} pending error="Wrong email or password." />);

    expect(screen.getByRole("alert")).toHaveTextContent("Wrong email or password.");
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
