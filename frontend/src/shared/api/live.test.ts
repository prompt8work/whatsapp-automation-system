import { describe, expect, it } from "vitest";

import { parseSse } from "./live";

describe("parseSse", () => {
  it("returns complete events and keeps the unfinished rest", () => {
    const text =
      'retry: 1000\n\nevent: change\ndata: {"changed":["inbox"],"versions":{"inbox":2}}\n\nevent: change\ndata: {"chan';
    const [updates, rest] = parseSse(text);
    expect(updates).toEqual([{ changed: ["inbox"], versions: { inbox: 2 } }]);
    expect(rest).toBe('event: change\ndata: {"chan');
  });

  it("ignores broken data", () => {
    expect(parseSse("data: not json\n\n")[0]).toEqual([]);
  });
});
