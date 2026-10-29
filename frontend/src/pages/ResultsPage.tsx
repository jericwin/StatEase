import { ArrowLeft, BarChart3, FileDown, RefreshCw, XCircle } from 'lucide-react'
import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { PageBody, PageHeader } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/feedback'
import { ResultView } from '@/features/results/ResultView'
import { useProjectId } from '@/lib/active'
import { formatP, relativeTime } from '@/lib/format'
import { useCatalog, useProject, useResults } from '@/lib/queries'
import { cn } from '@/lib/utils'

export default function ResultsPage() {
  const pid = useProjectId()
  const project = useProject(pid)
  const results = useResults(pid)
  const catalog = useCatalog()
  const [params, setParams] = useSearchParams()
  const items = useMemo(() => results.data?.items ?? [], [results.data])
  const runParam = Number(params.get('run') ?? 0)
  const active = items.find((i) => i.run.id === runParam) ?? (runParam ? undefined : items[0])
  const categories = catalog.data?.categories ?? []
  const grouped = useMemo(() => {
    const byCat = new Map<string, typeof items>()
    for (const it of items) {
      const cat = it.result?.category ?? catalog.data?.analyses.find((a) => a.id === it.configuration.analysis_type)?.category ?? 'other'
      byCat.set(cat, [...(byCat.get(cat) ?? []), it])
    }
    return byCat
  }, [items, catalog.data])

  const settings = project.data?.settings ?? { alpha: 0.05, ci_level: 0.95, p_style: 'apa' as const, decimals: 2 }

  return (
    <>
      <PageHeader
        breadcrumb={<Link to={`/p/${pid}`} className="hover:underline">{project.data?.name ?? 'Project'}</Link>}
        title="Results"
        description="The latest result of every analysis in this project. Re-run analyses from Analyze after changing settings."
        actions={
          <>
            <Button onClick={() => results.refetch()} loading={results.isFetching}><RefreshCw /> Refresh</Button>
            <Link to={`/p/${pid}/report`}><Button variant="primary"><FileDown /> Build report</Button></Link>
          </>
        }
      />
      <PageBody>
        {results.isError && <ErrorState error={results.error} retry={() => results.refetch()} />}
        {results.isLoading && <Skeleton className="h-96" />}
        {results.isSuccess && items.length === 0 && (
          <EmptyState icon={<BarChart3 />} title="No results yet" description="Run analyses to see tables, charts and interpretations here." action={<Link to={`/p/${pid}/analyze`}><Button variant="primary">Go to Analyze</Button></Link>} />
        )}
        {items.length > 0 && (
          <div className="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
            <nav aria-label="Results" className={cn('lg:sticky lg:top-4 lg:self-start', runParam && 'hidden lg:block')}>
              <div className="overflow-hidden rounded-lg border border-line bg-surface">
                {[...grouped.entries()].map(([cat, list]) => (
                  <div key={cat}>
                    <div className="label-caps border-b border-line bg-surface-2 px-3 py-1.5">{categories.find((c) => c.id === cat)?.name ?? cat}</div>
                    <ul className="divide-y divide-line">
                      {list.map((it) => {
                        const isActive = active?.run.id === it.run.id
                        const failed = it.run.status === 'failed'
                        return (
                          <li key={it.run.id}>
                            <button
                              type="button"
                              onClick={() => setParams({ run: String(it.run.id) })}
                              aria-current={isActive ? 'true' : undefined}
                              className={cn('block w-full px-3 py-2 text-left text-[13px] hover:bg-surface-2', isActive && 'bg-accent-soft shadow-[inset_2px_0_0_var(--accent)]')}
                            >
                              <div className="flex items-center gap-1.5">
                                {failed && <XCircle className="size-3.5 shrink-0 text-danger" aria-label="Failed" />}
                                <span className="truncate font-medium">{it.result?.heading || it.result?.plain_title || it.configuration.analysis_type}</span>
                              </div>
                              <div className="mt-0.5 flex justify-between gap-2 text-xs text-muted">
                                <span className="truncate">{failed ? 'Could not run' : it.result?.title}</span>
                                {typeof it.result?.summary.p === 'number' && <span className="num shrink-0">{formatP(it.result.summary.p, settings.p_style, true)}</span>}
                              </div>
                            </button>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            </nav>
            <div className={cn('min-w-0', !runParam && 'hidden lg:block')}>
              {runParam > 0 && (
                <button type="button" className="mb-3 flex items-center gap-1 text-[13px] text-accent lg:hidden" onClick={() => setParams({})}>
                  <ArrowLeft className="size-4" /> All results
                </button>
              )}
              {active ? (
                <div className="rounded-lg border border-line bg-surface p-4 sm:p-5">
                  <ResultView key={active.run.id} item={active} settings={settings} projectId={pid} />
                  <p className="mt-6 border-t border-line pt-3 text-xs text-muted">
                    Run #{active.run.id} · {active.run.completed_at && relativeTime(active.run.completed_at)}
                    {active.run.duration_ms !== null && ` · computed in ${Math.round(active.run.duration_ms)} ms`}
                  </p>
                </div>
              ) : (
                <EmptyState title="Result not found" description="It may have been replaced by a newer run." />
              )}
            </div>
            {!runParam && <div className="lg:hidden" />}
          </div>
        )}
      </PageBody>
    </>
  )
}
