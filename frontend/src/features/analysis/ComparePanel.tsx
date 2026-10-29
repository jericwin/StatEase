import { useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Check, ChevronDown, GitCompareArrows, Info, Users } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Callout, EmptyState } from '@/components/ui/feedback'
import { Field, SegmentedControl, Select } from '@/components/ui/form'
import { ResultView } from '@/features/results/ResultView'
import { api, errorMessage } from '@/lib/api'
import type { AnalysisResult, ComparePlan, Configuration, Dataset, ProjectSettings, ResultItem, Run } from '@/lib/types'
import { cn } from '@/lib/utils'

const GROUP_LEVELS = ['nominal', 'binary', 'ordinal']
const MEASURE_LEVELS = ['numeric', 'ordinal']

function categoriesOf(dataset: Dataset, name: string): string[] {
  const v = dataset.variables.find((x) => x.name === name)
  const cats = v?.profile.categories ?? []
  const key = (x: string | number) => (typeof x === 'number' && Number.isInteger(x) ? String(x) : String(x))
  return cats.map((c) => v?.category_labels[key(c.value)] ?? key(c.value))
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cn(
        'inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] transition-colors',
        on ? 'border-accent bg-accent-soft font-medium text-accent' : 'border-line-strong text-fg-2 hover:border-accent/50',
      )}
    >
      {on && <Check className="size-3.5" />}
      {children}
    </button>
  )
}

export function ComparePanel({ projectId, dataset, settings }: { projectId: number; dataset: Dataset; settings: ProjectSettings }) {
  const qc = useQueryClient()
  const vars = dataset.variables
  const groupers = useMemo(() => vars.filter((v) => GROUP_LEVELS.includes(v.level) && (v.profile.unique ?? 0) >= 2 && (v.profile.unique ?? 0) <= 20), [vars])
  const measuresAll = useMemo(() => vars.filter((v) => MEASURE_LEVELS.includes(v.level) && !(v.level === 'ordinal' && (v.profile.unique ?? 0) < 5 && groupers.some((g) => g.name === v.name))), [vars, groupers])

  const [mode, setMode] = useState<'groups' | 'variables'>(groupers.length ? 'groups' : 'variables')
  const [group, setGroup] = useState(groupers[0]?.name ?? '')
  const levels = useMemo(() => (group ? categoriesOf(dataset, group) : []), [dataset, group])
  const [chosen, setChosen] = useState<string[]>([])
  const [measures, setMeasures] = useState<string[]>([])
  const [var1, setVar1] = useState(measuresAll[0]?.name ?? '')
  const [var2, setVar2] = useState(measuresAll[1]?.name ?? '')
  const [relation, setRelation] = useState<'paired' | 'relationship' | undefined>()
  const [test, setTest] = useState('auto')
  const [advanced, setAdvanced] = useState(false)
  const [question, setQuestion] = useState<ComparePlan['question'] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<{ plan: ComparePlan; item: ResultItem } | null>(null)

  useEffect(() => {
    setChosen(levels.slice(0, levels.length === 2 ? 2 : levels.length))
  }, [levels])
  useEffect(() => {
    setMeasures(measuresAll.filter((m) => m.name !== group).slice(0, 10).map((m) => m.name))
  }, [measuresAll, group])
  useEffect(() => {
    setRelation(undefined)
    setQuestion(null)
  }, [var1, var2])

  const testChoices = mode === 'groups'
    ? chosen.length === 2
      ? [['auto', 'Automatic (recommended)'], ['welch', "Welch's t-test"], ['student', "Student's t-test"], ['mann_whitney', 'Mann–Whitney U']]
      : [['auto', 'Automatic (recommended)'], ['anova', 'One-way ANOVA'], ['welch_anova', "Welch's ANOVA"], ['kruskal', 'Kruskal–Wallis']]
    : relation === 'paired'
      ? [['auto', 'Automatic (recommended)'], ['paired_t', 'Paired t-test'], ['wilcoxon', 'Wilcoxon signed-rank']]
      : [['auto', 'Automatic (recommended)'], ['pearson', 'Pearson'], ['spearman', 'Spearman'], ['kendall', "Kendall's tau"]]

  const run = async (rel = relation) => {
    setBusy(true)
    setError(null)
    setOutcome(null)
    try {
      const body = mode === 'groups'
        ? { dataset_id: dataset.id, mode, group, levels: chosen, measures, test: test === 'auto' ? undefined : test }
        : { dataset_id: dataset.id, mode, var1, var2, relation: rel, test: test === 'auto' ? undefined : test }
      const plan = await api.post<ComparePlan>('/analyses/compare/plan', body)
      if (plan.question) {
        setQuestion(plan.question)
        return
      }
      setQuestion(null)
      const cfg = await api.post<Configuration>('/analyses/configurations', {
        project_id: projectId, dataset_version_id: plan.dataset_version_id, analysis_type: plan.analysis_type,
        variables: plan.variables, options: plan.options, name: plan.title,
      })
      const runs = await api.post<{ items: Run[] }>('/analyses/runs', { configuration_ids: [cfg.id], wait: true })
      const runRow = runs.items[0]
      let result: AnalysisResult | null = null
      let edited: string | null = null
      if (runRow.status === 'completed') {
        const r = await api.get<{ result: AnalysisResult; edited_interpretation: string | null }>(`/analyses/runs/${runRow.id}/results`)
        result = r.result
        edited = r.edited_interpretation
      }
      setOutcome({ plan, item: { configuration: { id: cfg.id, name: cfg.name, analysis_type: cfg.analysis_type }, run: runRow, result, edited_interpretation: edited } })
      qc.invalidateQueries({ queryKey: ['configs', projectId] })
      qc.invalidateQueries({ queryKey: ['results', projectId] })
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  if (!measuresAll.length)
    return <EmptyState icon={<GitCompareArrows />} title="Nothing to compare yet" description="This dataset has no numeric or rating columns. Check the column types in the Data tab." />

  const canRun = mode === 'groups' ? !!group && chosen.length >= 2 && measures.length > 0 : !!var1 && !!var2 && var1 !== var2
  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-line bg-surface">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
          <h2 className="text-[15px] font-semibold">What do you want to compare?</h2>
          <SegmentedControl
            label="Comparison type"
            value={mode}
            onChange={(m) => { setMode(m); setTest('auto'); setOutcome(null) }}
            options={[{ value: 'groups', label: 'Groups' }, { value: 'variables', label: 'Two measurements' }]}
          />
        </div>
        <div className="space-y-5 p-5">
          {mode === 'groups' ? (
            groupers.length === 0 ? (
              <Callout tone="info">No grouping column was found. If a column holds group codes (for example 1 and 2), set its type to Nominal in the Data tab.</Callout>
            ) : (
              <>
                <div className="grid gap-4 sm:grid-cols-[260px_1fr]">
                  <Field label="Groups are in column">
                    {(id) => (
                      <Select id={id} value={group} onChange={(e) => setGroup(e.target.value)}>
                        {groupers.map((g) => <option key={g.name} value={g.name}>{g.label || g.name}</option>)}
                      </Select>
                    )}
                  </Field>
                  <div>
                    <div className="mb-1.5 text-[13px] font-medium text-fg-2">Compare these groups</div>
                    <div className="flex flex-wrap gap-2">
                      {levels.map((lv) => (
                        <Chip key={lv} on={chosen.includes(lv)} onClick={() => setChosen(chosen.includes(lv) ? chosen.filter((x) => x !== lv) : [...chosen, lv])}>{lv}</Chip>
                      ))}
                    </div>
                  </div>
                </div>
                <div>
                  <div className="mb-1.5 flex items-center justify-between">
                    <span className="text-[13px] font-medium text-fg-2">Measures</span>
                    <span className="flex gap-3 text-xs">
                      <button className="text-accent hover:underline" onClick={() => setMeasures(measuresAll.filter((m) => m.name !== group).map((m) => m.name))}>All</button>
                      <button className="text-accent hover:underline" onClick={() => setMeasures([])}>None</button>
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {measuresAll.filter((m) => m.name !== group).map((m) => (
                      <Chip key={m.name} on={measures.includes(m.name)} onClick={() => setMeasures(measures.includes(m.name) ? measures.filter((x) => x !== m.name) : [...measures, m.name])}>{m.label || m.name}</Chip>
                    ))}
                  </div>
                </div>
                {chosen.length > 2 && <p className="flex items-center gap-1.5 text-[13px] text-muted"><Users className="size-4" /> {chosen.length} groups: one overall test per measure, then corrected pairwise comparisons.</p>}
              </>
            )
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="First measurement">{(id) => <Select id={id} value={var1} onChange={(e) => setVar1(e.target.value)}>{measuresAll.map((m) => <option key={m.name} value={m.name}>{m.label || m.name}</option>)}</Select>}</Field>
              <Field label="Second measurement">{(id) => <Select id={id} value={var2} onChange={(e) => setVar2(e.target.value)}>{measuresAll.map((m) => <option key={m.name} value={m.name}>{m.label || m.name}</option>)}</Select>}</Field>
            </div>
          )}

          {question && (
            <div className="rounded-lg border border-accent/30 bg-accent-soft/60 p-4" role="group" aria-label="Clarifying question">
              <p className="text-[14px] font-medium">{question.text}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {question.options.map((o) => (
                  <Button key={o.value} onClick={() => { setRelation(o.value as 'paired' | 'relationship'); run(o.value as 'paired' | 'relationship') }}>{o.label}</Button>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
            <Button variant="primary" size="lg" onClick={() => run()} loading={busy} disabled={!canRun}>
              <GitCompareArrows /> Compare
            </Button>
            <button type="button" onClick={() => setAdvanced(!advanced)} className="flex items-center gap-1 text-[13px] text-muted hover:text-fg" aria-expanded={advanced}>
              Advanced <ChevronDown className={cn('size-4 transition-transform', advanced && 'rotate-180')} />
            </button>
            {advanced && (
              <Select aria-label="Statistical test" className="w-60" value={test} onChange={(e) => setTest(e.target.value)}>
                {testChoices.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            )}
            {busy && <span className="text-[13px] text-muted">Checking assumptions and running the test…</span>}
          </div>
          {busy && <div className="h-1 overflow-hidden rounded-full bg-surface-3"><div className="progress-indeterminate h-full w-1/3 bg-accent" /></div>}
          {error && <Callout tone="danger">{error}</Callout>}
        </div>
      </section>

      {outcome && (
        <section className="animate-in rounded-xl border border-line bg-surface p-5">
          {outcome.plan.explanation && (
            <p className="mb-4 flex gap-2 rounded-md bg-surface-2 p-3 text-[13px] text-fg-2"><Info className="mt-0.5 size-4 shrink-0 text-accent" />{outcome.plan.explanation}</p>
          )}
          <ResultView item={outcome.item} settings={settings} projectId={projectId} />
          <div className="mt-5 flex flex-wrap gap-2 border-t border-line pt-4">
            <Link to={`/p/${projectId}/report`}><Button variant="primary">Add to report <ArrowRight /></Button></Link>
            <Link to={`/p/${projectId}/results?run=${outcome.item.run.id}`}><Button>Open in Results</Button></Link>
          </div>
        </section>
      )}
    </div>
  )
}
