import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, Check, Download, FileSpreadsheet, Plus, Sparkles, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DatasetPicker } from '@/components/DatasetPicker'
import { PageBody, PageHeader } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Callout, EmptyState, ErrorState, Panel, Skeleton, useToast } from '@/components/ui/feedback'
import { Checkbox, Field, Input, Select } from '@/components/ui/form'
import { useActiveDataset, useProjectId } from '@/lib/active'
import { api, download, errorMessage } from '@/lib/api'
import { keys, useDataset, useProject } from '@/lib/queries'
import type { CleaningOp, CleaningPreview, CleaningStep, CleaningSuggestion, CleaningSummary, Dataset } from '@/lib/types'
import { cn } from '@/lib/utils'

const OPS: { op: CleaningOp; label: string; help: string }[] = [
  { op: 'recode', label: 'Recode or merge values', help: 'Change values, e.g. “M” → “Male”, or a value → missing.' },
  { op: 'missing_codes', label: 'Treat codes as missing', help: 'Values such as 99, N/A or “-” that mean no answer.' },
  { op: 'drop_missing', label: 'Remove rows with missing values', help: 'Drop incomplete responses.' },
  { op: 'fill_missing', label: 'Fill missing values', help: 'Mean, median, most common value or a fixed value.' },
  { op: 'drop_duplicates', label: 'Remove duplicate rows', help: 'Keeps the first copy.' },
  { op: 'to_number', label: 'Convert text to numbers', help: 'Strips commas, units and symbols.' },
  { op: 'trim_text', label: 'Remove extra spaces', help: 'In all text columns.' },
  { op: 'change_case', label: 'Change letter case', help: 'Title, lower, upper or sentence case.' },
  { op: 'out_of_range', label: 'Valid range check', help: 'Values outside the range become missing or are removed.' },
  { op: 'outliers', label: 'Handle outliers', help: 'IQR or z-score rule. Report this in your methodology.' },
  { op: 'rename', label: 'Rename a column', help: '' },
  { op: 'drop_columns', label: 'Remove columns', help: 'E.g. timestamps or e-mail addresses.' },
]

function describe(s: CleaningStep): string {
  const col = s.column ?? s.columns?.join(', ') ?? ''
  switch (s.op) {
    case 'recode': return `${col}: recode ${Object.entries(s.mapping ?? {}).map(([a, b]) => `“${a}” → ${b === '' ? 'missing' : `“${b}”`}`).join(', ')}`
    case 'missing_codes': return `${col}: treat ${(s.codes ?? []).map((c) => `“${c}”`).join(', ')} as missing`
    case 'drop_missing': return s.columns?.length ? `Remove rows missing ${s.how === 'all' ? 'all of' : 'any of'} ${col}` : 'Remove empty rows'
    case 'fill_missing': return `${col}: fill missing with ${s.method === 'value' ? `“${s.value}”` : s.method === 'mode' ? 'most common value' : `the ${s.method}`}`
    case 'drop_duplicates': return s.columns?.length ? `Remove rows with the same ${col}` : 'Remove duplicate rows'
    case 'to_number': return `${col}: convert to numbers`
    case 'trim_text': return s.columns?.length ? `Remove extra spaces in ${col}` : 'Remove extra spaces in all text columns'
    case 'change_case': return `${col}: ${s.case} case`
    case 'out_of_range': return `${col}: valid range ${s.min ?? '−∞'}–${s.max ?? '∞'} (${s.action === 'drop' ? 'remove row' : 'set missing'})`
    case 'outliers': return `${col}: outliers by ${s.method === 'z' ? 'z-score' : 'IQR'} (${s.action === 'drop' ? 'remove row' : 'set missing'})`
    case 'rename': return `Rename ${col} to ${s.to}`
    case 'drop_columns': return `Remove ${col}`
  }
}

/* ------------------------------------------------------------------ add-a-step form */

function StepForm({ columns, datasetId, onAdd }: { columns: string[]; datasetId: number; onAdd: (s: CleaningStep) => void }) {
  const [op, setOp] = useState<CleaningOp>('recode')
  const [column, setColumn] = useState(columns[0] ?? '')
  const [picked, setPicked] = useState<string[]>([])
  const [text, setText] = useState('')
  const [pairs, setPairs] = useState<Record<string, string>>({})
  const [method, setMethod] = useState('median')
  const [how, setHow] = useState<'any' | 'all'>('any')
  const [action, setAction] = useState<'missing' | 'drop'>('missing')
  const [min, setMin] = useState('')
  const [max, setMax] = useState('')
  const [kase, setKase] = useState<'title' | 'lower' | 'upper' | 'sentence'>('title')
  const values = useQuery({
    queryKey: ['values', datasetId, column],
    queryFn: () => api.get<{ items: { value: unknown; count: number }[] }>(`/datasets/${datasetId}/variables/${encodeURIComponent(column)}/values`),
    enabled: op === 'recode' && !!column,
    retry: false,
  })
  useEffect(() => setPairs({}), [column])
  const multi = op === 'drop_columns' || op === 'drop_missing' || op === 'drop_duplicates'
  const meta = OPS.find((o) => o.op === op)!

  const build = (): CleaningStep | null => {
    switch (op) {
      case 'recode': {
        const mapping = Object.fromEntries(Object.entries(pairs).filter(([, v]) => v !== undefined))
        return Object.keys(mapping).length ? { op, column, mapping } : null
      }
      case 'missing_codes': {
        const codes = text.split(',').map((x) => x.trim()).filter(Boolean)
        return codes.length ? { op, columns: [column], codes } : null
      }
      case 'drop_missing': return { op, columns: picked.length ? picked : undefined, how: picked.length ? how : 'all' }
      case 'fill_missing': return method === 'value' && !text ? null : { op, column, method, value: method === 'value' ? text : undefined }
      case 'drop_duplicates': return { op, columns: picked.length ? picked : undefined }
      case 'to_number': return { op, columns: [column] }
      case 'trim_text': return { op }
      case 'change_case': return { op, column, case: kase }
      case 'out_of_range': return min === '' && max === '' ? null : { op, column, min: min === '' ? null : Number(min), max: max === '' ? null : Number(max), action }
      case 'outliers': return { op, column, method, action }
      case 'rename': return text.trim() ? { op, column, to: text.trim() } : null
      case 'drop_columns': return picked.length ? { op, columns: picked } : null
    }
  }
  const step = build()
  const reset = () => {
    setText('')
    setPairs({})
    setPicked([])
  }

  return (
    <div className="space-y-3">
      <Field label="Step" help={meta.help}>
        {(id) => (
          <Select id={id} value={op} onChange={(e) => { setOp(e.target.value as CleaningOp); setMethod(e.target.value === 'outliers' ? 'iqr' : 'median'); reset() }}>
            {OPS.map((o) => <option key={o.op} value={o.op}>{o.label}</option>)}
          </Select>
        )}
      </Field>
      {multi ? (
        <fieldset>
          <legend className="mb-1.5 text-[13px] font-medium">{op === 'drop_columns' ? 'Columns to remove' : 'Columns (none = all columns)'}</legend>
          <div className="scroll-thin grid max-h-40 grid-cols-2 gap-x-3 gap-y-1 overflow-auto rounded-md border border-line p-2">
            {columns.map((c) => (
              <label key={c} className="flex min-w-0 items-center gap-2 text-[13px]">
                <Checkbox checked={picked.includes(c)} onCheckedChange={(v) => setPicked(v ? [...picked, c] : picked.filter((x) => x !== c))} aria-label={c} />
                <span className="truncate">{c}</span>
              </label>
            ))}
          </div>
        </fieldset>
      ) : op !== 'trim_text' && (
        <Field label="Column">
          {(id) => <Select id={id} value={column} onChange={(e) => setColumn(e.target.value)}>{columns.map((c) => <option key={c}>{c}</option>)}</Select>}
        </Field>
      )}

      {op === 'recode' && (
        <div>
          <p className="mb-1.5 text-[13px] font-medium">Values in {column}</p>
          {values.isPending ? <Skeleton className="h-20" /> : values.data?.items.length ? (
            <div className="scroll-thin max-h-56 space-y-1 overflow-auto rounded-md border border-line p-2">
              {values.data.items.filter((v) => v.value !== null).slice(0, 60).map((v) => {
                const key = String(v.value)
                return (
                  <div key={key} className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 text-[13px]">
                    <span className="truncate" title={key}>“{key}” <span className="text-muted">· {v.count}</span></span>
                    <ArrowRight className="size-3.5 text-muted" />
                    <Input aria-label={`New value for ${key}`} className="h-7" placeholder="keep" value={pairs[key] ?? ''}
                      onChange={(e) => setPairs((p) => { const n = { ...p }; if (e.target.value === '') delete n[key]; else n[key] = e.target.value; return n })} />
                  </div>
                )
              })}
            </div>
          ) : <p className="text-[13px] text-muted">Values of renamed columns appear after saving. Type the old and new value instead.</p>}
          <p className="mt-1 text-xs text-muted">Leave a box empty to keep the value. Type a single “-” and use “Treat codes as missing” to blank values.</p>
        </div>
      )}
      {op === 'missing_codes' && <Field label="Codes, separated by commas" help="e.g. 99, N/A, -">{(id) => <Input id={id} value={text} onChange={(e) => setText(e.target.value)} />}</Field>}
      {op === 'drop_missing' && picked.length > 1 && (
        <Field label="Remove a row when">{(id) => <Select id={id} value={how} onChange={(e) => setHow(e.target.value as 'any' | 'all')}><option value="any">any of these is missing</option><option value="all">all of these are missing</option></Select>}</Field>
      )}
      {op === 'fill_missing' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Fill with">{(id) => <Select id={id} value={method} onChange={(e) => setMethod(e.target.value)}><option value="median">Median</option><option value="mean">Mean</option><option value="mode">Most common value</option><option value="value">A fixed value</option></Select>}</Field>
          {method === 'value' && <Field label="Value">{(id) => <Input id={id} value={text} onChange={(e) => setText(e.target.value)} />}</Field>}
        </div>
      )}
      {op === 'change_case' && (
        <Field label="Case">{(id) => <Select id={id} value={kase} onChange={(e) => setKase(e.target.value as typeof kase)}><option value="title">Title Case</option><option value="sentence">Sentence case</option><option value="lower">lower case</option><option value="upper">UPPER CASE</option></Select>}</Field>
      )}
      {op === 'out_of_range' && (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Lowest valid">{(id) => <Input id={id} inputMode="decimal" value={min} onChange={(e) => setMin(e.target.value)} placeholder="e.g. 1" />}</Field>
          <Field label="Highest valid">{(id) => <Input id={id} inputMode="decimal" value={max} onChange={(e) => setMax(e.target.value)} placeholder="e.g. 5" />}</Field>
        </div>
      )}
      {op === 'outliers' && (
        <>
          <Field label="Rule">{(id) => <Select id={id} value={method} onChange={(e) => setMethod(e.target.value)}><option value="iqr">Beyond 1.5 × IQR (box-plot rule)</option><option value="z">More than 3 SD from the mean</option></Select>}</Field>
          <Callout tone="warning">Removing outliers changes your results. Only do it for a reason you can defend, and report it in your methodology.</Callout>
        </>
      )}
      {(op === 'out_of_range' || op === 'outliers') && (
        <Field label="Then">{(id) => <Select id={id} value={action} onChange={(e) => setAction(e.target.value as 'missing' | 'drop')}><option value="missing">Set the value to missing</option><option value="drop">Remove the whole row</option></Select>}</Field>
      )}
      {op === 'rename' && <Field label="New name">{(id) => <Input id={id} value={text} onChange={(e) => setText(e.target.value)} />}</Field>}

      <Button variant="secondary" disabled={!step} onClick={() => { if (step) { onAdd(step); reset() } }}>
        <Plus /> Add step
      </Button>
    </div>
  )
}

/* ------------------------------------------------------------------ preview */

function Delta({ label, before, after, good = 'down' }: { label: string; before: number; after: number; good?: 'down' | 'up' }) {
  const changed = before !== after
  const better = good === 'down' ? after < before : after > before
  return (
    <div className="min-w-0 rounded-md border border-line bg-surface px-3 py-2">
      <p className="truncate text-xs text-muted">{label}</p>
      <p className="mt-0.5 text-[15px] tabular-nums">
        {changed ? <><span className="text-muted line-through decoration-1">{before.toLocaleString()}</span> <span className={cn('font-semibold', better ? 'text-success' : 'text-fg')}>{after.toLocaleString()}</span></> : <span className="font-semibold">{after.toLocaleString()}</span>}
      </p>
    </div>
  )
}

function SummaryStrip({ before, after }: { before: CleaningSummary; after: CleaningSummary }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Delta label="Rows" before={before.rows} after={after.rows} good="up" />
      <Delta label="Missing cells" before={before.missing_cells} after={after.missing_cells} />
      <Delta label="Duplicate rows" before={before.duplicate_rows} after={after.duplicate_rows} />
      <Delta label="Columns" before={before.columns} after={after.columns} good="up" />
    </div>
  )
}

function PreviewTable({ preview }: { preview: CleaningPreview }) {
  const changed = useMemo(() => new Set(preview.changed.map(([r, c]) => `${r}:${c}`)), [preview.changed])
  return (
    <div className="scroll-thin max-h-[460px] overflow-auto rounded-md border border-line [contain:paint]">
      <table className="stat-table">
        <thead className="sticky top-0 z-[1] bg-surface">
          <tr>{preview.columns.map((c) => <th key={c} className="whitespace-nowrap">{c}</th>)}</tr>
        </thead>
        <tbody>
          {preview.rows.map((row, i) => (
            <tr key={i}>
              {row.map((v, j) => {
                const hit = changed.has(`${i}:${preview.columns[j]}`)
                return (
                  <td key={j} className={cn('whitespace-nowrap', typeof v === 'number' && 'num text-right', hit && 'bg-accent-soft font-medium', v === null && 'text-muted')}
                    title={hit ? 'Changed by cleaning' : undefined}>
                    {v === null ? '—' : String(v)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ------------------------------------------------------------------ page */

function Exports({ dataset }: { dataset: Dataset }) {
  const first = [...dataset.versions].sort((a, b) => a.number - b.number)[0]
  const base = `/datasets/${dataset.id}/download`
  const cleaned = dataset.versions.length > 1
  return (
    <div className="flex flex-wrap gap-2">
      <Button variant={cleaned ? 'primary' : 'secondary'} onClick={() => download(`${base}?format=xlsx`, { fallbackName: `${dataset.name}.xlsx` })}>
        <FileSpreadsheet /> {cleaned ? 'Cleaned data (Excel + cleaning log)' : 'Data (Excel)'}
      </Button>
      <Button variant="secondary" onClick={() => download(`${base}?format=csv`, { fallbackName: `${dataset.name}.csv` })}>
        <Download /> CSV
      </Button>
      {cleaned && first && (
        <Button variant="ghost" onClick={() => download(`${base}?format=xlsx&version_id=${first.id}`, { fallbackName: `${dataset.name}_raw.xlsx` })}>
          <Download /> Raw data (version {first.number})
        </Button>
      )}
    </div>
  )
}

export default function CleanPage() {
  const pid = useProjectId()
  const project = useProject(pid)
  const { datasetId, setDatasetId, datasets, query } = useActiveDataset(pid)
  const dataset = useDataset(datasetId)
  const qc = useQueryClient()
  const toast = useToast()
  const [accepted, setAccepted] = useState<Record<string, boolean>>({})
  const [manual, setManual] = useState<CleaningStep[]>([])
  const [saved, setSaved] = useState<{ version: number; log: string[] } | null>(null)

  const suggestions = useQuery({
    queryKey: ['cleaning', datasetId, dataset.data?.version.id],
    queryFn: () => api.get<{ suggestions: CleaningSuggestion[]; summary: CleaningSummary; version_number: number }>(`/datasets/${datasetId}/cleaning/suggestions`),
    enabled: !!datasetId && !!dataset.data,
  })
  useEffect(() => {
    setAccepted({})
    setManual([])
  }, [datasetId, dataset.data?.version.id])

  const chosen = (suggestions.data?.suggestions ?? []).filter((s) => accepted[s.id] ?? s.default)
  const steps = useMemo(() => [...chosen.map((s) => s.step), ...manual], [chosen, manual])
  const stepsKey = JSON.stringify(steps)
  const [debounced, setDebounced] = useState(stepsKey)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(stepsKey), 350)
    return () => clearTimeout(t)
  }, [stepsKey])
  const preview = useQuery({
    queryKey: ['cleaning-preview', datasetId, dataset.data?.version.id, debounced],
    queryFn: () => api.post<CleaningPreview>(`/datasets/${datasetId}/cleaning/preview`, { steps: JSON.parse(debounced) }),
    enabled: !!datasetId && !!suggestions.data,
    placeholderData: (prev) => prev,
    retry: false,
  })
  const apply = useMutation({
    mutationFn: () => api.post<{ dataset: Dataset; log: { message: string }[] }>(`/datasets/${datasetId}/cleaning/apply`, { steps }),
    onSuccess: (r) => {
      qc.setQueryData(keys.dataset(r.dataset.id), r.dataset)
      qc.invalidateQueries({ queryKey: keys.datasets(pid) })
      setSaved({ version: r.dataset.version.number, log: r.log.map((x) => x.message) })
      toast('success', `Saved the cleaned data as version ${r.dataset.version.number}.`)
    },
    onError: (e) => toast('danger', errorMessage(e)),
  })

  const columns = preview.data?.columns ?? dataset.data?.variables.map((v) => v.name) ?? []
  const header = (
    <PageHeader
      breadcrumb={<Link to={`/p/${pid}`} className="hover:underline">{project.data?.name ?? 'Project'}</Link>}
      title="Clean data"
      description="Fix the raw data before analysis. The import is kept unchanged; the cleaned data is saved as a new version, which analyses then use. Export it with a cleaning log for your methodology."
      actions={<DatasetPicker datasets={datasets} value={datasetId} onChange={setDatasetId} />}
    />
  )
  if (query.isPending) return <>{header}<PageBody><Skeleton className="h-64" /></PageBody></>
  if (!datasets.length)
    return <>{header}<PageBody><EmptyState icon={<Sparkles />} title="Import data first" description="Cleaning works on an imported file." action={<Link to={`/p/${pid}/import`}><Button variant="primary">Import data</Button></Link>} /></PageBody></>
  if (suggestions.isError) return <>{header}<PageBody><ErrorState error={suggestions.error} retry={() => suggestions.refetch()} /></PageBody></>

  const list = suggestions.data?.suggestions ?? []
  return (
    <>
      {header}
      <PageBody>
        {saved && dataset.data && (
          <Callout tone="success" className="mb-4" title={`Cleaned data saved as version ${saved.version}`}>
            <p>Analyses now use the cleaned data. The raw import is still available as version 1.</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Exports dataset={dataset.data} />
              <Link to={`/p/${pid}/objectives`}><Button variant="ghost">Continue to objectives <ArrowRight /></Button></Link>
            </div>
          </Callout>
        )}
        <div className="grid gap-4 lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)]">
          <div className="min-w-0 space-y-4">
            <Panel title="Suggested fixes" description={suggestions.data ? (list.length ? `${list.length} found in version ${suggestions.data.version_number}` : undefined) : 'Checking the data…'}>
              {!suggestions.data ? <Skeleton className="h-32" /> : list.length === 0 ? (
                <p className="flex items-center gap-2 text-[13px] text-muted"><Check className="size-4 text-success" /> No common problems found. You can still add your own steps below.</p>
              ) : (
                <ul className="-my-1 divide-y divide-line">
                  {list.map((s) => {
                    const on = accepted[s.id] ?? s.default
                    return (
                      <li key={s.id} className="flex gap-3 py-2.5">
                        <Checkbox checked={on} onCheckedChange={(v) => setAccepted((a) => ({ ...a, [s.id]: v }))} aria-label={s.title} className="mt-0.5" />
                        <div className="min-w-0 text-[13px]">
                          <p className={cn('font-medium', !on && 'text-muted')}>{s.title}</p>
                          <p className="mt-0.5 break-words text-muted">{s.detail}</p>
                          {!s.default && <p className="mt-1 flex items-center gap-1 text-xs text-warning"><AlertTriangle className="size-3.5" /> Review before applying</p>}
                          {s.examples.length > 0 && <p className="mt-1 truncate text-xs text-muted">e.g. {s.examples.map((x) => `“${x}”`).join(', ')}</p>}
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </Panel>

            <Panel title="Your own steps" description="Run after the suggested fixes, in this order.">
              {manual.length > 0 && (
                <ol className="mb-4 space-y-1.5">
                  {manual.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 rounded-md border border-line px-2.5 py-1.5 text-[13px]">
                      <span className="text-muted tabular-nums">{chosen.length + i + 1}.</span>
                      <span className="min-w-0 flex-1 break-words">{describe(s)}</span>
                      <button type="button" className="rounded p-0.5 text-muted hover:text-danger" aria-label={`Remove step ${chosen.length + i + 1}`} onClick={() => setManual(manual.filter((_, j) => j !== i))}><X className="size-4" /></button>
                    </li>
                  ))}
                </ol>
              )}
              {datasetId && columns.length > 0 && <StepForm key={columns.join('|')} columns={columns} datasetId={datasetId} onAdd={(s) => setManual([...manual, s])} />}
            </Panel>
          </div>

          <div className="min-w-0 space-y-4">
            <Panel
              title="Preview"
              description={steps.length ? `${steps.length} ${steps.length === 1 ? 'step' : 'steps'} · changed cells are highlighted` : 'Choose fixes or add steps to see the result'}
              actions={
                <Button variant="primary" disabled={!steps.length || preview.isError} loading={apply.isPending} onClick={() => apply.mutate()}>
                  <Check /> Save cleaned version
                </Button>
              }
            >
              {preview.isError ? (
                <Callout tone="danger" title="A step cannot run">{errorMessage(preview.error)}</Callout>
              ) : !preview.data ? <Skeleton className="h-72" /> : (
                <div className={cn('space-y-4 transition-opacity', preview.isFetching && 'opacity-60')}>
                  <SummaryStrip before={preview.data.before} after={preview.data.after} />
                  {preview.data.log.length > 0 && (
                    <section>
                      <h3 className="label-caps mb-1.5">Cleaning log</h3>
                      <ol className="list-decimal space-y-1 pl-5 text-[13px] text-fg-2">
                        {preview.data.log.map((l) => <li key={l.step}>{l.message}</li>)}
                      </ol>
                    </section>
                  )}
                  <section>
                    <h3 className="label-caps mb-1.5">First {preview.data.rows.length} rows after cleaning</h3>
                    <PreviewTable preview={preview.data} />
                  </section>
                </div>
              )}
            </Panel>
            {dataset.data && (
              <Panel title="Export" description={`Version ${dataset.data.version.number} of ${dataset.data.versions.length} · ${dataset.data.row_count.toLocaleString()} rows`}>
                <Exports dataset={dataset.data} />
                {(dataset.data.lineage.cleaning?.length ?? 0) > 0 && (
                  <p className="mt-3 text-xs text-muted">The Excel file includes a “Cleaning log” sheet listing every change since the raw import.</p>
                )}
              </Panel>
            )}
          </div>
        </div>
        {!saved && (
          <div className="mt-4 flex justify-end">
            <Link to={`/p/${pid}/objectives`} className="text-[13px] text-muted hover:text-fg hover:underline">Skip — the data is already clean</Link>
          </div>
        )}
      </PageBody>
    </>
  )
}
