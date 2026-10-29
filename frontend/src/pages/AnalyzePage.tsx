import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Check, ChevronDown, ListChecks, Play, Plus } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { DatasetPicker } from '@/components/DatasetPicker'
import { PageBody, PageHeader } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Badge, Callout, EmptyState, ErrorState, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger, useToast } from '@/components/ui/feedback'
import { Checkbox, SegmentedControl } from '@/components/ui/form'
import { Dialog } from '@/components/ui/overlay'
import { ComparePanel } from '@/features/analysis/ComparePanel'
import { ConfigCard } from '@/features/analysis/ConfigCard'
import { useActiveDataset, useProjectId } from '@/lib/active'
import { api, errorMessage } from '@/lib/api'
import { keys, useCatalog, useConfigs, useDataset, useProject, useRecommendations } from '@/lib/queries'
import type { AnalysisSpec, Assignment, Configuration, Dataset, Recommendation, Run } from '@/lib/types'
import { asArray, cn, storageGet, storageSet, useMediaQuery } from '@/lib/utils'

export default function AnalyzePage() {
  const pid = useProjectId()
  const project = useProject(pid)
  const [params, setParams] = useSearchParams()
  const category = params.get('category')
  const { datasetId, setDatasetId, datasets, query: dsQuery } = useActiveDataset(pid)
  const dataset = useDataset(datasetId)
  const catalog = useCatalog()
  const configs = useConfigs(pid)
  const recs = useRecommendations(datasetId)
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [expanded, setExpanded] = useState<number | null>(null)
  const [technical, setTechnical] = useState(() => storageGet('statease.technical', '0') === '1')
  const [confirmRun, setConfirmRun] = useState<number[] | null>(null)
  const [batch, setBatch] = useState<number[] | null>(null)
  const [mobileTab, setMobileTab] = useState(category ? 'choose' : (params.get('tab') ?? 'recommended'))
  const wide = useMediaQuery('(min-width: 1280px)')

  const specs = useMemo(() => Object.fromEntries((catalog.data?.analyses ?? []).map((a) => [a.id, a])), [catalog.data])
  const allConfigs = configs.data?.items ?? []
  const items = useMemo(() => allConfigs.filter((c) => c.dataset_id === datasetId), [allConfigs, datasetId])

  const invalidate = useCallback(() => {
    qc.invalidateQueries({ queryKey: keys.configs(pid) })
    qc.invalidateQueries({ queryKey: keys.project(pid) })
  }, [qc, pid])

  const create = useMutation({
    mutationFn: (body: { analysis_type: string; variables?: Assignment; options?: Record<string, unknown>; source?: string; rec_key?: string }) =>
      api.post<Configuration>('/analyses/configurations', { project_id: pid, dataset_version_id: dataset.data!.version.id, variables: {}, options: {}, ...body }),
    onSuccess: (c) => {
      invalidate()
      qc.invalidateQueries({ queryKey: keys.recs(datasetId ?? 0) })
      setSelected((s) => new Set(s).add(c.id))
      return c
    },
    onError: (e) => toast('danger', errorMessage(e)),
  })
  const save = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Record<string, unknown> }) => api.patch<Configuration>(`/analyses/configurations/${id}`, patch),
    onSuccess: (c) => qc.setQueryData(keys.configs(pid), (old: { items: Configuration[] } | undefined) => old && { ...old, items: old.items.map((x) => (x.id === c.id ? c : x)) }),
    onError: (e) => toast('danger', errorMessage(e)),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/analyses/configurations/${id}`),
    onSuccess: () => {
      invalidate()
      qc.invalidateQueries({ queryKey: keys.recs(datasetId ?? 0) })
    },
  })
  const duplicate = useMutation({
    mutationFn: (id: number) => api.post<Configuration>(`/analyses/configurations/${id}/duplicate`),
    onSuccess: (c) => {
      invalidate()
      setExpanded(c.id)
      setSelected((s) => new Set(s).add(c.id))
    },
  })
  const runMutation = useMutation({
    mutationFn: (ids: number[]) => api.post<{ items: Run[] }>('/analyses/runs', { configuration_ids: ids, use_latest_version: true }),
    onSuccess: (_r, ids) => {
      setBatch(ids)
      invalidate()
    },
    onError: (e) => toast('danger', errorMessage(e)),
  })

  // Track batch progress through the polled configurations.
  const batchStatus = useMemo(() => {
    if (!batch) return null
    const rows = allConfigs.filter((c) => batch.includes(c.id))
    const done = rows.filter((c) => c.last_run && ['completed', 'failed', 'cancelled'].includes(c.last_run.status)).length
    const failed = rows.filter((c) => c.last_run?.status === 'failed').length
    return { total: batch.length, done, failed }
  }, [batch, allConfigs])
  const notified = useRef(false)
  useEffect(() => {
    if (!batchStatus) {
      notified.current = false
      return
    }
    if (batchStatus.done === batchStatus.total && !notified.current) {
      notified.current = true
      qc.invalidateQueries({ queryKey: ['results', pid] })
      toast(batchStatus.failed ? 'danger' : 'success', batchStatus.failed ? `${batchStatus.failed} of ${batchStatus.total} analyses could not be run. Open them to see why.` : `${batchStatus.total} analys${batchStatus.total === 1 ? 'is' : 'es'} completed.`)
    }
  }, [batchStatus, qc, pid, toast])

  const addRecommendation = async (r: Recommendation, run = false) => {
    if (r.kind === 'transform') {
      try {
        await api.post(`/datasets/${datasetId}/transforms/scale-score`, { items: r.config.variables.items, name: r.config.options.name, method: 'mean' })
        qc.invalidateQueries({ queryKey: keys.dataset(datasetId!) })
        qc.invalidateQueries({ queryKey: keys.recs(datasetId!) })
        toast('success', `Created ${String(r.config.options.name)}. It is now available for analyses.`)
      } catch (e) {
        toast('danger', errorMessage(e))
      }
      return
    }
    const c = await create.mutateAsync({ analysis_type: r.analysis_type, variables: r.config.variables, options: r.config.options, source: 'recommended', rec_key: r.key })
    if (run) runMutation.mutate([c.id])
  }

  const runAllRecommended = async () => {
    const pending = (recs.data?.recommendations ?? []).filter((r) => r.kind === 'analysis' && !r.added)
    const ids: number[] = []
    for (const r of pending) {
      const c = await create.mutateAsync({ analysis_type: r.analysis_type, variables: r.config.variables, options: r.config.options, source: 'recommended', rec_key: r.key })
      ids.push(c.id)
    }
    const existing = items.filter((c) => c.source === 'recommended').map((c) => c.id)
    const all = [...new Set([...ids, ...existing])]
    // Make sure the summary dialog sees every configuration that was just created.
    await qc.refetchQueries({ queryKey: keys.configs(pid) })
    if (all.length) setConfirmRun(all)
  }

  const toggleCatalog = async (spec: AnalysisSpec, on: boolean) => {
    if (on) {
      const c = await create.mutateAsync({ analysis_type: spec.id })
      setExpanded(c.id)
      setMobileTab('choose')
    } else {
      const last = [...items].reverse().find((c) => c.analysis_type === spec.id)
      if (last) remove.mutate(last.id)
    }
  }

  const selectedIds = items.filter((c) => selected.has(c.id)).map((c) => c.id)
  const runnable = selectedIds.filter((id) => (items.find((c) => c.id === id)?.problems.length ?? 0) === 0)

  if (dsQuery.isSuccess && datasets.length === 0)
    return (
      <>
        <PageHeader title="Analyze data" />
        <PageBody>
          <EmptyState icon={<ListChecks />} title="Import data first" description="Recommendations are generated from the variables in your dataset." action={<Link to={`/p/${pid}/import`}><Button variant="primary">Import data</Button></Link>} />
        </PageBody>
      </>
    )

  const ds = dataset.data
  const recommended = <RecommendedList recs={recs} onAdd={addRecommendation} onRunAll={runAllRecommended} busy={create.isPending || runMutation.isPending} technical={technical} dataset={ds} />
  const chooser = (
    <CatalogChecklist
      specs={catalog.data?.analyses ?? []}
      categories={catalog.data?.categories ?? []}
      focus={category}
      counts={items.reduce<Record<string, number>>((m, c) => ({ ...m, [c.analysis_type]: (m[c.analysis_type] ?? 0) + 1 }), {})}
      onToggle={toggleCatalog}
      technical={technical}
      onClearFocus={() => setParams({})}
    />
  )
  const selectedPanel = (
    <SelectedPanel
      items={items}
      specs={specs}
      dataset={ds}
      selected={selected}
      setSelected={setSelected}
      expanded={expanded}
      setExpanded={setExpanded}
      technical={technical}
      onSave={(id, patch) => save.mutate({ id, patch })}
      onRun={(ids) => setConfirmRun(ids)}
      onDuplicate={(id) => duplicate.mutate(id)}
      onRemove={(id) => remove.mutate(id)}
      runnable={runnable}
      selectedIds={selectedIds}
      batchStatus={batchStatus}
      onViewResults={() => navigate(`/p/${pid}/results`)}
    />
  )

  return (
    <>
      <PageHeader
        breadcrumb={<Link to={`/p/${pid}`} className="hover:underline">{project.data?.name ?? 'Project'}</Link>}
        title="Analyze data"
        description={ds ? `${ds.name} · ${ds.row_count.toLocaleString()} rows · ${ds.variables.length} variables` : undefined}
        actions={
          <>
            <DatasetPicker datasets={datasets} value={datasetId} onChange={setDatasetId} />
            <SegmentedControl
              label="Naming"
              size="sm"
              value={technical ? 'technical' : 'plain'}
              onChange={(v) => {
                setTechnical(v === 'technical')
                storageSet('statease.technical', v === 'technical' ? '1' : '0')
              }}
              options={[
                { value: 'plain', label: 'Plain language' },
                { value: 'technical', label: 'Test names' },
              ]}
            />
          </>
        }
      />
      <PageBody>
        {(catalog.isError || configs.isError) && <ErrorState error={catalog.error ?? configs.error} />}
        <Tabs
          value={mobileTab}
          onValueChange={(v) => {
            setMobileTab(v)
            setParams((p) => { p.set('tab', v); p.delete('category'); return p }, { replace: true })
          }}
        >
          <TabsList className="mb-5">
            <TabsTrigger value="recommended" count={recs.data?.recommendations.length}>Recommended</TabsTrigger>
            <TabsTrigger value="compare">Compare</TabsTrigger>
            <TabsTrigger value="choose" count={items.length || undefined}>Custom</TabsTrigger>
          </TabsList>
          <TabsContent value="recommended">
            {wide ? (
              <div className="grid grid-cols-[minmax(0,1fr)_400px] gap-5">
                <div className="min-w-0">{recommended}</div>
                <aside className="sticky top-4 self-start">{selectedPanel}</aside>
              </div>
            ) : (
              <div className="space-y-6">{recommended}{items.length > 0 && selectedPanel}</div>
            )}
          </TabsContent>
          <TabsContent value="compare">
            {ds && project.data && <ComparePanel key={ds.id} projectId={pid} dataset={ds} settings={project.data.settings} />}
          </TabsContent>
          <TabsContent value="choose">
            {wide ? (
              <div className="grid grid-cols-[minmax(0,1fr)_440px] gap-5">
                <div className="min-w-0">{chooser}</div>
                <aside className="sticky top-4 self-start">{selectedPanel}</aside>
              </div>
            ) : (
              <div className="space-y-6">{chooser}{selectedPanel}</div>
            )}
          </TabsContent>
        </Tabs>
      </PageBody>

      <Dialog
        open={!!confirmRun}
        onOpenChange={(v) => !v && setConfirmRun(null)}
        title={`Run ${confirmRun?.length ?? 0} analys${confirmRun?.length === 1 ? 'is' : 'es'}?`}
        description="Each analysis uses its own variables and settings. Results are saved to the project."
        size="lg"
        footer={
          <>
            <Button onClick={() => setConfirmRun(null)}>Cancel</Button>
            <Button
              variant="primary"
              loading={runMutation.isPending}
              onClick={() => {
                // Skip only analyses known to be incomplete; the server validates every run again.
                const ids = (confirmRun ?? []).filter((id) => (allConfigs.find((c) => c.id === id)?.problems.length ?? 0) === 0)
                if (ids.length) runMutation.mutate(ids)
                setConfirmRun(null)
              }}
            >
              <Play /> Run now
            </Button>
          </>
        }
      >
        <ol className="divide-y divide-line rounded-md border border-line text-[13px]">
          {(confirmRun ?? []).map((id, i) => {
            const c = allConfigs.find((x) => x.id === id)
            if (!c) return null
            const spec = specs[c.analysis_type]
            const vars = Object.entries(c.variables).filter(([, v]) => asArray(v as string | string[]).length)
            return (
              <li key={id} className="flex gap-3 px-3 py-2">
                <span className="num w-5 shrink-0 text-muted">{i + 1}.</span>
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{spec?.name}</div>
                  <div className="text-xs text-muted">
                    {vars.map(([k, v]) => `${spec?.roles.find((r) => r.key === k)?.label ?? k}: ${asArray(v as string | string[]).join(', ')}`).join(' · ')}
                  </div>
                  {c.problems.length > 0 && <div className="mt-0.5 text-xs text-warning">Skipped — {c.problems[0]}</div>}
                </div>
              </li>
            )
          })}
        </ol>
      </Dialog>
    </>
  )
}

function RecommendedList({
  recs,
  onAdd,
  onRunAll,
  busy,
  technical,
  dataset,
}: {
  recs: ReturnType<typeof useRecommendations>
  onAdd: (r: Recommendation, run?: boolean) => void
  onRunAll: () => void
  busy: boolean
  technical: boolean
  dataset?: Dataset
}) {
  const [showAll, setShowAll] = useState(false)
  if (recs.isLoading) return <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-20" />)}</div>
  if (recs.isError) return <ErrorState error={recs.error} retry={() => recs.refetch()} />
  const data = recs.data
  if (!data) return null
  const list = showAll ? data.recommendations : data.recommendations.slice(0, 5)
  const pending = data.recommendations.filter((r) => r.kind === 'analysis' && !r.added).length
  const labelOf = (name: string) => dataset?.variables.find((v) => v.name === name)?.label || name
  return (
    <section aria-labelledby="rec-heading">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="rec-heading" className="text-[15px] font-semibold">Recommended analyses</h2>
          <p className="text-[13px] text-muted">
            Based on {data.summary.numeric} numeric, {data.summary.ordinal} rating and {data.summary.grouping} grouping variables
            {data.summary.scales > 0 && ` and ${data.summary.scales} questionnaire scale(s)`}.
          </p>
        </div>
        <Button variant="primary" onClick={onRunAll} disabled={busy || data.recommendations.length === 0}>
          <Play /> Run all recommended{pending > 0 && ` (${pending} new)`}
        </Button>
      </div>
      {data.excluded.length > 0 && (
        <p className="mb-3 text-xs text-muted">
          Not used automatically: {data.excluded.map((e) => `${e.name} (${e.reason.replace(/[.—].*$/, '').trim().toLowerCase()})`).join(', ')}.
        </p>
      )}
      {data.recommendations.length === 0 ? (
        <Callout tone="info">No automatic recommendations for this dataset. Choose analyses from the list below.</Callout>
      ) : (
        <ul className="space-y-2">
          {list.map((r) => {
            const vars = Object.values(r.config.variables).flatMap((v) => asArray(v as string | string[]))
            return (
              <li key={r.key} className="rounded-md border border-line bg-surface px-4 py-3">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-[13.5px] font-semibold">{r.title}</h3>
                      <Badge tone={r.kind === 'transform' ? 'neutral' : 'accent'}>{technical ? r.technical_name : r.test}</Badge>
                    </div>
                    <p className="mt-0.5 text-[13px] text-fg-2">{r.question}</p>
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {vars.slice(0, 8).map((v) => (
                        <span key={v} className="rounded-[3px] bg-surface-3 px-1.5 py-0.5 text-[11.5px] text-fg-2">{labelOf(v)}</span>
                      ))}
                      {vars.length > 8 && <span className="text-[11.5px] text-muted">+{vars.length - 8} more</span>}
                    </div>
                    <details className="mt-1.5 text-xs text-muted">
                      <summary className="cursor-pointer select-none hover:text-fg">Why this analysis?</summary>
                      <p className="mt-1">{r.why}</p>
                      {r.limitations.map((l) => <p key={l} className="mt-1">• {l}</p>)}
                    </details>
                  </div>
                  <div className="flex shrink-0 gap-1.5">
                    {r.added ? (
                      <Badge tone="success"><Check className="size-3" /> Added</Badge>
                    ) : (
                      <>
                        <Button size="sm" onClick={() => onAdd(r)} disabled={busy}>
                          <Plus /> {r.kind === 'transform' ? 'Create' : 'Add'}
                        </Button>
                        {r.kind === 'analysis' && (
                          <Button size="sm" variant="primary" onClick={() => onAdd(r, true)} disabled={busy}>
                            Run analysis
                          </Button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
      {data.recommendations.length > 5 && (
        <button className="mt-2 text-[13px] font-medium text-accent hover:underline" onClick={() => setShowAll(!showAll)}>
          {showAll ? 'Show fewer' : `Show all ${data.recommendations.length} recommendations`}
        </button>
      )}
    </section>
  )
}

function CatalogChecklist({
  specs,
  categories,
  focus,
  counts,
  onToggle,
  technical,
  onClearFocus,
}: {
  specs: AnalysisSpec[]
  categories: { id: string; name: string; plain: string }[]
  focus: string | null
  counts: Record<string, number>
  onToggle: (s: AnalysisSpec, on: boolean) => void
  technical: boolean
  onClearFocus: () => void
}) {
  const [open, setOpen] = useState<Set<string>>(() => new Set(focus ? [focus] : ['descriptives', 'compare']))
  useEffect(() => {
    if (focus) setOpen(new Set([focus]))
  }, [focus])
  const shown = focus ? categories.filter((c) => c.id === focus) : categories
  return (
    <section aria-labelledby="catalog-heading">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="catalog-heading" className="text-[15px] font-semibold">{focus ? shown[0]?.name : 'Choose analyses'}</h2>
          <p className="text-[13px] text-muted">{focus ? shown[0]?.plain : 'Tick an analysis to add it; then assign variables on the right.'}</p>
        </div>
        {focus && <Button size="sm" variant="ghost" onClick={onClearFocus}>Show all categories <ArrowRight /></Button>}
      </div>
      <div className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
        {shown.map((cat) => {
          const list = specs.filter((s) => s.category === cat.id)
          const isOpen = open.has(cat.id)
          return (
            <div key={cat.id}>
              <button
                type="button"
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-surface-2"
                aria-expanded={isOpen}
                onClick={() => setOpen((s) => { const n = new Set(s); if (n.has(cat.id)) n.delete(cat.id); else n.add(cat.id); return n })}
              >
                <span className="flex-1">
                  <span className="text-[13px] font-semibold">{cat.name}</span>
                  <span className="ml-2 text-xs text-muted">{cat.plain}</span>
                </span>
                <span className="num text-xs text-muted">{list.length}</span>
                <ChevronDown className={cn('size-4 text-muted transition-transform', isOpen && 'rotate-180')} />
              </button>
              {isOpen && (
                <ul className="border-t border-line bg-surface-2/60 px-4 py-1">
                  {list.map((s) => {
                    const n = counts[s.id] ?? 0
                    return (
                      <li key={s.id} className="flex items-start gap-2.5 py-2">
                        <Checkbox checked={n > 0} onCheckedChange={(on) => onToggle(s, on)} className="mt-0.5" aria-label={s.name} />
                        <div className="min-w-0 flex-1 text-[13px]">
                          <div className="flex flex-wrap items-center gap-x-2">
                            <span className="font-medium">{technical ? s.name : s.plain_name}</span>
                            <span className="text-xs text-muted">{technical ? s.plain_name : s.name}</span>
                            {n > 1 && <Badge>{n} configured</Badge>}
                          </div>
                          <p className="text-xs text-muted">{s.description}</p>
                        </div>
                        {n > 0 && (
                          <button className="shrink-0 text-xs font-medium text-accent hover:underline" onClick={() => onToggle(s, true)}>
                            Add another
                          </button>
                        )}
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function SelectedPanel(p: {
  items: Configuration[]
  specs: Record<string, AnalysisSpec>
  dataset?: Dataset
  selected: Set<number>
  setSelected: (s: Set<number>) => void
  expanded: number | null
  setExpanded: (id: number | null) => void
  technical: boolean
  onSave: (id: number, patch: Record<string, unknown>) => void
  onRun: (ids: number[]) => void
  onDuplicate: (id: number) => void
  onRemove: (id: number) => void
  runnable: number[]
  selectedIds: number[]
  batchStatus: { total: number; done: number; failed: number } | null
  onViewResults: () => void
}) {
  const all = p.items.length > 0 && p.items.every((c) => p.selected.has(c.id))
  const some = p.items.some((c) => p.selected.has(c.id))
  const running = p.batchStatus && p.batchStatus.done < p.batchStatus.total
  return (
    <div className="flex max-h-[calc(100dvh-2rem)] flex-col rounded-lg border border-line bg-surface">
      <div className="flex items-center gap-2.5 border-b border-line px-3 py-2.5">
        <Checkbox
          checked={all ? true : some ? 'indeterminate' : false}
          onCheckedChange={(on) => p.setSelected(on ? new Set(p.items.map((c) => c.id)) : new Set())}
          aria-label="Select all analyses"
          disabled={!p.items.length}
        />
        <h2 className="flex-1 text-[13px] font-semibold">Selected analyses <span className="num font-normal text-muted">({p.items.length})</span></h2>
      </div>
      <div className="scroll-thin min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {p.items.length === 0 && (
          <p className="px-2 py-8 text-center text-[13px] text-muted">Add a recommended analysis or tick one from the list. Its settings appear here.</p>
        )}
        {p.dataset &&
          p.items.map((c) => (
            <ConfigCard
              key={c.id}
              config={c}
              spec={p.specs[c.analysis_type]}
              variables={p.dataset!.variables}
              datasetId={p.dataset!.id}
              selected={p.selected.has(c.id)}
              expanded={p.expanded === c.id}
              onSelect={(on) => {
                const n = new Set(p.selected)
                if (on) n.add(c.id)
                else n.delete(c.id)
                p.setSelected(n)
              }}
              onExpand={(on) => p.setExpanded(on ? c.id : null)}
              onSave={(patch) => p.onSave(c.id, patch)}
              onRun={() => p.onRun([c.id])}
              onDuplicate={() => p.onDuplicate(c.id)}
              onRemove={() => p.onRemove(c.id)}
              showTechnical={p.technical}
            />
          ))}
      </div>
      <div className="space-y-2 border-t border-line p-3">
        {p.batchStatus && (
          <div className="text-[13px]" role="status">
            <div className="flex justify-between text-xs text-muted">
              <span>{running ? 'Running analyses…' : `Finished${p.batchStatus.failed ? ` · ${p.batchStatus.failed} failed` : ''}`}</span>
              <span className="num">{p.batchStatus.done} / {p.batchStatus.total}</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-3">
              <div className="h-full bg-accent transition-[width]" style={{ width: `${(p.batchStatus.done / p.batchStatus.total) * 100}%` }} />
            </div>
          </div>
        )}
        <div className="flex gap-2">
          <Button variant="primary" className="flex-1 justify-center" disabled={p.runnable.length === 0 || !!running} onClick={() => p.onRun(p.selectedIds)}>
            <Play /> Run selected ({p.runnable.length})
          </Button>
          {p.batchStatus && !running && (
            <Button onClick={p.onViewResults}>
              View results <ArrowRight />
            </Button>
          )}
        </div>
        {p.selectedIds.length > p.runnable.length && (
          <p className="text-xs text-warning">{p.selectedIds.length - p.runnable.length} selected analysis(es) still need variables.</p>
        )}
      </div>
    </div>
  )
}
