import { useQueryClient } from '@tanstack/react-query'
import { Check, FileSpreadsheet, RotateCcw, Upload } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { PageBody, PageHeader } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Badge, Callout, Panel, useToast } from '@/components/ui/feedback'
import { Checkbox, Field, Input, Select, Switch } from '@/components/ui/form'
import { Tooltip } from '@/components/ui/overlay'
import { useActiveDataset, useProjectId } from '@/lib/active'
import { api, errorMessage, uploadWithProgress } from '@/lib/api'
import { formatBytes, LEVEL_HELP, LEVEL_LABEL, LEVELS } from '@/lib/format'
import { keys, useProject } from '@/lib/queries'
import type { Dataset, ImportIssue, ImportPreview, Level } from '@/lib/types'
import { cn } from '@/lib/utils'

const ACCEPT = '.csv,.tsv,.txt,.xlsx,.xlsm,.xls,.json,.ndjson,.jsonl,.parquet'
const DEFAULT_NULLS = ['', 'NA', 'N/A', 'n/a', 'NaN', 'nan', 'NULL', 'null', 'None', '#N/A', '-']
const STEPS = ['Select file', 'Preview', 'Review variables', 'Import']

interface Options {
  sheet?: string
  delimiter?: string
  has_header: boolean
  encoding: string
  null_values: string[]
  skip_rows: number
  decimal_comma: boolean
  ragged_lines: 'error' | 'truncate'
  date_formats: Record<string, string>
}

interface VarChoice {
  include: boolean
  rename: string
  level: Level
}

export default function ImportPage() {
  const pid = useProjectId()
  const project = useProject(pid)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const { setDatasetId } = useActiveDataset(pid)
  const [step, setStep] = useState(0)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [options, setOptions] = useState<Options>({
    has_header: true,
    encoding: 'utf-8',
    null_values: DEFAULT_NULLS,
    skip_rows: 0,
    decimal_comma: false,
    ragged_lines: 'error',
    date_formats: {},
  })
  const [choices, setChoices] = useState<Record<string, VarChoice>>({})
  const [name, setName] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const resetChoices = (p: ImportPreview) => {
    setChoices((prev) => {
      const next: Record<string, VarChoice> = {}
      for (const v of p.variables)
        next[v.column_name] = prev[v.column_name] ?? { include: true, rename: v.column_name, level: v.measurement_level }
      return next
    })
  }

  const [progress, setProgress] = useState<number | null>(null)
  const upload = async (file: File) => {
    setError(null)
    setBusy('Uploading and reading the file')
    try {
      const form = new FormData()
      form.append('file', file)
      setProgress(0)
      const p = await uploadWithProgress<ImportPreview>('/datasets/uploads', form, (f) => {
        setProgress(f)
        if (f >= 1) setBusy('Reading the file and detecting column types')
      })
      setPreview(p)
      setOptions((o) => ({ ...o, sheet: p.detected.sheet, delimiter: p.detected.delimiter }))
      setName(file.name.replace(/\.[^.]+$/, ''))
      resetChoices(p)
      setStep(1)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(null)
      setProgress(null)
    }
  }

  const refresh = async (next: Partial<Options>) => {
    if (!preview) return
    const merged = { ...options, ...next }
    setOptions(merged)
    setBusy('Updating preview')
    setError(null)
    try {
      const p = await api.post<ImportPreview>(`/datasets/uploads/${preview.upload.upload_id}/preview`, { options: merged })
      setPreview(p)
      resetChoices(p)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  const location = useLocation()
  const handedFile = (location.state as { file?: File } | null)?.file
  const started = useRef(false)
  useEffect(() => {
    if (handedFile && !started.current) {
      started.current = true
      window.history.replaceState({}, '')
      upload(handedFile)
    }
  }, [handedFile]) // eslint-disable-line react-hooks/exhaustive-deps

  const blocking = (preview?.issues ?? []).filter((i) => i.severity === 'error')

  const commit = async () => {
    if (!preview) return
    setBusy('Importing')
    setError(null)
    const renames: Record<string, string> = {}
    const exclude: string[] = []
    const variables: Record<string, { measurement_level: Level }> = {}
    for (const v of preview.variables) {
      const c = choices[v.column_name]
      if (!c) continue
      if (!c.include) exclude.push(v.column_name)
      else {
        if (c.rename.trim() && c.rename.trim() !== v.column_name) renames[v.column_name] = c.rename.trim()
        variables[c.rename.trim() || v.column_name] = { measurement_level: c.level }
      }
    }
    try {
      const ds = await api.post<Dataset>('/datasets', {
        project_id: pid,
        upload_id: preview.upload.upload_id,
        name: name.trim() || undefined,
        options: { ...options, renames, exclude_columns: exclude },
        variables,
      })
      qc.invalidateQueries({ queryKey: keys.datasets(pid) })
      qc.invalidateQueries({ queryKey: keys.project(pid) })
      setDatasetId(ds.id)
      toast('success', `Imported ${ds.row_count.toLocaleString()} rows and ${ds.column_count} variables.`)
      navigate(`/p/${pid}/clean`)
    } catch (e) {
      setError(errorMessage(e))
      setBusy(null)
    }
  }

  const startOver = () => {
    if (preview) api.del(`/datasets/uploads/${preview.upload.upload_id}`).catch(() => {})
    setPreview(null)
    setStep(0)
    setError(null)
  }

  return (
    <>
      <PageHeader
        breadcrumb={<Link to={`/p/${pid}`} className="hover:underline">{project.data?.name ?? 'Project'}</Link>}
        title="Import data"
        description="Your original file is stored unchanged. Every import creates a separate, versioned dataset."
        actions={preview && <Button variant="ghost" onClick={startOver}><RotateCcw /> Start over</Button>}
      />
      <PageBody className="space-y-4">
        <Stepper step={step} />
        {error && <Callout tone="danger" title="Import problem">{error}</Callout>}

        {step === 0 && <DropZone onFile={upload} busy={busy} progress={progress} />}

        {preview && step === 1 && (
          <>
            <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
              <Panel title="Import options" description={`${preview.upload.filename} · ${formatBytes(preview.upload.size_bytes)}`}>
                <OptionsForm preview={preview} options={options} onChange={refresh} busy={!!busy} />
              </Panel>
              <div className="min-w-0 space-y-3">
                <Issues issues={preview.issues} options={options} onFix={refresh} />
                <Panel title="Preview" description={`First ${preview.rows.length} rows · ${preview.columns.length} columns`} bodyClassName="p-0">
                  <PreviewTable columns={preview.columns} rows={preview.rows} />
                </Panel>
              </div>
            </div>
            <Footer>
              <Button onClick={startOver}>Back</Button>
              <Button variant="primary" onClick={() => setStep(2)} disabled={blocking.length > 0 || preview.columns.length === 0 || !!busy}>
                Continue to variables
              </Button>
            </Footer>
          </>
        )}

        {preview && step === 2 && (
          <>
            <Callout tone="info" title="Check how each column will be treated">
              Types were inferred from the values. Numbers are not assumed to be measurements: a 1–5 rating is treated as ordinal, and ID
              columns are excluded from analyses. Correct anything that looks wrong — you can change this later too.
            </Callout>
            <VariableReview preview={preview} choices={choices} onChange={setChoices} />
            <Footer>
              <Button onClick={() => setStep(1)}>Back</Button>
              <Button variant="primary" onClick={() => setStep(3)}>
                Continue
              </Button>
            </Footer>
          </>
        )}

        {preview && step === 3 && (
          <>
            <Panel title="Confirm import">
              <div className="grid max-w-2xl gap-4 sm:grid-cols-2">
                <Field label="Dataset name">{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
                <div className="text-[13px]">
                  <div className="text-xs text-muted">Summary</div>
                  <ul className="mt-1 space-y-0.5">
                    <li>{Object.values(choices).filter((c) => c.include).length} of {preview.columns.length} columns included</li>
                    <li>{options.sheet ? `Worksheet “${options.sheet}”` : `Delimiter “${options.delimiter === '\t' ? 'tab' : options.delimiter}”`}</li>
                    <li>{preview.issues.length} import note(s)</li>
                  </ul>
                </div>
              </div>
            </Panel>
            <Footer>
              <Button onClick={() => setStep(2)}>Back</Button>
              <Button variant="primary" onClick={commit} loading={busy === 'Importing'}>
                <Check /> Import data
              </Button>
            </Footer>
          </>
        )}
        {busy && step > 0 && busy !== 'Importing' && <p className="text-xs text-muted">{busy}…</p>}
      </PageBody>
    </>
  )
}

function Stepper({ step }: { step: number }) {
  return (
    <ol className="flex items-center gap-2 overflow-x-auto text-[13px]" aria-label="Import progress">
      {STEPS.map((s, i) => (
        <li key={s} className="flex shrink-0 items-center gap-2">
          <span
            aria-current={i === step ? 'step' : undefined}
            className={cn(
              'num flex size-6 items-center justify-center rounded-full border text-xs font-semibold',
              i < step && 'border-accent bg-accent text-accent-fg',
              i === step && 'border-accent text-accent',
              i > step && 'border-line-strong text-muted',
            )}
          >
            {i < step ? <Check className="size-3.5" /> : i + 1}
          </span>
          <span className={cn(i === step ? 'font-medium text-fg' : 'text-muted', i !== step && 'hidden sm:inline')}>{s}</span>
          {i < STEPS.length - 1 && <span className="h-px w-6 bg-line-strong sm:w-10" aria-hidden />}
        </li>
      ))}
    </ol>
  )
}

function Footer({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap justify-between gap-2 border-t border-line pt-4">{children}</div>
}

function DropZone({ onFile, busy, progress }: { onFile: (f: File) => void; busy: string | null; progress: number | null }) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setOver(false)
      const f = e.dataTransfer.files?.[0]
      if (f) onFile(f)
    },
    [onFile],
  )
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={cn(
        'flex flex-col items-center justify-center rounded-lg border-2 border-dashed bg-surface px-6 py-14 text-center transition-colors',
        over ? 'border-accent bg-accent-soft' : 'border-line-strong',
      )}
    >
      <FileSpreadsheet className="size-8 text-muted" aria-hidden />
      <h2 className="mt-3 text-[15px] font-semibold">{busy ? `${busy}…` : 'Drop a file here, or choose one'}</h2>
      {busy && progress !== null && (
        <div className="mt-3 w-full max-w-xs" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)} aria-label="Upload progress">
          <div className="h-1.5 overflow-hidden rounded-full bg-surface-3">
            {progress < 1 ? <div className="h-full bg-accent transition-[width]" style={{ width: `${progress * 100}%` }} /> : <div className="progress-indeterminate h-full w-1/3 bg-accent" />}
          </div>
          <div className="num mt-1 text-xs text-muted">{progress < 1 ? `${Math.round(progress * 100)}% uploaded` : 'Analysing columns…'}</div>
        </div>
      )}
      <p className="mt-1 max-w-md text-[13px] text-muted">
        Excel (.xlsx, .xls), CSV, TSV, JSON or Parquet. The first row should contain column names; you can change this in the next step.
      </p>
      <input ref={input} type="file" accept={ACCEPT} className="sr-only" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} aria-label="Choose a data file" />
      <Button variant="primary" size="lg" className="mt-5" onClick={() => input.current?.click()} loading={!!busy}>
        <Upload /> Choose file
      </Button>
    </div>
  )
}

function OptionsForm({ preview, options, onChange, busy }: { preview: ImportPreview; options: Options; onChange: (o: Partial<Options>) => void; busy: boolean }) {
  const isText = ['csv', 'tsv'].includes(preview.upload.format)
  const isExcel = ['xlsx', 'xls'].includes(preview.upload.format)
  const [nulls, setNulls] = useState(options.null_values.filter(Boolean).join(', '))
  return (
    <div className="space-y-3">
      {isExcel && preview.detected.sheets && (
        <Field label="Worksheet">
          {(id) => (
            <Select id={id} value={options.sheet} onChange={(e) => onChange({ sheet: e.target.value })} disabled={busy}>
              {preview.detected.sheets!.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </Select>
          )}
        </Field>
      )}
      {isText && (
        <>
          <Field label="Delimiter">
            {(id) => (
              <Select id={id} value={options.delimiter} onChange={(e) => onChange({ delimiter: e.target.value })} disabled={busy}>
                <option value=",">Comma ( , )</option>
                <option value=";">Semicolon ( ; )</option>
                <option value={'\t'}>Tab</option>
                <option value="|">Pipe ( | )</option>
              </Select>
            )}
          </Field>
          <Field label="Encoding">
            {(id) => (
              <Select id={id} value={options.encoding} onChange={(e) => onChange({ encoding: e.target.value })} disabled={busy}>
                <option value="utf-8">UTF-8</option>
                <option value="cp1252">Windows-1252</option>
                <option value="latin-1">Latin-1 (ISO-8859-1)</option>
                <option value="utf-16">UTF-16</option>
              </Select>
            )}
          </Field>
          <div className="flex items-center justify-between gap-2 text-[13px]">
            <label htmlFor="decimal-comma">Decimal comma (1,5)</label>
            <Switch id="decimal-comma" checked={options.decimal_comma} onCheckedChange={(v) => onChange({ decimal_comma: v })} disabled={busy} />
          </div>
        </>
      )}
      {(isText || isExcel) && (
        <>
          <div className="flex items-center justify-between gap-2 text-[13px]">
            <label htmlFor="has-header">First row contains column names</label>
            <Switch id="has-header" checked={options.has_header} onCheckedChange={(v) => onChange({ has_header: v })} disabled={busy} />
          </div>
          <Field label="Rows to skip at the top">
            {(id) => (
              <Input id={id} type="number" min={0} value={options.skip_rows} onChange={(e) => onChange({ skip_rows: Math.max(0, Number(e.target.value)) })} disabled={busy} />
            )}
          </Field>
        </>
      )}
      <Field label="Values that mean “missing”" help="Comma-separated. Empty cells are always missing.">
        {(id) => (
          <Input
            id={id}
            value={nulls}
            onChange={(e) => setNulls(e.target.value)}
            onBlur={() => onChange({ null_values: ['', ...nulls.split(',').map((s) => s.trim()).filter(Boolean)] })}
            disabled={busy}
          />
        )}
      </Field>
    </div>
  )
}

function Issues({ issues, options, onFix }: { issues: ImportIssue[]; options: Options; onFix: (o: Partial<Options>) => void }) {
  if (!issues.length) return <Callout tone="success">No structural problems found in the file.</Callout>
  return (
    <div className="space-y-2">
      {issues.map((i, k) => (
        <Callout
          key={k}
          tone={i.severity === 'error' ? 'danger' : i.code.startsWith('duplicate') || i.code.startsWith('empty_column') ? 'info' : 'warning'}
          action={
            i.code === 'inconsistent_rows' && options.ragged_lines === 'error' ? (
              <Button size="sm" onClick={() => onFix({ ragged_lines: 'truncate' })}>Read anyway</Button>
            ) : i.code === 'mixed_types' && i.values?.length ? (
              <Button size="sm" onClick={() => onFix({ null_values: [...options.null_values, ...i.values!] })}>Treat as missing</Button>
            ) : i.code === 'ambiguous_date' && i.suggested_format && i.column ? (
              <Button size="sm" onClick={() => onFix({ date_formats: { ...options.date_formats, [i.column!]: i.suggested_format! } })}>
                Convert dates
              </Button>
            ) : undefined
          }
        >
          {i.message}
          {i.code === 'inconsistent_rows' && options.ragged_lines === 'error' && (
            <span className="block text-xs text-muted">“Read anyway” drops extra fields and fills short rows with missing values.</span>
          )}
        </Callout>
      ))}
    </div>
  )
}

export function PreviewTable({ columns, rows }: { columns: string[]; rows: unknown[][] }) {
  return (
    <div className="scroll-thin max-h-[440px] overflow-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead className="sticky top-0 z-10 bg-surface-2">
          <tr>
            <th className="num border-r border-b border-line px-2 py-1.5 text-right text-[11px] font-normal text-muted">#</th>
            {columns.map((c) => (
              <th key={c} className="border-b border-line px-3 py-1.5 text-left font-semibold whitespace-nowrap">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="hover:bg-surface-2">
              <td className="num border-r border-b border-line px-2 py-1 text-right text-[11px] text-muted">{i + 1}</td>
              {r.map((v, j) => (
                <td key={j} className={cn('max-w-64 truncate border-b border-line px-3 py-1 whitespace-nowrap', typeof v === 'number' && 'num text-right')}>
                  {v === null ? <span className="text-muted/70 italic">missing</span> : String(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function VariableReview({
  preview,
  choices,
  onChange,
}: {
  preview: ImportPreview
  choices: Record<string, VarChoice>
  onChange: (c: Record<string, VarChoice>) => void
}) {
  const set = (name: string, patch: Partial<VarChoice>) => onChange({ ...choices, [name]: { ...choices[name], ...patch } })
  const groups = useMemo(() => new Set(preview.variables.map((v) => v.scale_group).filter(Boolean)), [preview])
  return (
    <div className="overflow-hidden rounded-lg border border-line bg-surface">
      {groups.size > 0 && (
        <div className="border-b border-line bg-surface-2 px-4 py-2 text-xs text-fg-2">
          Possible questionnaire scales detected: {[...groups].join(', ')}. These will be suggested for reliability analysis.
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-[13px]">
          <thead className="border-b border-line bg-surface-2 text-left text-xs text-muted">
            <tr>
              <th className="w-10 px-3 py-2 font-medium">Use</th>
              <th className="px-3 py-2 font-medium">Column name</th>
              <th className="w-44 px-3 py-2 font-medium">Measurement level</th>
              <th className="px-3 py-2 font-medium">Example values</th>
              <th className="px-3 py-2 text-right font-medium">Missing</th>
              <th className="px-3 py-2 text-right font-medium">Distinct</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {preview.variables.map((v) => {
              const c = choices[v.column_name]
              if (!c) return null
              return (
                <tr key={v.column_name} className={cn(!c.include && 'opacity-50')}>
                  <td className="px-3 py-2 align-top">
                    <Checkbox checked={c.include} onCheckedChange={(x) => set(v.column_name, { include: x })} aria-label={`Include ${v.column_name}`} />
                  </td>
                  <td className="px-3 py-2 align-top">
                    <Input value={c.rename} onChange={(e) => set(v.column_name, { rename: e.target.value })} aria-label={`Name for ${v.column_name}`} className="h-7" />
                    <p className="mt-1 text-xs text-muted">{v.inference_note}</p>
                  </td>
                  <td className="px-3 py-2 align-top">
                    <Select value={c.level} onChange={(e) => set(v.column_name, { level: e.target.value as Level })} aria-label={`Measurement level of ${v.column_name}`}>
                      {LEVELS.map((l) => (
                        <option key={l} value={l} title={LEVEL_HELP[l]}>
                          {LEVEL_LABEL[l]}
                        </option>
                      ))}
                    </Select>
                    {c.level !== v.inferred_level && <p className="mt-1 text-xs text-accent">Changed from {LEVEL_LABEL[v.inferred_level]}</p>}
                    {v.scale_group && <Badge className="mt-1">Scale: {v.scale_group}</Badge>}
                  </td>
                  <td className="max-w-64 px-3 py-2 align-top text-xs text-fg-2">
                    <Tooltip content={v.examples.join(', ')}>
                      <span className="line-clamp-2">{v.examples.join(', ')}</span>
                    </Tooltip>
                  </td>
                  <td className="num px-3 py-2 text-right align-top">{v.n_missing}</td>
                  <td className="num px-3 py-2 text-right align-top">{v.n_unique}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="border-t border-line px-4 py-2 text-xs text-muted">Missing and distinct counts are based on the preview sample of up to 20,000 rows.</p>
    </div>
  )
}
