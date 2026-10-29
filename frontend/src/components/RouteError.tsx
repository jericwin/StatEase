import { ArrowLeft, Check, Copy, RefreshCw } from 'lucide-react'
import { Component, useEffect, useState, type ErrorInfo, type ReactNode } from 'react'
import { isRouteErrorResponse, Link, useLocation, useRouteError } from 'react-router-dom'
import { Mark } from '@/components/brand/Mark'

/** After a new release the old page may ask for script files that no longer exist. A reload fixes it. */
function isStaleBundle(error: unknown) {
  const msg = error instanceof Error ? error.message : String(error ?? '')
  return /dynamically imported module|Importing a module script failed|error loading dynamically imported|Failed to fetch dynamically|ChunkLoadError/i.test(msg)
}

function describe(error: unknown): { status?: number; title: string; body: string; detail: string } {
  if (isRouteErrorResponse(error)) {
    if (error.status === 404)
      return { status: 404, title: 'This page doesn’t exist', body: 'The link may be out of date, or the project it pointed to was deleted.', detail: `${error.status} ${error.statusText}` }
    return { status: error.status, title: 'The page could not be loaded', body: 'The server answered with an error. Try again in a moment.', detail: `${error.status} ${error.statusText} ${typeof error.data === 'string' ? error.data : ''}`.trim() }
  }
  if (isStaleBundle(error))
    return { title: 'StatEase has been updated', body: 'This tab is still running the previous version. Reload to continue — your projects and reports are saved on the server.', detail: String((error as Error)?.message ?? error) }
  const e = error instanceof Error ? error : new Error(String(error))
  return {
    title: 'Something went wrong on this page',
    body: 'The page hit an error it could not recover from. Your data, results and reports are saved on the server, so reloading is safe.',
    detail: `${e.name}: ${e.message}${e.stack ? `\n\n${e.stack.split('\n').slice(1, 8).join('\n')}` : ''}`,
  }
}

/**
 * Shown by the router when a page throws while rendering or loading.
 * `inApp` keeps it inside the app shell (sidebar stays usable); otherwise it is a full page.
 */
export function RouteError({ inApp = false }: { inApp?: boolean }) {
  const error = useRouteError()
  const location = useLocation()
  const info = describe(error)
  const [copied, setCopied] = useState(false)

  // A stale bundle is fixed by one automatic reload; never loop.
  useEffect(() => {
    if (!isStaleBundle(error)) return
    const key = `statease:reloaded:${location.pathname}`
    try {
      if (sessionStorage.getItem(key)) return
      sessionStorage.setItem(key, '1')
    } catch {
      return // no storage: let the person press Reload instead of risking a loop
    }
    window.location.reload()
  }, [error, location.pathname])

  useEffect(() => {
    if (!isRouteErrorResponse(error)) console.error('[StatEase] page error', error)
  }, [error])

  const copy = async () => {
    const text = `StatEase error report\nPage: ${location.pathname}${location.search}\nTime: ${new Date().toISOString()}\nBrowser: ${navigator.userAgent}\n\n${info.detail}`
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      /* clipboard blocked — the details are still visible below */
    }
  }

  const content = (
    <div className="mx-auto w-full max-w-xl">
      {!inApp && (
        <Link to="/" className="mb-14 inline-flex items-center gap-2.5 text-ink" aria-label="StatEase Analytics home">
          <Mark />
          <span className="display text-[19px] leading-none">StatEase</span>
        </Link>
      )}
      <p className="kicker">{info.status ? `Error ${info.status}` : 'Error'}</p>
      <h1 className="display mt-3 text-[34px] leading-tight sm:text-[40px]">{info.title}</h1>
      <p className="mt-4 text-[15.5px] leading-relaxed text-ink-2">{info.body}</p>
      <div className="mt-8 flex flex-wrap items-center gap-3">
        {info.status !== 404 && (
          <button type="button" onClick={() => window.location.reload()} className="inline-flex h-11 items-center gap-2 rounded-full bg-ink px-5 text-[14.5px] font-medium text-paper hover:opacity-90">
            <RefreshCw className="size-4" /> Reload page
          </button>
        )}
        <Link to={inApp ? '/app' : '/'} className="inline-flex h-11 items-center gap-2 rounded-full border border-paper-line bg-surface px-5 text-[14.5px] font-medium text-ink hover:border-ink/40">
          <ArrowLeft className="size-4" /> {inApp ? 'Back to dashboard' : 'Back to home'}
        </Link>
      </div>
      {info.status !== 404 && (
        <details className="mt-10 border-t border-paper-line pt-4 text-[13px] text-ink-2">
          <summary className="cursor-pointer select-none hover:text-ink">Technical details</summary>
          <p className="mt-3">If this keeps happening, copy these details and send them to whoever runs your StatEase installation.</p>
          <pre className="mt-3 max-h-56 overflow-auto rounded-md border border-paper-line bg-paper-2 p-3 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap text-ink">{info.detail}</pre>
          <button type="button" onClick={copy} className="mt-3 inline-flex items-center gap-1.5 font-medium text-ink underline decoration-ink/30 underline-offset-4">
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />} {copied ? 'Copied' : 'Copy details'}
          </button>
        </details>
      )}
    </div>
  )

  if (inApp) return <div className="px-5 py-14 sm:px-10 sm:py-20">{content}</div>
  return <main className="flex min-h-dvh items-center bg-paper px-5 py-16 text-ink sm:px-8">{content}</main>
}

/**
 * Contains a crash to one part of a page (a single figure or table), so the rest of the page keeps working.
 * `resetKey` clears the error when the content changes (e.g. a different chart is shown).
 */
export class ErrorBoundary extends Component<{ children: ReactNode; fallback?: (retry: () => void) => ReactNode; label?: string; resetKey?: unknown }, { error: Error | null; key: unknown }> {
  state = { error: null as Error | null, key: this.props.resetKey }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  static getDerivedStateFromProps(props: { resetKey?: unknown }, state: { error: Error | null; key: unknown }) {
    return props.resetKey !== state.key ? { error: null, key: props.resetKey } : null
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[StatEase] ${this.props.label ?? 'component'} failed`, error, info.componentStack)
  }

  retry = () => this.setState({ error: null })

  render() {
    if (!this.state.error) return this.props.children
    if (this.props.fallback) return this.props.fallback(this.retry)
    return (
      <div role="alert" className="rounded-md border border-dashed border-line bg-surface-2 p-4 text-[13px] text-muted">
        <p className="font-medium text-fg">{this.props.label ? `This ${this.props.label} couldn’t be displayed.` : 'This part of the page couldn’t be displayed.'}</p>
        <p className="mt-1">The rest of the page still works, and nothing was lost.</p>
        <button type="button" onClick={this.retry} className="mt-2 inline-flex items-center gap-1.5 font-medium text-fg underline underline-offset-4">
          <RefreshCw className="size-3.5" /> Try again
        </button>
      </div>
    )
  }
}
