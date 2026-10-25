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
    const validation = Array.isArray(detail) ? detail.flatMap((item: unknown) => {
      if (!item || typeof item !== 'object' || !('msg' in item) || typeof item.msg !== 'string') return [];
      const field = 'loc' in item && Array.isArray(item.loc) ? item.loc.filter((part: unknown) => part !== 'body').join('.') : '';
      return [field ? `${field}: ${item.msg}` : item.msg];
    }).join('; ') : '';
    throw new ApiError(typeof detail === 'string' ? detail : validation || `${path} failed (${res.status})`, res.status);
  }
  return res.json();
}
