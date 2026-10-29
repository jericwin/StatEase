import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, ArrowRight, CheckCircle2, ListChecks, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DatasetPicker } from '@/components/DatasetPicker'
import { Button } from '@/components/ui/button'
import { Badge, Callout, EmptyState } from '@/components/ui/feedback'
import { Checkbox, Field, Input, Select, Textarea } from '@/components/ui/form'
import { useActiveDataset } from '@/lib/active'
import { api, errorMessage } from '@/lib/api'
import { LEVEL_LABEL } from '@/lib/format'
import { useCatalog, useDataset } from '@/lib/queries'
import type { AnalysisSpec, Dataset, Objective, ObjectiveAnalysis, Report } from '@/lib/types'
import { asArray, cn } from '@/lib/utils'

export const EXAMPLE = `1. What is the demographic profile of the respondents in terms of:
1.1 Age
1.2 Gender
2. What is the level of acceptability of the product in terms of:
2.1 Appearance
2.2 Aroma
2.3 Taste
2.4 Texture
2.5 Overall acceptability
3. Which formulation is the most acceptable?
4. Is there a significant difference in the level of acceptability between the two formulations?`

function categoriesOf(dataset: Dataset, name: string): string[] {
  const v = dataset.variables.find((x) => x.name === name)
  return (v?.profile.categories ?? []).map((c) => v?.category_labels[String(c.value)] ?? String(c.value))
}

function isReady(a: ObjectiveAnalysis, spec?: AnalysisSpec) {
  if (!spec) return false
  return spec.roles.every((r) => asArray(a.variables[r.key] as string | string[]).filter(Boolean).length >= r.min)
}

/** The variables an analysis needs, as a checklist (multi-variable roles) or a dropdown (single roles). */
function VariableChecklist({ analysis, spec, dataset, onChange }: { analysis: ObjectiveAnalysis; spec: AnalysisSpec; dataset: Dataset; onChange: (a: ObjectiveAnalysis) => void }) {
  const vars = dataset.variables.filter((v) => v.level !== 'identifier' && v.level !== 'text')
  const setRole = (key: string, value: string | string[]) => onChange({ ...analysis, variables: { ...analysis.variables, [key]: value } })
  const groupCol = (analysis.variables.group as string) || ''
  const cats = groupCol ? categoriesOf(dataset, groupCol) : []
  return (
    <div className="space-y-3">
      {spec.roles.map((role) => {
        const eligible = vars.filter((v) => role.levels.includes(v.level))
        const current = asArray(analysis.variables[role.key] as string | string[]).filter(Boolean)
        if (role.max === 1)
          return (
            <Field key={role.key} label={role.label}>
              {(id) => (
                <Select id={id} value={current[0] ?? ''} onChange={(e) => setRole(role.key, e.target.value)}>
                  <option value="">{role.min ? 'Choose a column…' : 'None'}</option>
                  {eligible.map((v) => <option key={v.name} value={v.name}>{v.label || v.name}</option>)}
                </Select>
              )}
            </Field>
          )
        const others = new Set(spec.roles.filter((r) => r.key !== role.key).flatMap((r) => asArray(analysis.variables[r.key] as string | string[])))
        return (
          <fieldset key={role.key}>
            <legend className="mb-1.5 flex items-baseline gap-2 text-[13px] font-medium text-fg-2">
              {role.label} <span className="text-xs font-normal text-muted">{current.length} selected</span>
            </legend>
            <div className="grid gap-x-4 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
              {eligible.filter((v) => !others.has(v.name)).map((v) => {
                const on = current.includes(v.name)
                return (
                  <label key={v.name} className={cn('flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-[13px] hover:bg-surface-2', on && 'font-medium')}>
                    <Checkbox checked={on} onCheckedChange={(c) => setRole(role.key, c ? [...current, v.name] : current.filter((x) => x !== v.name))} aria-label={v.label || v.name} />
                    <span className="truncate">{v.label || v.name}</span>
                    <span className="ml-auto shrink-0 text-[11px] text-muted">{LEVEL_LABEL[v.level]}</span>
                  </label>
                )
              })}
            </div>
          </fieldset>
        )
      })}
      {analysis.analysis_type === 'compare_two_groups' && cats.length > 2 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {(['group_a', 'group_b'] as const).map((k, i) => (
            <Field key={k} label={i ? 'Second group' : 'First group'}>
              {(id) => (
                <Select id={id} value={String(analysis.options[k] ?? '')} onChange={(e) => onChange({ ...analysis, options: { ...analysis.options, [k]: e.target.value } })}>
                  <option value="">Choose…</option>
                  {cats.map((c) => <option key={c}>{c}</option>)}
                </Select>
              )}
            </Field>
          ))}
        </div>
      )}
      {analysis.analysis_type === 'rank_groups' && (
        <Field label="Decide the most acceptable by">
          {(id) => (
            <Select id={id} value={String(analysis.options.decide_by ?? 'average')} onChange={(e) => onChange({ ...analysis, options: { ...analysis.options, decide_by: e.target.value } })}>
              <option value="average">Average of all selected measures</option>
              {asArray(analysis.variables.measures as string[]).map((m) => <option key={m} value={m}>{dataset.variables.find((v) => v.name === m)?.label || m}</option>)}
            </Select>
          )}
        </Field>
      )}
      {analysis.filter && (
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="text-muted">Only:</span>
          {categoriesOf(dataset, analysis.filter.column).map((c) => {
            const on = analysis.filter!.values.includes(c)
            return (
              <button key={c} type="button" aria-pressed={on}
                onClick={() => {
                  const values = on ? analysis.filter!.values.filter((x) => x !== c) : [...analysis.filter!.values, c]
                  onChange({ ...analysis, filter: values.length ? { ...analysis.filter!, values } : null })
                }}
                className={cn('h-7 rounded-full border px-2.5 text-[12.5px]', on ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong text-fg-2')}>
                {c}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function ObjectivesStep({ projectId, onCreated, onCancel, skipLink }: { projectId: number; onCreated: (r: Report) => void; onCancel?: () => void; skipLink?: string }) {
  const { datasetId, setDatasetId, datasets } = useActiveDataset(projectId)
  const dataset = useDataset(datasetId)
  const catalog = useCatalog()
  const qc = useQueryClient()
  const [text, setText] = useState('')
  const [title, setTitle] = useState('Results and Discussion')
  const [objectives, setObjectives] = useState<Objective[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const specs = useMemo(() => Object.fromEntries((catalog.data?.analyses ?? []).map((a) => [a.id, a])), [catalog.data])

  const parse = useMutation({
    mutationFn: () => api.post<{ objectives: Objective[] }>('/reports/objectives/parse', { dataset_id: datasetId, text }),
    onSuccess: (r) => { setObjectives(r.objectives); setError(null) },
    onError: (e) => setError(errorMessage(e)),
  })
  const create = useMutation({
    mutationFn: (withObjectives: boolean) => api.post<Report>('/reports', {
      project_id: projectId, dataset_id: datasetId, title,
      objectives: withObjectives ? objectives!.map((o) => ({ ...o, analyses: o.analyses.map((a) => ({ ...a, status: isReady(a, specs[a.analysis_type]) ? 'ready' : 'needs_input' })) })) : null,
    }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['reports', projectId] })
      qc.invalidateQueries({ queryKey: ['results', projectId] })
      onCreated(r)
    },
    onError: (e) => setError(errorMessage(e)),
  })

  const updateAnalysis = (oi: number, ai: number, a: ObjectiveAnalysis) =>
    setObjectives((list) => list!.map((o, j) => {
      if (j !== oi) return o
      const analyses = o.analyses.map((x, k) => (k === ai ? { ...a, status: isReady(a, specs[a.analysis_type]) ? 'ready' as const : 'needs_input' as const } : x))
      return { ...o, analyses, status: analyses.length && analyses.every((x) => x.status === 'ready') ? 'ready' : 'needs_input' }
    }))

  if (datasets.length === 0)
    return <EmptyState icon={<ListChecks />} title="Import data first" description="Objectives are matched to the columns of your dataset." action={<Link to={`/p/${projectId}/import`}><Button variant="primary">Import data</Button></Link>} />

  const readyCount = objectives?.filter((o) => o.status === 'ready').length ?? 0
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <section className="rounded-xl border border-line bg-surface p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-[17px] font-semibold">Statement of the problem</h2>
            <p className="mt-0.5 max-w-xl text-[13.5px] text-muted">Paste your objectives or research questions exactly as written, including sub-items like 1.1 and 1.2. Each becomes a section of your results with only the tables it needs.</p>
          </div>
          <DatasetPicker datasets={datasets} value={datasetId} onChange={(id) => { setDatasetId(id); setObjectives(null) }} />
        </div>
        <Textarea className="mt-4 min-h-52 font-mono text-[13px] leading-relaxed" placeholder={EXAMPLE} value={text}
          onChange={(e) => { setText(e.target.value); setObjectives(null) }} aria-label="Objectives of the study" />
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={() => parse.mutate()} loading={parse.isPending} disabled={text.trim().length < 5 || !datasetId}>
            <ListChecks /> Find the variables
          </Button>
          <Button variant="ghost" onClick={() => setText(EXAMPLE)}>Use example</Button>
          <div className="flex-1" />
          {skipLink && <Link to={skipLink} className="text-[13px] text-muted hover:text-fg hover:underline">Skip — explore recommended analyses</Link>}
          {onCancel && <Button variant="ghost" onClick={onCancel}>Cancel</Button>}
        </div>
        {error && <Callout tone="danger" className="mt-3">{error}</Callout>}
      </section>

      {objectives && dataset.data && (
        <section className="animate-in space-y-3" aria-label="Variables needed for each objective">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-[15px] font-semibold">Variables needed</h2>
            <span className="text-[13px] text-muted">{readyCount} of {objectives.length} objectives ready</span>
          </div>
          {objectives.map((o, i) => {
            const ok = o.status === 'ready'
            return (
              <div key={o.id} className={cn('rounded-xl border bg-surface', ok ? 'border-line' : 'border-warning/50')}>
                <div className="flex items-start gap-3 border-b border-line px-4 py-3">
                  {ok ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" aria-label="Ready" /> : <AlertCircle className="mt-0.5 size-5 shrink-0 text-warning" aria-label="Needs input" />}
                  <div className="min-w-0 flex-1">
                    <p className="text-[14px] font-medium">{i + 1}. {o.text}</p>
                    {!!o.subitems?.length && (
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {o.subitems.map((s, k) => <Badge key={s}>{i + 1}.{k + 1} {s}</Badge>)}
                      </div>
                    )}
                    {!ok && o.question && <p className="mt-1.5 text-[13px] text-warning">{o.question}</p>}
                    {o.assumed.map((a) => <p key={a} className="mt-1 text-[12.5px] text-muted">{a}</p>)}
                  </div>
                  <button className="rounded p-1 text-muted hover:text-danger" onClick={() => setObjectives(objectives.filter((_, j) => j !== i))} aria-label={`Remove objective ${i + 1}`}><Trash2 className="size-4" /></button>
                </div>
                <div className="divide-y divide-line">
                  {o.analyses.map((a, ai) => {
                    const spec = specs[a.analysis_type]
                    return (
                      <div key={ai} className="px-4 py-3">
                        <div className="mb-2 flex flex-wrap items-baseline gap-x-2 text-[13px]">
                          <span className="font-semibold">{spec?.plain_name ?? a.analysis_type}</span>
                          <span className="text-muted">{spec?.name}</span>
                        </div>
                        {spec && <VariableChecklist analysis={a} spec={spec} dataset={dataset.data!} onChange={(na) => updateAnalysis(i, ai, na)} />}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
          <div className="flex flex-wrap items-end gap-3 rounded-xl border border-line bg-surface p-4">
            <Field label="Report title" className="min-w-60 flex-1">{(id) => <Input id={id} value={title} onChange={(e) => setTitle(e.target.value)} />}</Field>
            <Button variant="primary" size="lg" onClick={() => create.mutate(true)} loading={create.isPending && create.variables === true} disabled={!objectives.length || readyCount === 0}>
              Analyze objectives <ArrowRight />
            </Button>
          </div>
          {readyCount < objectives.length && <p className="text-[12.5px] text-muted">Objectives that still need variables are kept as headings so you can finish them later.</p>}
          {create.isPending && (
            <div className="rounded-xl border border-line bg-surface p-4" role="status">
              <p className="text-[13px] text-fg-2">Running the analyses for {readyCount} objectives and assembling your results…</p>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-3"><div className="progress-indeterminate h-full w-1/3 bg-accent" /></div>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
