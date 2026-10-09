import { refreshSession, sessionStore, type SessionResponse } from "./session";

const response: SessionResponse = {
  access_token: "access-1",
  token_type: "bearer",
  expires_at: "2026-10-10T10:00:00Z",
  me: {
    user_id: "u1",
    email: "a@b.co",
    full_name: "A",
    is_super_admin: false,
    active_tenant_id: "t1",
    role: "admin",
    permissions: [],
    memberships: [],
  },
};

describe("sessionStore", () => {
  afterEach(() => {
    sessionStore.signOut();
    vi.unstubAllGlobals();
  });

  it("notifies subscribers and exposes the access token only when signed in", () => {
    const listener = vi.fn();
    const unsubscribe = sessionStore.subscribe(listener);

    sessionStore.signIn(response);
    expect(sessionStore.accessToken()).toBe("access-1");
    sessionStore.signOut();
    expect(sessionStore.accessToken()).toBeNull();

    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
  });

  it("shares one refresh request between concurrent callers", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(response), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const results = await Promise.all([refreshSession(), refreshSession(), refreshSession()]);

    expect(results).toEqual([true, true, true]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(sessionStore.get().status).toBe("authenticated");
  });

  it("signs out when the refresh cookie is rejected", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 401 })));

    expect(await refreshSession()).toBe(false);
    expect(sessionStore.get().status).toBe("anonymous");
  });
});
