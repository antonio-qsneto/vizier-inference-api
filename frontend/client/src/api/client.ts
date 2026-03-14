import { env } from "@/env";

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

interface ApiRequestOptions {
  method?: string;
  token?: string | null;
  body?: BodyInit | null;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function flattenErrorMessages(payload: unknown): string[] {
  if (typeof payload === "string") {
    return [payload];
  }

  if (Array.isArray(payload)) {
    return payload.flatMap((entry) => flattenErrorMessages(entry));
  }

  if (isPlainObject(payload)) {
    return Object.entries(payload).flatMap(([key, value]) => {
      const messages = flattenErrorMessages(value);
      return messages.length ? messages.map((message) => `${key}: ${message}`) : [];
    });
  }

  return [];
}

function buildErrorMessage(payload: unknown, statusText: string) {
  const messages = flattenErrorMessages(payload)
    .map((message) => message.trim())
    .filter(Boolean);

  if (messages.length) {
    return messages.join(" ");
  }

  return statusText || "Request failed";
}

export async function apiRequest<T>(
  endpoint: string,
  options: ApiRequestOptions = {},
) {
  const url = endpoint.startsWith("http")
    ? endpoint
    : `${env.apiBaseUrl}${endpoint}`;

  const headers = new Headers(options.headers);

  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const abortController = new AbortController();
  const timeoutHandle = window.setTimeout(
    () => abortController.abort(),
    env.apiTimeoutMs,
  );
  const upstreamSignal = options.signal;
  const onUpstreamAbort = () => abortController.abort();

  if (upstreamSignal) {
    if (upstreamSignal.aborted) {
      abortController.abort();
    } else {
      upstreamSignal.addEventListener("abort", onUpstreamAbort, { once: true });
    }
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? "GET",
      body: options.body ?? null,
      headers,
      signal: abortController.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(
        `Request timed out after ${env.apiTimeoutMs}ms`,
        0,
        null,
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutHandle);
    if (upstreamSignal) {
      upstreamSignal.removeEventListener("abort", onUpstreamAbort);
    }
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");

  if (!response.ok) {
    throw new ApiError(
      buildErrorMessage(payload, response.statusText),
      response.status,
      payload,
    );
  }

  return payload as T;
}

export function isPaginatedResponse<T>(
  payload: T[] | { results?: T[] },
): payload is { results: T[] } {
  return isPlainObject(payload) && Array.isArray(payload.results);
}
