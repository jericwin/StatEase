import { ArrowRight, BarChart3, Database, FileDown, GitBranch, ListChecks, Upload } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { PageBody, PageHeader } from '@/components/layout/AppShell'
import { Badge, Callout, EmptyState, ErrorState, Panel, Skeleton } from '@/components/ui/feedback'
import { useActiveDataset, useProjectId } from '@/lib/active'
import { formatDate, formatP, pluralize, relativeTime } from '@/lib/format'
import { useDataset, useExports, useProject, useResults } from '@/lib/queries'
import { cn } from '@/lib/utils'

function ActionTile({
  to,
  step,
  icon,
  title,
  description,
  status,
  primary,
}: {
  to: string
  step: number
  icon: ReactNode
  title: string
  description: string
  status: ReactNode
  primary?: boolean
}) {
  return (
    <Link
      to={to}
      className={cn(
        'group flex flex-col gap-3 p-5 transition-colors hover:bg-surface-2 focus-visible:z-10',
        primary && 'bg-accent-soft/50',
      )}
    >
      <div className="flex items-center gap-3">
        <span
          className={cn(
            'flex size-9 items-center justify-center rounded-md border [&_svg]:size-[18px]',
            primary ? 'border-accent bg-accent text-accent-fg' : 'border-line-strong bg-surface text-fg-2',
          )}
        >
          {icon}
        </span>
        <div>
          <div className="num text-[11px] font-semibold tracking-wide text-muted uppercase">Step {step}</div>
          <div className="text-[15px] font-semibold">{title}</div>
        </div>
        <ArrowRight className="ml-auto size-4 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-accent" />
      </div>
      <p className="text-[13px] text-muted">{description}</p>
      <div className="mt-auto text-xs text-fg-2">{status}</div>
    </Link>
  )
}

export default function OverviewPage() {
  const pid = useProjectId()
  const project = useProject(pid)
  const { datasetId, datasets, query } = useActiveDataset(pid)
  const dataset = useDataset(datasetId)
  const results = useResults(pid)
  const exports = useExports(pid)

  if (project.isError) return <PageBody><ErrorState error={project.error} /></PageBody>
  const p = project.data
  const completed = (results.data?.items ?? []).filter((r) => r.run.status === 'completed')
  const hasData = datasets.length > 0
  const nextStep = !hasData ? 1 : completed.length === 0 ? 2 : 3

  return (
    <>
      <PageHeader
        breadcrumb={<Link to="/app/projects" className="hover:underline">Projects</Link>}
        title={p?.name ?? <Skeleton className="h-6 w-64" />}
        description={p?.description ?? undefined}
        actions={p?.is_demo && <Badge tone="warning">Synthetic demo data</Badge>}
      />
      <PageBody className="space-y-5">
        <div className="grid divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface md:grid-cols-3 md:divide-x md:divide-y-0">
          <ActionTile
            to={`/p/${pid}/import`}
            step={1}
            icon={<Upload />}
            title="Import data"
            description="Upload Excel, CSV, TSV, JSON or Parquet. Column types are detected automatically."
            status={hasData ? `${pluralize(datasets.length, 'dataset')} imported` : 'No data yet'}
            primary={nextStep === 1}
          />
          <ActionTile
            to={`/p/${pid}/analyze`}
            step={2}
            icon={<ListChecks />}
            title="Analyze data"
            description="Review recommended analyses for your variables, or choose tests from the checklist."
            status={`${pluralize(p?.counts.analyses ?? 0, 'analysis', 'analyses')} configured · ${pluralize(completed.length, 'result')}`}
            primary={nextStep === 2}
          />
          <ActionTile
            to={`/p/${pid}/report`}
            step={3}
            icon={<FileDown />}
            title="Build report"
            description="Organise results by objective, edit tables and charts, download Word or Excel."
            status={`${pluralize(exports.data?.total ?? 0, 'export')} generated`}
            primary={nextStep === 3}
          />
        </div>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
          <Panel
            title="Datasets"
            bodyClassName="p-0"
            actions={
              <Link to={`/p/${pid}/import`} className="text-[13px] font-medium text-accent hover:underline">
                Import another
              </Link>
            }
          >
            {query.isLoading && <Skeleton className="m-4 h-16" />}
            {query.isSuccess && datasets.length === 0 && (
              <EmptyState
                icon={<Database />}
                title="No data imported"
                description="Import a spreadsheet to begin. The original file is stored unchanged."
              />
            )}
            {datasets.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead className="border-b border-line bg-surface-2 text-left text-xs text-muted">
                    <tr>
                      <th className="px-4 py-2 font-medium">Name</th>
                      <th className="px-4 py-2 text-right font-medium">Rows</th>
                      <th className="px-4 py-2 text-right font-medium">Columns</th>
                      <th className="px-4 py-2 font-medium">Version</th>
                      <th className="px-4 py-2 font-medium">Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {datasets.map((d) => (
                      <tr key={d.id} className="hover:bg-surface-2">
                        <td className="px-4 py-2.5">
                          <Link to={`/p/${pid}/data?dataset=${d.id}`} className="font-medium hover:text-accent hover:underline">
                            {d.name}
                          </Link>
                        </td>
                        <td className="num px-4 py-2.5 text-right">{d.row_count.toLocaleString()}</td>
                        <td className="num px-4 py-2.5 text-right">{d.column_count}</td>
                        <td className="px-4 py-2.5 text-muted">v{d.version.number}</td>
                        <td className="px-4 py-2.5 text-muted">
                          {d.lineage?.sql ? (
                            <span className="inline-flex items-center gap-1">
                              <GitBranch className="size-3.5" /> SQL query
                            </span>
                          ) : (
                            (d.source_filename ?? d.format.toUpperCase())
                          )}
                          <span className="ml-2 text-xs">{formatDate(d.created_at)}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel title="Data quality" description={dataset.data?.name}>
            {!datasetId && <p className="text-[13px] text-muted">Import data to see a quality summary.</p>}
            {dataset.isLoading && <Skeleton className="h-24" />}
            {dataset.data && (
              <div className="space-y-3">
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
                  <Stat label="Rows" value={dataset.data.profile.rows.toLocaleString()} />
                  <Stat label="Variables" value={dataset.data.profile.columns} />
                  <Stat label="Missing values" value={dataset.data.profile.total_missing.toLocaleString()} />
                  <Stat label="Complete rows" value={dataset.data.profile.complete_rows.toLocaleString()} />
                </dl>
                {dataset.data.profile.warnings.length === 0 ? (
                  <Callout tone="success">No data-quality issues were detected.</Callout>
                ) : (
                  <ul className="space-y-1.5 text-[13px]">
                    {dataset.data.profile.warnings.slice(0, 6).map((w, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-warning" aria-hidden />
                        <span className="text-fg-2">{w.message}</span>
                      </li>
                    ))}
                    {dataset.data.profile.warnings.length > 6 && (
                      <li>
                        <Link to={`/p/${pid}/data?tab=quality`} className="text-accent hover:underline">
                          View all {dataset.data.profile.warnings.length} warnings
                        </Link>
                      </li>
                    )}
                  </ul>
                )}
              </div>
            )}
          </Panel>
        </div>

        <Panel
          title="Recent results"
          bodyClassName="p-0"
          actions={
            completed.length > 0 && (
              <Link to={`/p/${pid}/results`} className="text-[13px] font-medium text-accent hover:underline">
                All results
              </Link>
            )
          }
        >
          {completed.length === 0 ? (
            <EmptyState
              icon={<BarChart3 />}
              title="No results yet"
              description={hasData ? 'Open Analyze to run recommended analyses.' : 'Results appear here after you import data and run analyses.'}
            />
          ) : (
            <ul className="divide-y divide-line">
              {completed.slice(0, 8).map((r) => (
                <li key={r.run.id}>
                  <Link to={`/p/${pid}/results?run=${r.run.id}`} className="flex items-center gap-3 px-4 py-2.5 text-[13px] hover:bg-surface-2">
                    <span className="min-w-0 flex-1 truncate">
                      <span className="font-medium">{r.result?.heading || r.result?.plain_title}</span>
                      <span className="ml-2 text-muted">{r.result?.title}</span>
                    </span>
                    {typeof r.result?.summary.p === 'number' && (
                      <span className="num text-xs text-muted">p {formatP(r.result.summary.p, 'apa').startsWith('<') ? '' : '= '}{formatP(r.result.summary.p)}</span>
                    )}
                    <span className="hidden text-xs text-muted sm:inline">{r.run.completed_at && relativeTime(r.run.completed_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </PageBody>
    </>
  )
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="num text-[15px] font-semibold">{value}</dd>
    </div>
  )
}
