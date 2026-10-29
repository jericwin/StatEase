import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Copy, Info, RotateCcw, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge, Callout, Tabs, TabsContent, TabsList, TabsTrigger, useToast } from '@/components/ui/feedback'
import { SegmentedControl, Textarea } from '@/components/ui/form'
import { api, errorMessage } from '@/lib/api'
import { formatP, type PStyle } from '@/lib/format'
import type { AnalysisResult, Assumption, ProjectSettings, ResultItem } from '@/lib/types'
import { asArray, cn } from '@/lib/utils'
import { ChartView } from './ChartView'
import { StatTable } from './StatTable'

const KIND_ORDER = ['descriptives', 'frequencies', 'main', 'effect', 'posthoc', 'assumptions'] as const

export function ResultView({ item, settings, projectId }: { item: ResultItem; settings: ProjectSettings; projectId: number }) {
  const r = item.result
  const [level, setLevel] = useState<'plain' | 'technical'>('plain')
  if (!r) {
    return (
      <Callout tone="danger" title="This analysis could not be completed">
        {item.run.error_message}
        {item.run.summary?.suggestion && <span className="mt-1 block">Suggestion: {item.run.summary.suggestion}</span>}
      </Callout>
    )
  }
  const style = settings.p_style as PStyle
  const d = settings.decimals
  const alpha = r.settings.alpha
  const tables = [...r.tables].sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind))
  const main = tables.filter((t) => t.kind === 'main')
  const desc = tables.filter((t) => t.kind === 'descriptives' || t.kind === 'frequencies')
  const posthoc = tables.filter((t) => t.kind === 'posthoc')
  const effect = tables.filter((t) => t.kind === 'effect')
  const assumptionTables = tables.filter((t) => t.kind === 'assumptions')
  const violated = r.assumptions.filter((a) => a.status === 'violated').length
  let tableNo = 0
  const num = () => ++tableNo

  return (
    <article className="min-w-0 space-y-4" aria-labelledby={`result-${item.run.id}`}>
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
          <span>{r.title}</span>
          {r.n !== null && <span className="num">· N = {r.n.toLocaleString()}</span>}
          {r.missing?.excluded ? <span className="num">· {r.missing.excluded.toLocaleString()} excluded (missing)</span> : null}
        </div>
        <h2 id={`result-${item.run.id}`} className="text-[17px] font-semibold">{r.heading || r.plain_title}</h2>
        {r.heading && <p className="-mt-1 text-[13px] text-muted">{r.plain_title}</p>}
        <VariableLine result={r} />
        <KeyFinding result={r} style={style} />
      </header>

      {r.warnings.length > 0 && (
        <div className="space-y-2">
          {r.warnings.map((w) => <Callout key={w} tone="warning">{w}</Callout>)}
        </div>
      )}

      <Tabs defaultValue="summary">
        <TabsList>
          <TabsTrigger value="summary">Summary</TabsTrigger>
          {desc.length > 0 && <TabsTrigger value="descriptives" count={desc.length}>Descriptives</TabsTrigger>}
          <TabsTrigger value="main">Test results</TabsTrigger>
          <TabsTrigger value="assumptions" count={violated || undefined}>Assumptions</TabsTrigger>
          {posthoc.length > 0 && <TabsTrigger value="posthoc">Post hoc</TabsTrigger>}
          {r.charts.length > 0 && <TabsTrigger value="charts" count={r.charts.length}>Charts</TabsTrigger>}
          <TabsTrigger value="interpretation">Interpretation</TabsTrigger>
          <TabsTrigger value="method">Method & code</TabsTrigger>
        </TabsList>

        <TabsContent value="summary" className="space-y-5 pt-4">
          <div className="rounded-md border border-line bg-surface-2 p-4">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="label-caps">What the results show</h3>
              <SegmentedControl
                size="sm"
                label="Interpretation detail"
                value={level}
                onChange={setLevel}
                options={[
                  { value: 'plain', label: 'Plain' },
                  { value: 'technical', label: 'Technical' },
                ]}
              />
            </div>
            <p className="text-[13.5px] leading-relaxed">{level === 'plain' ? r.interpretation.plain : r.interpretation.technical}</p>
            {item.edited_interpretation && <p className="mt-2 text-xs text-muted">An edited version of this text will be used in exports (see Interpretation).</p>}
          </div>
          {(main.length ? main.slice(0, 2) : desc.slice(0, 3)).map((t) => <StatTable key={t.id} table={t} decimals={d} style={style} alpha={alpha} />)}
          {effect.map((t) => <StatTable key={t.id} table={t} decimals={d} style={style} alpha={alpha} />)}
          {r.notes.length > 0 && (
            <ul className="space-y-1 text-xs text-muted">
              {r.notes.map((n) => <li key={n} className="flex gap-1.5"><Info className="mt-px size-3.5 shrink-0" />{n}</li>)}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="descriptives" className="space-y-6 pt-4">
          {desc.map((t) => <StatTable key={t.id} table={t} decimals={d} style={style} alpha={alpha} number={num()} />)}
        </TabsContent>

        <TabsContent value="main" className="space-y-6 pt-4">
          {[...main, ...effect].map((t) => <StatTable key={t.id} table={t} decimals={d} style={style} alpha={alpha} number={num()} />)}
          <p className="text-xs text-muted">Significance level α = {alpha}. p-values below .001 are shown as {formatP(0.0001, style)}.</p>
        </TabsContent>

        <TabsContent value="assumptions" className="space-y-4 pt-4">
          {r.assumptions.length === 0 ? <p className="text-[13px] text-muted">No assumption checks apply to this analysis.</p> : <AssumptionList items={r.assumptions} />}
          {assumptionTables.map((t) => <StatTable key={t.id} table={t} decimals={d} style={style} alpha={alpha} />)}
          <p className="text-xs text-muted">
            Statistical tests of assumptions are one piece of evidence. With large samples they flag trivial departures; with small samples they
            miss real ones. Inspect the plots and consider the study design.
          </p>
        </TabsContent>

        <TabsContent value="posthoc" className="space-y-6 pt-4">
          {posthoc.map((t) => <StatTable key={t.id} table={t} decimals={d} style={style} alpha={alpha} number={num()} />)}
        </TabsContent>

        <TabsContent value="charts" className="pt-4">
          <div className="grid gap-4 2xl:grid-cols-2">
            {r.charts.map((c, i) => <ChartView key={c.id} spec={c} number={i + 1} />)}
          </div>
        </TabsContent>

        <TabsContent value="interpretation" className="pt-4">
          <InterpretationEditor item={item} projectId={projectId} />
        </TabsContent>

        <TabsContent value="method" className="space-y-4 pt-4">
          <MethodPanel result={r} />
        </TabsContent>
      </Tabs>
    </article>
  )
}

function VariableLine({ result }: { result: AnalysisResult }) {
  const entries = Object.entries(result.variables).filter(([, v]) => asArray(v as string | string[]).length)
  if (!entries.length) return null
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
      {entries.map(([k, v]) => (
        <span key={k}>
          <span className="text-muted">{(k.charAt(0).toUpperCase() + k.slice(1)).replace(/_/g, ' ')}: </span>
          <span className="text-fg-2">{asArray(v as string | string[]).join(', ')}</span>
        </span>
      ))}
    </div>
  )
}

function KeyFinding({ result, style }: { result: AnalysisResult; style: PStyle }) {
  const s = result.summary
  if (s.p === undefined && s.effect === undefined) return null
  const sig = s.significant
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-md border border-line bg-surface px-3 py-2 text-[13px]">
      {sig !== undefined && sig !== null && (
        <span className={cn('inline-flex items-center gap-1.5 font-medium', sig ? 'text-success' : 'text-fg-2')}>
          {sig ? <CheckCircle2 className="size-4" /> : <Info className="size-4" />}
          {sig ? 'Statistically significant' : 'Not statistically significant'}
          <span className="font-normal text-muted">(α = {result.settings.alpha})</span>
        </span>
      )}
      {typeof s.p === 'number' && <span className="num">{formatP(s.p, style, true)}</span>}
      {typeof s.effect === 'number' && s.effect_name && (
        <span className="num">
          {s.effect_name} = {s.effect.toFixed(3)}
        </span>
      )}
    </div>
  )
}

const ASSUMPTION_ICON = {
  ok: { icon: CheckCircle2, cls: 'text-success', label: 'Met' },
  warning: { icon: AlertTriangle, cls: 'text-warning', label: 'Caution' },
  violated: { icon: XCircle, cls: 'text-danger', label: 'Not met' },
  info: { icon: Info, cls: 'text-muted', label: 'Note' },
}

export function AssumptionList({ items }: { items: Assumption[] }) {
  return (
    <ul className="divide-y divide-line rounded-md border border-line bg-surface">
      {items.map((a, i) => {
        const m = ASSUMPTION_ICON[a.status]
        const Icon = m.icon
        return (
          <li key={i} className="flex gap-3 px-3 py-2.5 text-[13px]">
            <Icon className={cn('mt-0.5 size-4 shrink-0', m.cls)} aria-hidden />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{a.name}</span>
                <Badge tone={a.status === 'ok' ? 'success' : a.status === 'violated' ? 'danger' : a.status === 'warning' ? 'warning' : 'neutral'}>{m.label}</Badge>
              </div>
              <p className="mt-0.5 text-fg-2">{a.message}</p>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function InterpretationEditor({ item, projectId }: { item: ResultItem; projectId: number }) {
  const r = item.result!
  const [text, setText] = useState(item.edited_interpretation ?? r.interpretation.technical)
  const qc = useQueryClient()
  const toast = useToast()
  const save = useMutation({
    mutationFn: (value: string | null) => api.put(`/analyses/runs/${item.run.id}/interpretation`, { text: value }),
    onSuccess: (_d, value) => {
      qc.invalidateQueries({ queryKey: ['results', projectId] })
      toast('success', value ? 'Interpretation saved. It will be used in exports.' : 'Restored the generated interpretation.')
    },
    onError: (e) => toast('danger', errorMessage(e)),
  })
  return (
    <div className="space-y-3">
      <Callout tone="info">
        The generated text is built from the computed statistics. You can edit it for your report; the numbers in tables are not affected.
      </Callout>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-md border border-line bg-surface-2 p-3 text-[13px]">
          <div className="label-caps mb-1">Plain language</div>
          <p>{r.interpretation.plain}</p>
        </div>
        <div className="rounded-md border border-line bg-surface-2 p-3 text-[13px]">
          <div className="label-caps mb-1">Technical (APA-style)</div>
          <p>{r.interpretation.technical}</p>
        </div>
      </div>
      <label htmlFor={`interp-${item.run.id}`} className="block text-[13px] font-medium">Text for the report</label>
      <Textarea id={`interp-${item.run.id}`} value={text} onChange={(e) => setText(e.target.value)} rows={6} />
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" onClick={() => save.mutate(text)} loading={save.isPending}>Save edited text</Button>
        <Button onClick={() => setText(r.interpretation.plain)}>Use plain version</Button>
        <Button
          variant="ghost"
          onClick={() => {
            setText(r.interpretation.technical)
            save.mutate(null)
          }}
        >
          <RotateCcw /> Restore generated
        </Button>
      </div>
    </div>
  )
}

function MethodPanel({ result }: { result: AnalysisResult }) {
  const m = result.method
  return (
    <>
      <section className="space-y-2 text-[13px]">
        <h3 className="label-caps">Calculation method</h3>
        <p>{m.description}</p>
        <h3 className="label-caps pt-2">Missing data</h3>
        <p>{m.missing_data}</p>
        {m.assumptions.length > 0 && (
          <>
            <h3 className="label-caps pt-2">Assumptions</h3>
            <ul className="list-disc space-y-0.5 pl-5">{m.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
          </>
        )}
        {m.limitations.length > 0 && (
          <>
            <h3 className="label-caps pt-2">Limitations</h3>
            <ul className="list-disc space-y-0.5 pl-5">{m.limitations.map((a) => <li key={a}>{a}</li>)}</ul>
          </>
        )}
        {m.references.length > 0 && (
          <>
            <h3 className="label-caps pt-2">References</h3>
            <ul className="space-y-0.5 text-xs text-fg-2">{m.references.map((a) => <li key={a}>{a}</li>)}</ul>
          </>
        )}
        <h3 className="label-caps pt-2">Settings used</h3>
        <pre className="overflow-x-auto rounded-md bg-surface-3 p-2 font-mono text-xs">{JSON.stringify({ variables: result.variables, options: result.options, alpha: result.settings.alpha, dataset_version: result.dataset_version_id }, null, 2)}</pre>
      </section>
      {result.code && (
        <section>
          <div className="mb-1 flex items-center justify-between">
            <h3 className="label-caps">Reproducible Python code</h3>
            <Button size="sm" variant="ghost" onClick={() => navigator.clipboard.writeText(result.code!)}><Copy /> Copy</Button>
          </div>
          <pre className="scroll-thin max-h-96 overflow-auto rounded-md bg-surface-3 p-3 font-mono text-xs leading-relaxed">{result.code}</pre>
          <p className="mt-1 text-xs text-muted">Generated from the exact settings above; it calls the same SciPy/statsmodels/pingouin functions as the engine.</p>
        </section>
      )}
    </>
  )
}
