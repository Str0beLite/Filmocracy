import { token } from './auth';

export const API = ((import.meta.env.VITE_API_URL as string | undefined) || '/api').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function http<T = unknown>(path: string, body?: unknown): Promise<T> {
  const t = token();
  if (!t) throw new ApiError('Sign in first', 401);
  const form = body instanceof FormData;
  const res = await fetch(`${API}${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { Authorization: `Bearer ${t}`, ...(body !== undefined && !form ? { 'Content-Type': 'application/json' } : {}) },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = (await res.json().catch(() => null))?.detail;
    throw new ApiError(typeof detail === 'string' ? detail : `${path} failed (${res.status})`, res.status);
  }
  return res.json();
}
