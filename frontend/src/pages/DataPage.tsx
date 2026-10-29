import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Calculator, Download, GitBranch, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { DatasetPicker } from '@/components/DatasetPicker'
import { PageBody, PageHeader } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Badge, Callout, EmptyState, ErrorState, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger, useToast } from '@/components/ui/feedback'
import { CheckRow, Field, Input, Select } from '@/components/ui/form'
import { ActionMenu } from '@/components/ui/menu'
import { ConfirmDialog, Dialog } from '@/components/ui/overlay'
import { DataGrid } from '@/features/DataGrid'
import { VariableEditor } from '@/features/VariableEditor'
import { useActiveDataset, useProjectId } from '@/lib/active'
import { api, download, errorMessage } from '@/lib/api'
import { formatDateTime, LEVEL_LABEL } from '@/lib/format'
import { keys, useDataset, useProject } from '@/lib/queries'
import type { Dataset } from '@/lib/types'

export default function DataPage() {
  const pid = useProjectId()
  const project = useProject(pid)
  const [params, setParams] = useSearchParams()
  const { datasetId, setDatasetId, datasets, query } = useActiveDataset(pid)
  const requested = Number(params.get('dataset') ?? 0)
  useEffect(() => {
    if (requested && requested !== datasetId && datasets.some((d) => d.id === requested)) setDatasetId(requested)
  }, [requested, datasetId, datasets, setDatasetId])
  const dataset = useDataset(datasetId)
  const tab = params.get('tab') ?? 'data'
  const [scaleOpen, setScaleOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const remove = useMutation({
    mutationFn: () => api.del(`/datasets/${datasetId}`),
    onSuccess: () => {
      setDeleting(false)
      qc.invalidateQueries({ queryKey: keys.datasets(pid) })
      toast('success', 'Dataset deleted.')
      navigate(`/p/${pid}`)
    },
    onError: (e) => toast('danger', errorMessage(e)),
  })

  const ds = dataset.data
  return (
    <>
      <PageHeader
        breadcrumb={<Link to={`/p/${pid}`} className="hover:underline">{project.data?.name ?? 'Project'}</Link>}
        title="Data explorer"
        description={ds ? `${ds.name} · ${ds.row_count.toLocaleString()} rows × ${ds.column_count} variables · version ${ds.version.number}` : undefined}
        actions={
          ds && (
            <>
              <DatasetPicker datasets={datasets} value={datasetId} onChange={setDatasetId} />
              <Button onClick={() => setScaleOpen(true)}>
                <Calculator /> Compute scale score
              </Button>
              <ActionMenu
                label="Dataset actions"
                actions={[
                  { label: 'Download CSV', icon: <Download />, onSelect: () => download(`/datasets/${ds.id}/download?format=csv`) },
                  { label: 'Download Parquet', icon: <Download />, onSelect: () => download(`/datasets/${ds.id}/download?format=parquet`) },
                  ...(ds.source_filename && !ds.lineage?.sql
                    ? [{ label: 'Download original file', icon: <Download />, onSelect: () => download(`/datasets/${ds.id}/download?format=original`) }]
                    : []),
                  'separator' as const,
                  { label: 'Delete dataset…', icon: <Trash2 />, danger: true, onSelect: () => setDeleting(true) },
                ]}
              />
            </>
          )
        }
      />
      <PageBody>
        {query.isSuccess && datasets.length === 0 && (
          <EmptyState title="No datasets in this project" description="Import a file to explore it here." action={<Link to={`/p/${pid}/import`}><Button variant="primary">Import data</Button></Link>} />
        )}
        {dataset.isError && <ErrorState error={dataset.error} retry={() => dataset.refetch()} />}
        {dataset.isLoading && <Skeleton className="h-96" />}
        {ds && (
          <Tabs value={tab} onValueChange={(v) => setParams((p) => { p.set('tab', v); return p }, { replace: true })}>
            <TabsList className="mb-4">
              <TabsTrigger value="data">Data</TabsTrigger>
              <TabsTrigger value="variables" count={ds.variables.length}>Variables</TabsTrigger>
              <TabsTrigger value="quality" count={ds.profile.warnings.length}>Data quality</TabsTrigger>
              <TabsTrigger value="history" count={ds.versions.length}>Versions & lineage</TabsTrigger>
            </TabsList>
            <TabsContent value="data">
              <DataGrid key={`${ds.id}-${ds.version.id}`} datasetId={ds.id} versionId={ds.version.id} variables={ds.variables} />
            </TabsContent>
            <TabsContent value="variables">
              <VariableEditor dataset={ds} />
            </TabsContent>
            <TabsContent value="quality">
              <QualityTab dataset={ds} />
            </TabsContent>
            <TabsContent value="history">
              <HistoryTab dataset={ds} />
            </TabsContent>
          </Tabs>
        )}
      </PageBody>
      {ds && scaleOpen && <ScaleScoreDialog dataset={ds} onClose={() => setScaleOpen(false)} />}
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        danger
        title="Delete dataset?"
        confirmLabel="Delete dataset"
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
        description="All versions of this dataset and the analyses that use it will be deleted. The original upload is removed as well."
      />
    </>
  )
}

function QualityTab({ dataset }: { dataset: Dataset }) {
  const p = dataset.profile
  const stats: [string, string][] = [
    ['Rows', p.rows.toLocaleString()],
    ['Variables', String(p.columns)],
    ['Missing cells', p.total_missing.toLocaleString()],
    ['Complete rows', `${p.complete_rows.toLocaleString()} (${p.rows ? ((p.complete_rows / p.rows) * 100).toFixed(1) : 0}%)`],
    ['Duplicate rows', p.duplicate_rows.toLocaleString()],
  ]
  const missing = dataset.variables.filter((v) => (v.profile.missing ?? 0) > 0).sort((a, b) => (b.profile.missing ?? 0) - (a.profile.missing ?? 0))
  return (
    <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      <div className="rounded-lg border border-line bg-surface">
        <dl className="divide-y divide-line text-[13px]">
          {stats.map(([k, v]) => (
            <div key={k} className="flex justify-between px-4 py-2.5">
              <dt className="text-muted">{k}</dt>
              <dd className="num font-medium">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="space-y-4">
        {p.warnings.length === 0 ? (
          <Callout tone="success">No data-quality issues were detected.</Callout>
        ) : (
          <div className="space-y-2">
            {p.warnings.map((w, i) => (
              <Callout key={i} tone="warning">{w.message}</Callout>
            ))}
          </div>
        )}
        <div className="rounded-lg border border-line bg-surface">
          <div className="border-b border-line px-4 py-2.5 text-[13px] font-semibold">Missing values by variable</div>
          {missing.length === 0 ? (
            <p className="px-4 py-3 text-[13px] text-muted">No variable has missing values.</p>
          ) : (
            <ul className="divide-y divide-line">
              {missing.map((v) => (
                <li key={v.name} className="flex items-center gap-3 px-4 py-2 text-[13px]">
                  <span className="w-40 shrink-0 truncate sm:w-56">{v.name}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3" aria-hidden>
                    <div className="h-full bg-warning" style={{ width: `${Math.min(100, v.profile.missing_pct ?? 0)}%` }} />
                  </div>
                  <span className="num w-28 shrink-0 text-right text-muted">
                    {v.profile.missing} ({(v.profile.missing_pct ?? 0).toFixed(1)}%)
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="border-t border-line px-4 py-2 text-xs text-muted">
            Analyses exclude missing values listwise for the variables involved and always report how many cases were excluded.
          </p>
        </div>
      </div>
    </div>
  )
}

function HistoryTab({ dataset }: { dataset: Dataset }) {
  const lineage = dataset.lineage
  return (
    <div className="space-y-4">
      {lineage?.sql && (
        <Callout tone="info" title="Derived from a SQL query">
          <pre className="mt-1 overflow-x-auto rounded bg-surface-3 p-2 font-mono text-xs">{lineage.sql}</pre>
          {dataset.parent_version_id && <p className="mt-1 text-xs">Source dataset version id {dataset.parent_version_id}.</p>}
        </Callout>
      )}
      {lineage?.synthetic && <Callout tone="warning">This dataset is synthetic demonstration data.</Callout>}
      <div className="overflow-hidden rounded-lg border border-line bg-surface">
        <table className="w-full text-[13px]">
          <thead className="border-b border-line bg-surface-2 text-left text-xs text-muted">
            <tr>
              <th className="px-4 py-2 font-medium">Version</th>
              <th className="px-4 py-2 font-medium">Change</th>
              <th className="px-4 py-2 text-right font-medium">Rows</th>
              <th className="px-4 py-2 font-medium">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {[...dataset.versions].reverse().map((v) => (
              <tr key={v.id}>
                <td className="px-4 py-2.5">
                  <span className="inline-flex items-center gap-1.5"><GitBranch className="size-3.5 text-muted" /> v{v.number}</span>
                  {v.id === dataset.version.id && <Badge tone="accent" className="ml-2">Current</Badge>}
                </td>
                <td className="px-4 py-2.5 text-fg-2">{v.note}</td>
                <td className="num px-4 py-2.5 text-right">{v.rows.toLocaleString()}</td>
                <td className="px-4 py-2.5 text-muted">{formatDateTime(v.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">
        Each analysis result records the exact dataset version it used. Earlier versions remain available, so earlier results stay reproducible.
      </p>
    </div>
  )
}

function ScaleScoreDialog({ dataset, onClose }: { dataset: Dataset; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const eligible = dataset.variables.filter((v) => ['numeric', 'ordinal'].includes(v.level) && v.data_type !== 'string')
  const groups = [...new Set(eligible.map((v) => v.scale_group).filter(Boolean))] as string[]
  const [items, setItems] = useState<string[]>(groups[0] ? eligible.filter((v) => v.scale_group === groups[0]).map((v) => v.name) : [])
  const [reverse, setReverse] = useState<string[]>([])
  const [name, setName] = useState(groups[0] ? `${groups[0]}_mean` : '')
  const [method, setMethod] = useState<'mean' | 'sum'>('mean')
  const [error, setError] = useState<string | null>(null)
  const create = useMutation({
    mutationFn: () => api.post<Dataset>(`/datasets/${dataset.id}/transforms/scale-score`, { items, name, method, reverse }),
    onSuccess: (d) => {
      qc.setQueryData(keys.dataset(dataset.id), d)
      qc.invalidateQueries({ queryKey: ['recs'] })
      qc.invalidateQueries({ queryKey: ['datasets'] })
      toast('success', `Added “${name}” as version ${d.version.number}.`)
      onClose()
    },
    onError: (e) => setError(errorMessage(e)),
  })
  return (
    <Dialog
      open
      onOpenChange={(v) => !v && onClose()}
      size="lg"
      title="Compute a scale score"
      description="Averages (or sums) questionnaire items into one variable. A new dataset version is created; the current version is kept."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={() => create.mutate()} loading={create.isPending} disabled={items.length < 2 || !name.trim()}>
            Create variable
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-[1fr_220px]">
        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[13px] font-medium text-fg-2">Items ({items.length} selected)</span>
            {groups.length > 0 && (
              <Select
                aria-label="Select a detected scale"
                className="w-44"
                value=""
                onChange={(e) => {
                  const g = e.target.value
                  setItems(eligible.filter((v) => v.scale_group === g).map((v) => v.name))
                  setName(`${g}_mean`)
                }}
              >
                <option value="">Select detected scale…</option>
                {groups.map((g) => (
                  <option key={g}>{g}</option>
                ))}
              </Select>
            )}
          </div>
          <div className="scroll-thin max-h-72 overflow-y-auto rounded-md border border-line px-3 py-1">
            {eligible.map((v) => (
              <div key={v.name} className="flex items-center justify-between gap-2">
                <CheckRow
                  checked={items.includes(v.name)}
                  onChange={(on) => setItems(on ? [...items, v.name] : items.filter((x) => x !== v.name))}
                  label={v.name}
                  description={LEVEL_LABEL[v.level]}
                />
                {items.includes(v.name) && (
                  <label className="flex items-center gap-1.5 text-xs text-muted">
                    <input
                      type="checkbox"
                      checked={reverse.includes(v.name)}
                      onChange={(e) => setReverse(e.target.checked ? [...reverse, v.name] : reverse.filter((x) => x !== v.name))}
                    />
                    reverse
                  </label>
                )}
              </div>
            ))}
          </div>
        </div>
        <div className="space-y-3">
          <Field label="New variable name">{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
          <Field label="Method">
            {(id) => (
              <Select id={id} value={method} onChange={(e) => setMethod(e.target.value as 'mean' | 'sum')}>
                <option value="mean">Mean of items</option>
                <option value="sum">Sum of items</option>
              </Select>
            )}
          </Field>
          <p className="text-xs text-muted">Rows with any missing item get a missing score. Check reliability before combining items.</p>
        </div>
      </div>
      {error && <Callout tone="danger" className="mt-3">{error}</Callout>}
    </Dialog>
  )
}
