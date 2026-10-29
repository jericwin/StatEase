import * as TabsPrimitive from '@radix-ui/react-tabs'
import { AlertTriangle, CheckCircle2, CircleAlert, Info, Loader2, XCircle } from 'lucide-react'
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger'

const tones: Record<Tone, string> = {
  neutral: 'bg-surface-3 text-fg-2 border-line',
  accent: 'bg-accent-soft text-accent border-accent/25',
  success: 'bg-success-soft text-success border-success/25',
  warning: 'bg-warning-soft text-warning border-warning/30',
  danger: 'bg-danger-soft text-danger border-danger/25',
}

export function Badge({ tone = 'neutral', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex h-5 items-center gap-1 rounded-[3px] border px-1.5 text-[11px] font-medium whitespace-nowrap', tones[tone], className)}>
      {children}
    </span>
  )
}

const icons = { info: Info, success: CheckCircle2, warning: AlertTriangle, danger: CircleAlert }

export function Callout({
  tone = 'info',
  title,
  children,
  action,
  className,
}: {
  tone?: 'info' | 'success' | 'warning' | 'danger'
  title?: ReactNode
  children?: ReactNode
  action?: ReactNode
  className?: string
}) {
  const Icon = icons[tone]
  const color = { info: 'border-line bg-surface-2 [&>svg]:text-accent', success: 'border-success/30 bg-success-soft [&>svg]:text-success', warning: 'border-warning/35 bg-warning-soft [&>svg]:text-warning', danger: 'border-danger/30 bg-danger-soft [&>svg]:text-danger' }[tone]
  return (
    <div role={tone === 'danger' ? 'alert' : 'status'} className={cn('flex gap-2.5 rounded-md border px-3 py-2.5 text-[13px]', color, className)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1 text-fg-2">
        {title && <div className="font-medium text-fg">{title}</div>}
        {children && <div className={cn(title && 'mt-0.5')}>{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

export function Spinner({ label = 'Loading', className }: { label?: string; className?: string }) {
  return (
    <div role="status" className={cn('flex items-center gap-2 text-[13px] text-muted', className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden />
      <span>{label}…</span>
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded bg-surface-3', className)} aria-hidden />
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode
  title: string
  description?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center px-6 py-12 text-center', className)}>
      {icon && <div className="mb-3 text-muted [&_svg]:size-6">{icon}</div>}
      <h3 className="text-[15px] font-semibold">{title}</h3>
      {description && <p className="mt-1 max-w-md text-[13px] text-muted">{description}</p>}
      {action && <div className="mt-4 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <Callout
      tone="danger"
      title="Could not load this view"
      action={
        retry && (
          <button className="text-[13px] font-medium underline underline-offset-2" onClick={retry}>
            Retry
          </button>
        )
      }
    >
      {message}
    </Callout>
  )
}

export function Panel({ title, actions, children, className, bodyClassName, description }: {
  title?: ReactNode
  actions?: ReactNode
  description?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={cn('rounded-lg border border-line bg-surface', className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <div className="min-w-0">
            {title && <h2 className="text-[13px] font-semibold">{title}</h2>}
            {description && <p className="text-xs text-muted">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn('p-4', bodyClassName)}>{children}</div>
    </section>
  )
}

export const Tabs = TabsPrimitive.Root
export const TabsContent = TabsPrimitive.Content

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <TabsPrimitive.List className={cn('scroll-thin flex gap-1 overflow-x-auto border-b border-line', className)}>{children}</TabsPrimitive.List>
  )
}

export function TabsTrigger({ value, children, count }: { value: string; children: ReactNode; count?: number }) {
  return (
    <TabsPrimitive.Trigger
      value={value}
      className="-mb-px flex h-9 shrink-0 items-center gap-1.5 border-b-2 border-transparent px-2.5 text-[13px] font-medium text-muted hover:text-fg data-[state=active]:border-accent data-[state=active]:text-fg"
    >
      {children}
      {count !== undefined && <span className="num rounded-[3px] bg-surface-3 px-1 text-[11px] text-fg-2">{count}</span>}
    </TabsPrimitive.Trigger>
  )
}

/* ---------------------------------------------------------------- toasts */

interface Toast {
  id: number
  tone: 'success' | 'danger' | 'info'
  message: string
}
const ToastCtx = createContext<(tone: Toast['tone'], message: string) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((tone: Toast['tone'], message: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t.slice(-3), { id, tone, message }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'danger' ? 7000 : 4000)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed right-3 bottom-3 left-3 z-[70] flex flex-col items-end gap-2 sm:left-auto">
        {toasts.map((t) => {
          const Icon = t.tone === 'success' ? CheckCircle2 : t.tone === 'danger' ? XCircle : Info
          return (
            <div
              key={t.id}
              className="pointer-events-auto flex w-full max-w-sm items-start gap-2.5 rounded-md border border-line bg-surface px-3 py-2.5 text-[13px] shadow-lg"
            >
              <Icon className={cn('mt-0.5 size-4 shrink-0', t.tone === 'success' ? 'text-success' : t.tone === 'danger' ? 'text-danger' : 'text-accent')} />
              <span className="text-fg-2">{t.message}</span>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}

export function useToast() {
  return useContext(ToastCtx)
}
