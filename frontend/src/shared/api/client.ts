/**
 * Typed API client. Types come from the backend's OpenAPI schema (ADR-009):
 *   npm run gen:api   -> regenerates ./schema.d.ts
 * Never hand-write request/response types for backend endpoints.
 *
 * Only features' api/ hooks may use this client.
 */
import createClient from "openapi-fetch";

import { env } from "@/shared/config/env";

import type { paths } from "./schema";
import { refreshSession, sessionStore } from "./session";

function withAccessToken(request: Request): Request {
  const token = sessionStore.accessToken();
  if (token) request.headers.set("Authorization", `Bearer ${token}`);
  return request;
}

/** Adds the access token; on 401 refreshes once and retries the request. */
async function authFetch(request: Request): Promise<Response> {
  const retry = request.clone();
  const response = await fetch(withAccessToken(request));
  if (response.status !== 401 || new URL(request.url).pathname.startsWith("/api/auth/")) {
    return response;
  }
  return (await refreshSession()) ? fetch(withAccessToken(retry)) : response;
}

export const api = createClient<paths>({
  baseUrl: env.apiBaseUrl || globalThis.location?.origin,
  credentials: "include",
  fetch: authFetch,
});

/** Error body returned by the backend for every DomainError: { code, message }. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }

  /** Build from an openapi-fetch `error` value of any shape. */
  static from(status: number, body: unknown): ApiError {
    if (body && typeof body === "object" && "code" in body && "message" in body) {
      return new ApiError(status, String(body.code), String(body.message));
    }
    if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") {
      return new ApiError(status, `http.${status}`, body.detail);
    }
    return new ApiError(status, `http.${status}`, "Something went wrong. Please try again.");
  }
}
