/**
 * Live dashboard updates (ARCHITECTURE §8.9). Reads the /api/live Server-Sent Events stream
 * with fetch() - EventSource can't send the Authorization header - and reconnects forever.
 * Each message names the topics that changed ("appointments", "inbox", "payments", ...).
 */
import { env } from "@/shared/config/env";

import { refreshSession, sessionStore } from "./session";

export type LiveUpdate = { changed: string[]; versions: Record<string, number> };

/** Split an SSE text buffer into complete events' data; returns [datas, rest]. */
export function parseSse(buffer: string): [LiveUpdate[], string] {
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  const updates = blocks.flatMap((block) => {
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trim())
      .join("\n");
    if (!data) return [];
    try {
      return [JSON.parse(data) as LiveUpdate];
    } catch {
      return [];
    }
  });
  return [updates, rest];
}

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    });
  });

/** Runs until `signal` aborts. `onChange` gets the changed topics (never on the first hello). */
export async function followLiveUpdates(onChange: (topics: string[]) => void, signal: AbortSignal) {
  let versions: Record<string, number> | null = null;
  while (!signal.aborted) {
    try {
      const url = `${env.apiBaseUrl}/api/live?since=${encodeURIComponent(JSON.stringify(versions ?? {}))}`;
      const token = sessionStore.accessToken();
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: "include",
        signal,
      });
      if (response.status === 401) {
        if (!(await refreshSession())) await sleep(10_000, signal);
        continue;
      }
      if (!response.ok || !response.body) throw new Error(`live ${response.status}`);
      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        const [updates, rest] = parseSse(buffer + value);
        buffer = rest;
        for (const update of updates) {
          if (versions !== null && update.changed.length > 0) onChange(update.changed);
          versions = update.versions;
        }
      }
    } catch {
      if (signal.aborted) return;
      await sleep(5_000, signal); // server or network trouble: polling still covers us
    }
  }
}
