import { displayName, handlerLabel } from "./inbox";

describe("inbox model", () => {
  it("says who handles the chat", () => {
    expect(handlerLabel(null, "me")).toBe("Bot");
    expect(handlerLabel({ reason: "bot", started_at: "", assigned_user_id: null }, "me")).toBe("Waiting for staff");
    expect(handlerLabel({ reason: "staff", started_at: "", assigned_user_id: "me" }, "me")).toBe("You");
    expect(handlerLabel({ reason: "staff", started_at: "", assigned_user_id: "you" }, "me")).toBe("Another staff member");
  });

  it("shows the WhatsApp name when known", () => {
    expect(displayName({ profile_name: "Rahul", phone: "+9198" })).toBe("Rahul (+9198)");
    expect(displayName({ profile_name: null, phone: "+9198" })).toBe("+9198");
  });
});
