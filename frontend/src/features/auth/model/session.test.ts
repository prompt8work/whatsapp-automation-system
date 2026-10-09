import type { Me } from "./session";
import { activeTenantName, can, loginErrorMessage, loginSchema, roleLabel } from "./session";

const me: Me = {
  user_id: "u1",
  email: "staff@x.com",
  full_name: "Front Desk",
  is_super_admin: false,
  active_tenant_id: "t2",
  role: "staff",
  permissions: ["contact.read", "locations.read"],
  memberships: [
    { tenant_id: "t1", tenant_name: "Clinic One", role: "admin" },
    { tenant_id: "t2", tenant_name: "Clinic Two", role: "staff" },
  ],
};

describe("auth model", () => {
  it("checks permissions", () => {
    expect(can(me, "contact.read")).toBe(true);
    expect(can(me, "users.manage")).toBe(false);
    expect(can(null, "contact.read")).toBe(false);
  });

  it("names the active clinic", () => {
    expect(activeTenantName(me)).toBe("Clinic Two");
  });

  it("labels roles, including the platform operator", () => {
    expect(roleLabel("doctor")).toBe("Doctor");
    expect(roleLabel(null)).toBe("Platform operator");
  });

  it("maps backend error codes to friendly messages", () => {
    expect(loginErrorMessage("identity.invalid_credentials")).toBe("Wrong email or password.");
    expect(loginErrorMessage("something.else")).toMatch(/could not sign in/i);
  });

  it("validates the login form", () => {
    expect(loginSchema.safeParse({ email: "x", password: "p" }).success).toBe(false);
    expect(loginSchema.safeParse({ email: "a@b.co", password: "p" }).success).toBe(true);
  });
});
