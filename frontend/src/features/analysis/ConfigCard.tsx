import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ChevronDown, Code2, Copy, Loader2, Play, Trash2, XCircle } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/feedback'
import { Checkbox, CheckRow, Field, Input, Select, Switch } from '@/components/ui/form'
import { Dialog, Tooltip } from '@/components/ui/overlay'
import { api } from '@/lib/api'
import type { AnalysisSpec, Assignment, Configuration, OptionSpec, Variable } from '@/lib/types'
import { asArray, cn } from '@/lib/utils'
import { RoleSlot } from './RoleSlot'

export interface ConfigCardProps {
  config: Configuration
  spec: AnalysisSpec | undefined
  variables: Variable[]
  datasetId: number
  selected: boolean
  expanded: boolean
  onSelect: (v: boolean) => void
  onExpand: (v: boolean) => void
  onSave: (patch: { variables?: Assignment; options?: Record<string, unknown>; name?: string }) => void
  onRun: () => void
  onDuplicate: () => void
  onRemove: () => void
  showTechnical: boolean
}

export function ConfigCard(p: ConfigCardProps) {
  const { config, spec } = p
  const [vars, setVars] = useState<Assignment>(config.variables)
  const [opts, setOpts] = useState<Record<string, unknown>>(config.options)
  const [advanced, setAdvanced] = useState(false)
  const [codeOpen, setCodeOpen] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingSave = useRef<{ variables?: Assignment; options?: Record<string, unknown> }>({})
  const { onSave } = p

  useEffect(() => {
    setVars(config.variables)
    setOpts(config.options)
  }, [config.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const queueSave = (patch: { variables?: Assignment; options?: Record<string, unknown> }) => {
    pendingSave.current = { ...pendingSave.current, ...patch }
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      onSave(pendingSave.current)
      pendingSave.current = {}
    }, 400)
  }
  useEffect(() => () => {
    if (timer.current) {
      clearTimeout(timer.current)
      if (Object.keys(pendingSave.current).length) onSave(pendingSave.current)
    }
  }, [onSave])

  const setRole = (key: string, value: string[], single: boolean) => {
    const next = { ...vars, [key]: single ? (value[0] ?? '') : value }
    setVars(next)
    queueSave({ variables: next })
  }
  const setOpt = (key: string, value: unknown) => {
    const next = { ...opts, [key]: value }
    setOpts(next)
    queueSave({ options: next })
  }

  const run = config.last_run
  const status = run?.status
  const assignedNames = (role: string) => asArray(vars[role] as string | string[] | undefined)
  const summary = (spec?.roles ?? [])
    .map((r) => assignedNames(r.key))
    .flat()
    .slice(0, 4)
    .join(', ')
  const problems = config.problems

  return (
    <div className={cn('rounded-md border bg-surface', p.expanded ? 'border-line-strong' : 'border-line')}>
      <div className="flex items-start gap-2.5 px-3 py-2.5">
        <Checkbox checked={p.selected} onCheckedChange={p.onSelect} className="mt-0.5" aria-label={`Select ${spec?.name ?? config.analysis_type} to run`} />
        <button type="button" className="min-w-0 flex-1 text-left" onClick={() => p.onExpand(!p.expanded)} aria-expanded={p.expanded}>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span className="text-[13px] font-medium">{p.showTechnical ? spec?.name : spec?.plain_name}</span>
            {config.source === 'recommended' && <Badge tone="accent">Recommended</Badge>}
            {config.outdated && (
              <Tooltip content={`Configured on version ${config.dataset_version_number}; runs will use the latest version.`}>
                <span><Badge tone="warning">Older data version</Badge></span>
              </Tooltip>
            )}
          </div>
          <div className="truncate text-xs text-muted">
            {p.showTechnical ? spec?.plain_name : spec?.name}
            {summary && <> · {summary}</>}
          </div>
        </button>
        <StatusIcon status={status} problems={problems.length} />
        <ChevronDown className={cn('mt-0.5 size-4 shrink-0 text-muted transition-transform', p.expanded && 'rotate-180')} aria-hidden />
      </div>

      {p.expanded && spec && (
        <div className="space-y-4 border-t border-line px-3 py-3">
          {spec.roles.map((role) => {
            const others = new Set(spec.roles.filter((r) => r.key !== role.key).flatMap((r) => assignedNames(r.key)))
            return (
              <RoleSlot
                key={role.key}
                role={role}
                value={assignedNames(role.key)}
                variables={p.variables}
                usedElsewhere={others}
                onChange={(v) => setRole(role.key, v, role.max === 1)}
              />
            )
          })}

          {spec.options.length > 0 && (
            <div className="space-y-3">
              {spec.options.filter((o) => !o.advanced).map((o) => (
                <OptionInput key={o.key} option={o} value={opts[o.key] ?? o.default} onChange={(v) => setOpt(o.key, v)} vars={vars} datasetId={p.datasetId} variables={p.variables} />
              ))}
              {spec.options.some((o) => o.advanced) && (
                <>
                  <button type="button" onClick={() => setAdvanced(!advanced)} className="flex items-center gap-1 text-xs font-medium text-accent hover:underline" aria-expanded={advanced}>
                    <ChevronDown className={cn('size-3.5 transition-transform', advanced && 'rotate-180')} /> {advanced ? 'Hide' : 'Show'} advanced options
                  </button>
                  {advanced && (
                    <div className="space-y-3 border-l-2 border-line pl-3">
                      {spec.options.filter((o) => o.advanced).map((o) => (
                        <OptionInput key={o.key} option={o} value={opts[o.key] ?? o.default} onChange={(v) => setOpt(o.key, v)} vars={vars} datasetId={p.datasetId} variables={p.variables} />
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {problems.length > 0 && (
            <ul className="space-y-1 rounded-md border border-warning/35 bg-warning-soft px-3 py-2 text-xs text-fg-2">
              {problems.map((x) => (
                <li key={x} className="flex gap-1.5"><AlertTriangle className="mt-px size-3.5 shrink-0 text-warning" />{x}</li>
              ))}
            </ul>
          )}
          {status === 'failed' && run?.error_message && (
            <div className="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-fg-2">
              <span className="font-medium text-danger">Could not run: </span>
              {run.error_message}
              {run.summary?.suggestion && <span className="mt-1 block">Suggestion: {run.summary.suggestion}</span>}
            </div>
          )}

          <details className="text-xs text-muted">
            <summary className="cursor-pointer select-none hover:text-fg">About this analysis</summary>
            <div className="mt-2 space-y-1.5">
              <p>{spec.description}</p>
              {spec.when_to_use && <p><span className="font-medium text-fg-2">When to use: </span>{spec.when_to_use}</p>}
              {spec.assumptions.length > 0 && (
                <div>
                  <span className="font-medium text-fg-2">Assumptions: </span>
                  {spec.assumptions.join(' ')}
                </div>
              )}
              <p><span className="font-medium text-fg-2">Missing data: </span>{spec.missing_data}</p>
            </div>
          </details>

          <div className="flex flex-wrap items-center gap-1.5 border-t border-line pt-3">
            <Button size="sm" variant="primary" onClick={p.onRun} disabled={problems.length > 0 || status === 'running' || status === 'queued'}>
              <Play /> Run
            </Button>
            <Button size="sm" variant="ghost" onClick={p.onDuplicate}><Copy /> Duplicate</Button>
            <Button size="sm" variant="ghost" onClick={() => setCodeOpen(true)}><Code2 /> Code</Button>
            <div className="flex-1" />
            <Button size="sm" variant="ghost" className="text-danger" onClick={p.onRemove}><Trash2 /> Remove</Button>
          </div>
        </div>
      )}
      {codeOpen && <CodeDialog configId={config.id} onClose={() => setCodeOpen(false)} />}
    </div>
  )
}

function StatusIcon({ status, problems }: { status?: string; problems: number }) {
  if (status === 'running' || status === 'queued')
    return <span className="flex items-center gap-1 text-xs text-muted"><Loader2 className="size-4 animate-spin" /> {status === 'queued' ? 'Queued' : 'Running'}</span>
  if (problems > 0) return <Tooltip content="Variables need attention"><span className="text-xs text-warning">Setup needed</span></Tooltip>
  if (status === 'completed') return <Tooltip content="Last run completed"><CheckCircle2 className="size-4 text-success" aria-label="Completed" /></Tooltip>
  if (status === 'failed') return <Tooltip content="Last run failed"><XCircle className="size-4 text-danger" aria-label="Failed" /></Tooltip>
  return <span className="text-xs text-muted">Ready</span>
}

function OptionInput({
  option,
  value,
  onChange,
  vars,
  datasetId,
  variables,
}: {
  option: OptionSpec
  value: unknown
  onChange: (v: unknown) => void
  vars: Assignment
  datasetId: number
  variables: Variable[]
}) {
  const dependsOn = option.depends_on ? asArray(vars[option.depends_on] as string | string[]) : []
  const levelSource = option.type === 'level' ? dependsOn[0] : undefined
  const levels = useQuery({
    queryKey: ['values', datasetId, levelSource],
    queryFn: () => api.get<{ items: { value: string | number | null; count: number }[] }>(`/datasets/${datasetId}/variables/${encodeURIComponent(levelSource!)}/values`),
    enabled: !!levelSource,
  })
  const labelFor = useMemo(() => {
    const v = variables.find((x) => x.name === levelSource)
    return (k: string) => v?.category_labels[k] ?? k
  }, [variables, levelSource])

  if (option.type === 'bool')
    return (
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={`opt-${option.key}`} className="text-[13px] text-fg-2">
          {option.label}
          {option.help && <span className="block text-xs text-muted">{option.help}</span>}
        </label>
        <Switch id={`opt-${option.key}`} checked={Boolean(value)} onCheckedChange={onChange} />
      </div>
    )
  if (option.type === 'select')
    return (
      <Field label={option.label} help={option.help}>
        {(id) => (
          <Select id={id} value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}>
            {option.choices?.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </Select>
        )}
      </Field>
    )
  if (option.type === 'number')
    return (
      <Field label={option.label} help={option.help}>
        {(id) => (
          <Input
            id={id}
            type="number"
            step="any"
            min={option.min ?? undefined}
            max={option.max ?? undefined}
            value={value === null || value === undefined ? '' : String(value)}
            onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
          />
        )}
      </Field>
    )
  if (option.type === 'level')
    return (
      <Field label={option.label} help={option.help || (levelSource ? undefined : 'Choose the variable first.')}>
        {(id) => (
          <Select id={id} value={String(value ?? '')} onChange={(e) => onChange(e.target.value || null)} disabled={!levelSource}>
            <option value="">Automatic</option>
            {(levels.data?.items ?? []).filter((x) => x.value !== null).map((x) => {
              const k = String(typeof x.value === 'number' && Number.isInteger(x.value) ? x.value : x.value)
              const lbl = labelFor(k)
              return <option key={k} value={lbl}>{lbl} ({x.count})</option>
            })}
          </Select>
        )}
      </Field>
    )
  if (option.type === 'multiselect') {
    const choices = option.depends_on ? dependsOn.map((d) => ({ value: d, label: d })) : (option.choices ?? [])
    const current = new Set(Array.isArray(value) ? (value as string[]) : [])
    return (
      <fieldset>
        <legend className="text-[13px] font-medium text-fg-2">{option.label}</legend>
        {option.help && <p className="text-xs text-muted">{option.help}</p>}
        {choices.length === 0 ? (
          <p className="mt-1 text-xs text-muted">Choose variables first.</p>
        ) : (
          <div className={cn('mt-1 grid gap-x-3', choices.length > 6 && 'sm:grid-cols-2')}>
            {choices.map((c) => (
              <CheckRow
                key={c.value}
                checked={current.has(c.value)}
                label={c.label}
                onChange={(on) => {
                  const next = new Set(current)
                  if (on) next.add(c.value)
                  else next.delete(c.value)
                  onChange(choices.map((x) => x.value).filter((x) => next.has(x)))
                }}
              />
            ))}
          </div>
        )}
      </fieldset>
    )
  }
  return (
    <Field label={option.label} help={option.help}>
      {(id) => <Input id={id} defaultValue={String(value ?? '')} onBlur={(e) => onChange(e.target.value)} />}
    </Field>
  )
}

export function CodeDialog({ configId, onClose }: { configId: number; onClose: () => void }) {
  const code = useQuery({ queryKey: ['code', configId], queryFn: () => api.get<{ code: string | null }>(`/analyses/configurations/${configId}/code`) })
  return (
    <Dialog
      open
      onOpenChange={(v) => !v && onClose()}
      size="xl"
      title="Reproducible Python code"
      description="Uses the same libraries, functions and options as the analysis engine."
      footer={
        <Button onClick={() => code.data?.code && navigator.clipboard.writeText(code.data.code)} disabled={!code.data?.code}>
          <Copy /> Copy code
        </Button>
      }
    >
      <pre className="scroll-thin max-h-[60dvh] overflow-auto rounded-md bg-surface-3 p-3 font-mono text-xs leading-relaxed">
        {code.isLoading ? 'Loading…' : (code.data?.code ?? 'Code is not available for this analysis.')}
      </pre>
    </Dialog>
  )
}
