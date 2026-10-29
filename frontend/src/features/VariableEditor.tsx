import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Tags } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge, useToast } from '@/components/ui/feedback'
import { Field, Input, Select } from '@/components/ui/form'
import { Dialog, Tooltip } from '@/components/ui/overlay'
import { api, errorMessage } from '@/lib/api'
import { LEVEL_HELP, LEVEL_LABEL, LEVELS } from '@/lib/format'
import { keys } from '@/lib/queries'
import type { Dataset, Level, Variable } from '@/lib/types'
import { cn } from '@/lib/utils'

type Patch = Partial<{ label: string | null; level: Level; missing_codes: (string | number)[]; unit: string | null; category_labels: Record<string, string>; category_order: (string | number)[] }>

export function VariableEditor({ dataset }: { dataset: Dataset }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<Variable | null>(null)
  const save = useMutation({
    mutationFn: (body: Record<string, Patch>) => api.patch(`/datasets/${dataset.id}/variables`, { variables: body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.dataset(dataset.id) })
      qc.invalidateQueries({ queryKey: ['recs'] })
      qc.invalidateQueries({ queryKey: ['configs'] })
    },
    onError: (e) => toast('danger', errorMessage(e)),
  })
  const visible = useMemo(
    () => dataset.variables.filter((v) => !query || v.name.toLowerCase().includes(query.toLowerCase()) || (v.label ?? '').toLowerCase().includes(query.toLowerCase())),
    [dataset.variables, query],
  )
  const patch = (v: Variable, p: Patch) => save.mutate({ [v.name]: p })
  const versionIsLatest = true

  return (
    <div className="overflow-hidden rounded-lg border border-line bg-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <Input placeholder="Find a variable" value={query} onChange={(e) => setQuery(e.target.value)} className="w-full sm:w-64" aria-label="Find a variable" />
        <p className="text-xs text-muted">Changes are saved immediately and apply to the latest version. The stored data is never modified.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-[13px]">
          <thead className="border-b border-line bg-surface-2 text-left text-xs text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">Variable</th>
              <th className="px-3 py-2 font-medium">Label</th>
              <th className="w-40 px-3 py-2 font-medium">Measurement level</th>
              <th className="w-36 px-3 py-2 font-medium">Missing-value codes</th>
              <th className="w-24 px-3 py-2 font-medium">Unit</th>
              <th className="px-3 py-2 text-right font-medium">Missing</th>
              <th className="px-3 py-2 text-right font-medium">Distinct</th>
              <th className="px-3 py-2 font-medium">Categories</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {visible.map((v) => (
              <tr key={v.name} className="hover:bg-surface-2">
                <td className="px-3 py-2 align-top">
                  <div className="font-medium">{v.name}</div>
                  <div className="text-xs text-muted">{v.data_type}{v.scale_group && <> · scale {v.scale_group}</>}</div>
                </td>
                <td className="px-3 py-2 align-top">
                  <Input
                    defaultValue={v.label ?? ''}
                    placeholder="Add a readable label"
                    aria-label={`Label for ${v.name}`}
                    className="h-7"
                    onBlur={(e) => e.target.value !== (v.label ?? '') && patch(v, { label: e.target.value || null })}
                  />
                </td>
                <td className="px-3 py-2 align-top">
                  <Select
                    value={v.level}
                    onChange={(e) => patch(v, { level: e.target.value as Level })}
                    aria-label={`Measurement level of ${v.name}`}
                    disabled={!versionIsLatest}
                  >
                    {LEVELS.map((l) => (
                      <option key={l} value={l}>
                        {LEVEL_LABEL[l]}
                      </option>
                    ))}
                  </Select>
                  {v.inferred_level && v.inferred_level !== v.level && <div className="mt-1 text-xs text-muted">Detected: {LEVEL_LABEL[v.inferred_level]}</div>}
                  <Tooltip content={v.inference_note ?? LEVEL_HELP[v.level]}>
                    <span className="mt-1 block cursor-help text-xs text-muted underline decoration-dotted underline-offset-2">Why?</span>
                  </Tooltip>
                </td>
                <td className="px-3 py-2 align-top">
                  <Input
                    defaultValue={v.missing_codes.join(', ')}
                    placeholder="e.g. 99, -9"
                    aria-label={`Missing-value codes for ${v.name}`}
                    className="h-7"
                    onBlur={(e) => {
                      const codes = e.target.value.split(',').map((s) => s.trim()).filter(Boolean).map((s) => (Number.isNaN(Number(s)) ? s : Number(s)))
                      if (JSON.stringify(codes) !== JSON.stringify(v.missing_codes)) patch(v, { missing_codes: codes })
                    }}
                  />
                </td>
                <td className="px-3 py-2 align-top">
                  <Input defaultValue={v.unit ?? ''} aria-label={`Unit for ${v.name}`} className="h-7" onBlur={(e) => e.target.value !== (v.unit ?? '') && patch(v, { unit: e.target.value || null })} />
                </td>
                <td className="num px-3 py-2 text-right align-top">
                  {v.profile.missing ?? '—'}
                  {!!v.profile.missing_pct && v.profile.missing_pct > 0 && <div className="text-xs text-muted">{v.profile.missing_pct.toFixed(1)}%</div>}
                </td>
                <td className="num px-3 py-2 text-right align-top">{v.profile.unique ?? '—'}</td>
                <td className="px-3 py-2 align-top">
                  {['nominal', 'ordinal', 'binary'].includes(v.level) ? (
                    <Button size="sm" variant="ghost" onClick={() => setEditing(v)}>
                      <Tags /> {Object.keys(v.category_labels).length ? 'Edit labels' : 'Labels & order'}
                    </Button>
                  ) : v.profile.mean !== undefined && v.profile.mean !== null ? (
                    <span className="num text-xs text-muted">M = {Number(v.profile.mean).toFixed(2)}, SD = {Number(v.profile.sd ?? 0).toFixed(2)}</span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && <CategoryDialog dataset={dataset} variable={editing} onClose={() => setEditing(null)} onSave={(p) => { patch(editing, p); setEditing(null) }} />}
    </div>
  )
}

function CategoryDialog({ dataset, variable, onClose, onSave }: { dataset: Dataset; variable: Variable; onClose: () => void; onSave: (p: Patch) => void }) {
  const values = useQuery({
    queryKey: ['values', dataset.id, variable.name],
    queryFn: () => api.get<{ items: { value: string | number | null; count: number }[] }>(`/datasets/${dataset.id}/variables/${encodeURIComponent(variable.name)}/values`),
  })
  const observed = (values.data?.items ?? []).filter((x) => x.value !== null).map((x) => ({ key: String(x.value), count: x.count }))
  const [order, setOrder] = useState<string[] | null>(null)
  const [labels, setLabels] = useState<Record<string, string>>(variable.category_labels)
  const current =
    order ??
    (() => {
      const declared = variable.category_order.map(String).filter((k) => observed.some((o) => o.key === k))
      const rest = observed.map((o) => o.key).filter((k) => !declared.includes(k)).sort((a, b) => (Number(a) - Number(b)) || a.localeCompare(b))
      return [...declared, ...rest]
    })()
  const counts = Object.fromEntries(observed.map((o) => [o.key, o.count]))
  const move = (i: number, d: number) => {
    const next = [...current]
    const j = i + d
    if (j < 0 || j >= next.length) return
    ;[next[i], next[j]] = [next[j], next[i]]
    setOrder(next)
  }
  const ordinal = variable.level === 'ordinal'
  return (
    <Dialog
      open
      onOpenChange={(v) => !v && onClose()}
      title={`Categories of ${variable.name}`}
      description={ordinal ? 'Set readable labels and the order from lowest to highest.' : 'Give number codes readable labels (e.g. 1 = Male).'}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            onClick={() =>
              onSave({
                category_labels: labels,
                category_order: current.map((k) => (variable.data_type === 'string' || Number.isNaN(Number(k)) ? k : Number(k))),
              })
            }
          >
            Save
          </Button>
        </>
      }
    >
      {values.isLoading && <p className="text-[13px] text-muted">Loading categories…</p>}
      {observed.length > 0 && (
        <ul className="divide-y divide-line rounded-md border border-line">
          {current.map((k, i) => (
            <li key={k} className="flex items-center gap-2 px-3 py-2">
              {ordinal && (
                <div className="flex flex-col">
                  <button className="rounded p-0.5 text-muted hover:text-fg disabled:opacity-30" onClick={() => move(i, -1)} disabled={i === 0} aria-label={`Move ${k} up`}>
                    <ArrowUp className="size-3.5" />
                  </button>
                  <button className="rounded p-0.5 text-muted hover:text-fg disabled:opacity-30" onClick={() => move(i, 1)} disabled={i === current.length - 1} aria-label={`Move ${k} down`}>
                    <ArrowDown className="size-3.5" />
                  </button>
                </div>
              )}
              <code className={cn('num w-24 shrink-0 truncate font-mono text-xs')}>{k}</code>
              <Field label={<span className="sr-only">Label for {k}</span>} className="flex-1">
                {(id) => <Input id={id} value={labels[k] ?? ''} placeholder="Label (optional)" onChange={(e) => setLabels({ ...labels, [k]: e.target.value })} className="h-7" />}
              </Field>
              <Badge className="num">{counts[k]?.toLocaleString()}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  )
}
