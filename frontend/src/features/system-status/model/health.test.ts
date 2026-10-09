import { describeHealth } from "./health";

describe("describeHealth", () => {
  it("is unknown while loading", () => {
    expect(describeHealth(undefined).tone).toBe("unknown");
  });

  it("is good when the API and database are up", () => {
    expect(describeHealth({ status: "ok", environment: "local", version: "0.1.0" })).toEqual({
      label: "All systems operational",
      tone: "good",
    });
  });

  it("is bad when the database is unreachable", () => {
    expect(
      describeHealth({ status: "unavailable", environment: "local", version: "0.1.0" }).tone,
    ).toBe("bad");
  });
});
