import { Plus, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Checkbox, Input } from '@/components/ui/form'
import { Popover } from '@/components/ui/overlay'
import { LEVEL_LABEL } from '@/lib/format'
import type { Level, Role, Variable } from '@/lib/types'
import { cn } from '@/lib/utils'

const LEVEL_DOT: Record<Level, string> = {
  numeric: 'bg-[var(--chart-1)]',
  ordinal: 'bg-[var(--chart-4)]',
  nominal: 'bg-[var(--chart-3)]',
  binary: 'bg-[var(--chart-5)]',
  date: 'bg-muted',
  datetime: 'bg-muted',
  text: 'bg-muted',
  identifier: 'bg-muted',
}

export function LevelDot({ level }: { level: Level }) {
  return <span className={cn('inline-block size-2 shrink-0 rounded-full', LEVEL_DOT[level])} aria-hidden title={LEVEL_LABEL[level]} />
}

/**
 * Accessible variable selector for one analysis role: assigned variables are shown as chips; the
 * picker lists every variable, with ineligible ones disabled and the reason shown.
 */
export function RoleSlot({
  role,
  value,
  variables,
  usedElsewhere,
  onChange,
}: {
  role: Role
  value: string[]
  variables: Variable[]
  usedElsewhere: Set<string>
  onChange: (v: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const single = role.max === 1
  const byName = useMemo(() => Object.fromEntries(variables.map((v) => [v.name, v])), [variables])
  const list = useMemo(() => {
    const term = q.toLowerCase()
    const filtered = variables.filter((v) => !term || v.name.toLowerCase().includes(term) || (v.label ?? '').toLowerCase().includes(term))
    return filtered.sort((a, b) => Number(!role.levels.includes(a.level)) - Number(!role.levels.includes(b.level)))
  }, [variables, q, role.levels])
  const full = role.max !== null && value.length >= role.max
  const allowed = role.levels.map((l) => LEVEL_LABEL[l].toLowerCase()).join(', ')
  const missing = value.length < role.min

  const toggle = (name: string) => {
    if (value.includes(name)) onChange(value.filter((x) => x !== name))
    else if (single) {
      onChange([name])
      setOpen(false)
    } else if (!full) onChange([...value, name])
  }

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[13px] font-medium text-fg">
          {role.label}
          {role.min > 0 && <span className="text-danger" aria-hidden> *</span>}
        </span>
        <span className="text-[11px] text-muted">
          {single ? '1 variable' : role.max ? `${role.min}–${role.max} variables` : `${role.min}+ variables`}
        </span>
      </div>
      {role.description && <p className="text-xs text-muted">{role.description}</p>}
      <div
        className={cn(
          'mt-1.5 flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border bg-surface-2 p-1.5',
          missing ? 'border-dashed border-line-strong' : 'border-line',
        )}
      >
        {value.map((name) => {
          const v = byName[name]
          const bad = v && !role.levels.includes(v.level)
          return (
            <span
              key={name}
              className={cn(
                'inline-flex h-6 max-w-full items-center gap-1.5 rounded-[3px] border bg-surface px-1.5 text-xs',
                bad ? 'border-danger/50 text-danger' : 'border-line-strong',
              )}
            >
              {v && <LevelDot level={v.level} />}
              <span className="truncate">{v?.label || name}</span>
              <button type="button" className="rounded text-muted hover:text-fg" onClick={() => onChange(value.filter((x) => x !== name))} aria-label={`Remove ${name} from ${role.label}`}>
                <X className="size-3.5" />
              </button>
            </span>
          )
        })}
        {(
          <Popover
            open={open}
            onOpenChange={(o) => {
              setOpen(o)
              if (!o) setQ('')
            }}
            className="w-80 p-0"
            trigger={
              <button
                type="button"
                disabled={full && !single}
                className="inline-flex h-6 items-center gap-1 rounded-[3px] px-1.5 text-xs font-medium text-accent hover:bg-accent-soft disabled:opacity-50"
                aria-label={`Add variable to ${role.label}`}
              >
                <Plus className="size-3.5" /> {single ? (value.length ? 'Change' : 'Choose variable') : value.length ? 'Add' : 'Add variables'}
              </button>
            }
          >
            <div className="border-b border-line p-2">
              <Input autoFocus placeholder="Search variables" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search variables" />
              <p className="mt-1.5 text-[11px] text-muted">Needs: {allowed}</p>
            </div>
            <ul className="scroll-thin max-h-72 overflow-y-auto py-1" role="listbox" aria-multiselectable={!single} aria-label={role.label}>
              {list.map((v) => {
                const eligible = role.levels.includes(v.level)
                const selected = value.includes(v.name)
                const elsewhere = usedElsewhere.has(v.name) && !selected
                const disabled = !eligible || elsewhere || (!selected && full && !single)
                return (
                  <li key={v.name} role="option" aria-selected={selected} aria-disabled={disabled}>
                    <button
                      type="button"
                      disabled={disabled}
                      onClick={() => toggle(v.name)}
                      className={cn('flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] hover:bg-surface-3 disabled:cursor-not-allowed disabled:hover:bg-transparent', disabled && 'opacity-55')}
                    >
                      {!single && <Checkbox checked={selected} onCheckedChange={() => {}} disabled={disabled} className="pointer-events-none" aria-label="" />}
                      <LevelDot level={v.level} />
                      <span className="min-w-0 flex-1 truncate">
                        {v.label || v.name}
                        {v.label && <span className="ml-1 text-xs text-muted">{v.name}</span>}
                      </span>
                      <span className="shrink-0 text-[11px] text-muted">
                        {elsewhere ? 'used in another role' : !eligible ? `${LEVEL_LABEL[v.level]} — not allowed` : LEVEL_LABEL[v.level]}
                      </span>
                    </button>
                  </li>
                )
              })}
              {list.length === 0 && <li className="px-3 py-2 text-[13px] text-muted">No variables match.</li>}
            </ul>
          </Popover>
        )}
      </div>
    </div>
  )
}
