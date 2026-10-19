import type { z } from "zod";
import { ApiError } from "./schemas";

export class HttpError extends Error {
  status: number;
  kind: string | undefined;
  constructor(status: number, message: string, kind?: string) {
    super(message);
    this.status = status;
    this.kind = kind;
  }
}

const CSRF = { "x-chatlpt": "1" };

export async function request<T>(schema: z.ZodType<T>, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: { "content-type": "application/json", ...CSRF, ...(init.headers ?? {}) },
  });
  if (!response.ok) throw await toError(response);
  if (response.status === 204) return undefined as T;
  return schema.parse(await response.json());
}

export async function toError(response: Response): Promise<HttpError> {
  try {
    const body = ApiError.parse(await response.json());
    return new HttpError(response.status, body.error, body.type);
  } catch {
    return new HttpError(response.status, response.statusText || "request failed");
  }
}

export const csrfHeaders = CSRF;
