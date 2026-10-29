export const API_BASE = (import.meta.env.VITE_API_URL ? `${import.meta.env.VITE_API_URL.replace(/\/+$/, '')}/api/v1` : '/api/v1')
const TOKEN_KEY = 'statease.token'

export class ApiError extends Error {
  code: string
  status: number
  details: unknown
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

// The session token is kept in localStorage so users stay signed in across tabs and restarts.
export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable */
  }
}

type Query = Record<string, string | number | boolean | null | undefined>

function url(path: string, query?: Query) {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  const s = qs.toString()
  return `${API_BASE}${path}${s ? `?${s}` : ''}`
}

async function request<T>(method: string, path: string, opts: { query?: Query; body?: unknown; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  let res: Response
  try {
    res = await fetch(url(path, opts.query), { method, headers, body })
  } catch {
    throw new ApiError(0, 'network_error', 'The server could not be reached. Check that the backend is running.')
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  const data = text ? safeJson(text) : null
  if (!res.ok) {
    const err = (data as { error?: { code: string; message: string; details?: unknown } } | null)?.error
    if (res.status === 401) window.dispatchEvent(new CustomEvent('statease:unauthorized'))
    throw new ApiError(res.status, err?.code ?? 'http_error', err?.message ?? `Request failed (${res.status}).`, err?.details)
  }
  return data as T
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>('GET', path, { query }),
  post: <T>(path: string, body?: unknown, query?: Query) => request<T>('POST', path, { body, query }),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, { body }),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, { body }),
  del: <T = void>(path: string) => request<T>('DELETE', path),
  upload: <T>(path: string, form: FormData) => request<T>('POST', path, { form }),
}

/** Download a file through fetch so the auth header is sent; saves it with the server-provided name. */
export async function download(path: string, init?: { method?: string; body?: unknown; fallbackName?: string }) {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (init?.body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(path.startsWith('/api') ? path : `${API_BASE}${path}`, {
    method: init?.method ?? 'GET',
    headers,
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  })
  if (!res.ok) {
    const data = safeJson(await res.text()) as { error?: { code: string; message: string } } | null
    throw new ApiError(res.status, data?.error?.code ?? 'download_failed', data?.error?.message ?? 'Download failed.')
  }
  const disposition = res.headers.get('Content-Disposition') ?? ''
  const match = /filename="?([^";]+)"?/i.exec(disposition)
  const name = match?.[1] ?? init?.fallbackName ?? 'download'
  const blob = await res.blob()
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(href), 2000)
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message
  if (e instanceof Error) return e.message
  return 'Something went wrong.'
}

/** Multipart upload with progress callbacks (fetch cannot report upload progress). */
export function uploadWithProgress<T>(path: string, form: FormData, onProgress: (fraction: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}${path}`)
    const token = getToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
    xhr.onerror = () => reject(new ApiError(0, 'network_error', 'The upload failed. Check your connection.'))
    xhr.onload = () => {
      const data = safeJson(xhr.responseText) as { error?: { code: string; message: string; details?: unknown } } | null
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as T)
      else reject(new ApiError(xhr.status, data?.error?.code ?? 'http_error', data?.error?.message ?? 'Upload failed.', data?.error?.details))
    }
    xhr.send(form)
  })
}
