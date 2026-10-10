/**
 * Turn an openapi-fetch result into data or a thrown ApiError (with the backend's error code).
 *
 *   const appointment = await unwrap(api.POST("/api/appointments/{appointment_id}/approve", {...}));
 */
import { ApiError } from "./client";

type Result<T> = { data?: T; error?: unknown; response: Response };

export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) throw ApiError.from(response.status, error);
  return data as T;
}

/** For endpoints that return 204 No Content. */
export async function unwrapEmpty(call: Promise<Result<unknown>>): Promise<void> {
  const { error, response } = await call;
  if (!response.ok) throw ApiError.from(response.status, error);
}
