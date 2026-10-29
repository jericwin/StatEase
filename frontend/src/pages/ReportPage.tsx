import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowDown,
  ArrowUp,
  BarChart3,
  Check,
  Copy,
  FileSpreadsheet,
  FileText,
  GripVertical,
  Heading,
  ListChecks,
  Loader2,
  Pencil,
  Plus,
  Table2,
  Trash2,
  Type,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { PageBody, PageHeader } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Badge, Callout, ErrorState, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger, useToast } from '@/components/ui/feedback'
import { Checkbox, CheckRow, Field, Input, Select, Switch } from '@/components/ui/form'
import { ActionMenu } from '@/components/ui/menu'
import { Dialog, Sheet } from '@/components/ui/overlay'
import { BlockEditor, type RebindRequest } from '@/features/report/BlockEditor'
import { ObjectivesStep } from '@/features/report/ObjectivesStep'
import { blockText, numbering, ReportDocument } from '@/features/report/ReportDocument'
import { useProjectId } from '@/lib/active'
import { api, download, errorMessage } from '@/lib/api'
import { useCatalog, useDataset, useProject } from '@/lib/queries'
import type { AnalysisSpec, ExportRecord, Report, ReportBlock } from '@/lib/types'
import { cn, useMediaQuery } from '@/lib/utils'

const uid = () => Math.random().toString(36).slice(2, 12)

export default function ReportPage() {
  const pid = useProjectId()
  const project = useProject(pid)
  const [params, setParams] = useSearchParams()
  const list = useQuery({ queryKey: ['reports', pid], queryFn: () => api.get<{ items: { id: number; title: string; updated_at: string }[] }>('/reports', { project_id: pid }) })
  const items = list.data?.items ?? []
  const wantNew = params.get('new') === '1'
  const reportId = Number(params.get('id') ?? 0) || items[0]?.id

  return (
    <>
      <PageHeader
        breadcrumb={<Link to={`/p/${pid}`} className="hover:underline">{project.data?.name ?? 'Project'}</Link>}
        title="Report"
        description="Organise results by objective, edit tables and charts, then export to Word or Excel."
        actions={
          items.length > 0 && !wantNew && (
            <>
              {items.length > 1 && (
                <Select aria-label="Report" className="w-56" value={reportId} onChange={(e) => setParams({ id: e.target.value })}>
                  {items.map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}
                </Select>
              )}
              <Button onClick={() => setParams({ new: '1' })}><Plus /> New report</Button>
            </>
          )
        }
      />
      <PageBody>
        {list.isLoading && <Skeleton className="h-96" />}
        {list.isError && <ErrorState error={list.error} retry={() => list.refetch()} />}
        {list.isSuccess && (items.length === 0 || wantNew) && (
          <ObjectivesStep projectId={pid} onCancel={items.length ? () => setParams({}) : undefined} onCreated={(r) => setParams({ id: String(r.id) })} />
        )}
        {list.isSuccess && items.length > 0 && !wantNew && reportId && <ReportBuilder key={reportId} reportId={reportId} projectId={pid} />}
      </PageBody>
    </>
  )
}

/* ------------------------------------------------------------------ builder */

const ICON = { heading: Heading, text: Type, table: Table2, chart: BarChart3 }
const SERVER_FIELDS: (keyof ReportBlock)[] = ['missing', 'analysis', 'source_table', 'source_chart', 'resolved', 'resolved_text', 'generated', 'chart_types', 'alternatives']

function ReportBuilder({ reportId, projectId }: { reportId: number; projectId: number }) {
  const qc = useQueryClient()
  const toast = useToast()
  const catalog = useCatalog()
  const wide = useMediaQuery('(min-width: 1180px)')
  const query = useQuery({ queryKey: ['report', reportId], queryFn: () => api.get<Report>(`/reports/${reportId}`) })
  const [report, setReport] = useState<Report | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [saving, setSaving] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [mobileTab, setMobileTab] = useState('checklist')
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [includeData, setIncludeData] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pending = useRef<Partial<Pick<Report, 'title' | 'blocks' | 'options'>>>({})
  const dataset = useDataset(report?.dataset_id ?? undefined)
  const specs = useMemo(() => Object.fromEntries((catalog.data?.analyses ?? []).map((a) => [a.id, a])), [catalog.data]) as Record<string, AnalysisSpec>

  useEffect(() => {
    if (query.data && !report) setReport(query.data)
  }, [query.data, report])

  /** Merge server-computed fields into local blocks without losing local edits. */
  const absorb = useCallback((server: Report, replaceBlocks = false) => {
    setReport((local) => {
      if (!local || replaceBlocks) return server
      const byId = Object.fromEntries(server.blocks.map((b) => [b.id, b]))
      return { ...local, objectives: server.objectives, blocks: local.blocks.map((b) => {
        const s = byId[b.id]
        if (!s) return b
        const merged = { ...b }
        for (const f of SERVER_FIELDS) (merged as Record<string, unknown>)[f] = s[f]
        return merged
      }) }
    })
  }, [])

  const flush = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current)
    const body = pending.current
    if (!Object.keys(body).length) return
    pending.current = {}
    setSaving('saving')
    try {
      const server = await api.put<Report>(`/reports/${reportId}`, body)
      absorb(server)
      setSaving('saved')
      qc.invalidateQueries({ queryKey: ['reports', projectId] })
    } catch (e) {
      setSaving('error')
      toast('danger', errorMessage(e))
    }
  }, [reportId, absorb, qc, projectId, toast])

  const change = (patch: Partial<Pick<Report, 'title' | 'blocks' | 'options'>>) => {
    setReport((r) => (r ? { ...r, ...patch, options: { ...r.options, ...(patch.options ?? {}) } } : r))
    pending.current = { ...pending.current, ...patch, ...(patch.options ? { options: { ...(pending.current.options ?? {}), ...patch.options } } : {}) }
    setSaving('saving')
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(flush, 600)
  }
  useEffect(() => () => { void flush() }, [flush])

  const setBlocks = (blocks: ReportBlock[]) => change({ blocks })
  const updateBlock = (b: ReportBlock) => setBlocks(report!.blocks.map((x) => (x.id === b.id ? b : x)))

  const rebind = useMutation({
    mutationFn: async ({ block, req }: { block: ReportBlock; req: RebindRequest }) => {
      await flush()
      const body = req.chart_id && !req.variables && req.filter === undefined ? { run_id: block.source?.run_id, chart_id: req.chart_id } : req
      return api.post<Report>(`/reports/${reportId}/blocks/${block.id}/rebind`, body)
    },
    onSuccess: (server) => {
      absorb(server, true)
      qc.invalidateQueries({ queryKey: ['results', projectId] })
      toast('success', 'Recalculated from your data.')
    },
    onError: (e) => toast('danger', errorMessage(e)),
  })

  const exportFile = useMutation({
    mutationFn: async (format: 'docx' | 'xlsx') => {
      await flush()
      const e = await api.post<ExportRecord>('/exports', { project_id: projectId, format, report_id: reportId, include_data: format === 'xlsx' && includeData })
      if (e.download_url) await download(e.download_url, { fallbackName: e.filename ?? `report.${format}` })
      return e
    },
    onSuccess: (e) => toast('success', `${e.format === 'docx' ? 'Word' : 'Excel'} file ready: ${e.summary?.tables ?? 0} tables, ${e.summary?.figures ?? 0} figures.`),
    onError: (e) => toast('danger', errorMessage(e)),
  })

  if (query.isLoading || !report) return <Skeleton className="h-96" />
  if (query.isError) return <ErrorState error={query.error} />

  const blocks = report.blocks
  const nums = numbering(blocks)
  const current = blocks.find((b) => b.id === selected) ?? null
  const includedCount = blocks.filter((b) => b.include && !b.missing && b.type !== 'heading').length

  const move = (from: number, to: number) => {
    if (to < 0 || to >= blocks.length || from === to) return
    const next = [...blocks]
    const [b] = next.splice(from, 1)
    next.splice(to, 0, b)
    setBlocks(next)
  }
  const add = (b: Partial<ReportBlock>) => {
    const block = { id: uid(), include: true, ...b } as ReportBlock
    const at = selected ? blocks.findIndex((x) => x.id === selected) + 1 : blocks.length
    const next = [...blocks]
    next.splice(at, 0, block)
    setBlocks(next)
    setSelected(block.id)
  }

  const checklist = (
    <div className="flex flex-col rounded-xl border border-line bg-surface">
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <h2 className="flex items-center gap-2 text-[14px] font-semibold"><ListChecks className="size-4 text-accent" /> Checklist</h2>
        <span className="text-[12px] text-muted">{includedCount} selected</span>
      </div>
      <ul className="scroll-thin max-h-[calc(100dvh-20rem)] min-h-40 overflow-y-auto p-2" aria-label="Report items">
        {blocks.map((b, i) => {
          const Icon = ICON[b.type]
          const isHeading = b.type === 'heading'
          const label = b.type === 'table' || b.type === 'chart' ? `${nums[b.id] ? `${nums[b.id]} · ` : ''}${b.title ?? ''}` : b.type === 'text' ? (b.title && b.title !== 'Interpretation' ? b.title : 'Interpretation') : blockText(b)
          return (
            <li
              key={b.id}
              draggable
              onDragStart={() => setDragIndex(i)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => { if (dragIndex !== null) move(dragIndex, i); setDragIndex(null) }}
              onDragEnd={() => setDragIndex(null)}
              className={cn(
                'group flex items-center gap-1.5 rounded-md px-1.5 py-1.5 text-[13px]',
                isHeading && 'mt-2 first:mt-0',
                selected === b.id ? 'bg-accent-soft' : 'hover:bg-surface-2',
                dragIndex === i && 'opacity-40',
              )}
            >
              <GripVertical className="size-4 shrink-0 cursor-grab text-muted/60" aria-hidden />
              <Checkbox checked={b.include} onCheckedChange={(v) => updateBlock({ ...b, include: v })} aria-label={`Include ${label}`} />
              <button className="flex min-w-0 flex-1 items-center gap-1.5 text-left" onClick={() => setSelected(b.id)}>
                <Icon className={cn('size-3.5 shrink-0', isHeading ? 'text-fg' : 'text-muted')} />
                <span className={cn('truncate', isHeading && 'font-semibold', !b.include && 'text-muted line-through decoration-muted/50')}>{label || 'Untitled'}</span>
                {b.missing && <Badge tone="warning">Missing</Badge>}
              </button>
              <span className="flex shrink-0 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
                <button className="rounded p-0.5 text-muted hover:text-fg disabled:opacity-30" disabled={i === 0} onClick={() => move(i, i - 1)} aria-label="Move up"><ArrowUp className="size-3.5" /></button>
                <button className="rounded p-0.5 text-muted hover:text-fg disabled:opacity-30" disabled={i === blocks.length - 1} onClick={() => move(i, i + 1)} aria-label="Move down"><ArrowDown className="size-3.5" /></button>
                <ActionMenu
                  label={`Actions for ${label}`}
                  trigger={<button className="rounded p-0.5 text-muted hover:text-fg" aria-label={`Actions for ${label}`}><Pencil className="size-3.5" /></button>}
                  actions={[
                    { label: 'Edit', icon: <Pencil />, onSelect: () => setSelected(b.id) },
                    { label: 'Duplicate', icon: <Copy />, onSelect: () => { const copy = { ...JSON.parse(JSON.stringify(b)), id: uid(), title: b.title ? `${b.title} (copy)` : b.title, title_edited: true }; const next = [...blocks]; next.splice(i + 1, 0, copy); setBlocks(next); setSelected(copy.id) } },
                    'separator',
                    { label: 'Delete', icon: <Trash2 />, danger: true, onSelect: () => { setBlocks(blocks.filter((x) => x.id !== b.id)); if (selected === b.id) setSelected(null) } },
                  ]}
                />
              </span>
            </li>
          )
        })}
      </ul>
      <div className="flex flex-wrap gap-1.5 border-t border-line p-2">
        <Button size="sm" variant="ghost" onClick={() => setLibraryOpen(true)}><Plus /> From analysis</Button>
        <Button size="sm" variant="ghost" onClick={() => add({ type: 'heading', text: 'New section' })}><Heading /> Heading</Button>
        <Button size="sm" variant="ghost" onClick={() => add({ type: 'text', text: 'Write your text here.' })}><Type /> Text</Button>
      </div>
    </div>
  )

  const options = (
    <div className="space-y-3 rounded-xl border border-line bg-surface p-4">
      <Field label="Report title">{(id) => <Input id={id} value={report.title} onChange={(e) => change({ title: e.target.value })} />}</Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Style">
          {(id) => (
            <Select id={id} value={report.options.style ?? 'apa'} onChange={(e) => change({ options: { style: e.target.value as 'apa' | 'academic' } })}>
              <option value="apa">APA</option>
              <option value="academic">Academic</option>
            </Select>
          )}
        </Field>
        <Field label="Decimals">
          {(id) => (
            <Select id={id} value={report.options.decimals ?? 2} onChange={(e) => change({ options: { decimals: Number(e.target.value) } })}>
              {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
            </Select>
          )}
        </Field>
      </div>
      <div className="flex items-center justify-between gap-2 text-[13px]">
        <label htmlFor="opt-details">Statistical details <span className="block text-xs text-muted">Test statistic, df, CI, effect size</span></label>
        <Switch id="opt-details" checked={report.options.include_details !== false} onCheckedChange={(v) => change({ options: { include_details: v } })} />
      </div>
      <div className="flex items-center justify-between gap-2 text-[13px]">
        <label htmlFor="opt-methods">Method notes</label>
        <Switch id="opt-methods" checked={report.options.include_methods !== false} onCheckedChange={(v) => change({ options: { include_methods: v } })} />
      </div>
    </div>
  )

  const exportBar = (
    <div className="space-y-2 rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" className="flex-1 justify-center" onClick={() => exportFile.mutate('docx')} loading={exportFile.isPending && exportFile.variables === 'docx'} disabled={exportFile.isPending || includedCount === 0}>
          <FileText /> Word (.docx)
        </Button>
        <Button className="flex-1 justify-center" onClick={() => exportFile.mutate('xlsx')} loading={exportFile.isPending && exportFile.variables === 'xlsx'} disabled={exportFile.isPending || includedCount === 0}>
          <FileSpreadsheet /> Excel (.xlsx)
        </Button>
      </div>
      <CheckRow checked={includeData} onChange={setIncludeData} label="Include raw data in Excel" />
      {exportFile.isPending && (
        <div>
          <p className="text-xs text-muted">Generating and checking the file…</p>
          <div className="mt-1 h-1 overflow-hidden rounded-full bg-surface-3"><div className="progress-indeterminate h-full w-1/3 bg-accent" /></div>
        </div>
      )}
    </div>
  )

  const status = (
    <span className="flex items-center gap-1.5 text-[12px] text-muted" role="status">
      {saving === 'saving' && <><Loader2 className="size-3.5 animate-spin" /> Saving…</>}
      {saving === 'saved' && <><Check className="size-3.5 text-success" /> Saved</>}
      {saving === 'error' && <span className="text-danger">Not saved</span>}
    </span>
  )

  const preview = <ReportDocument report={report} blocks={blocks} selected={selected} onSelect={setSelected} onBlockChange={updateBlock} />
  const editor = current && (
    <BlockEditor
      key={current.id}
      block={current}
      dataset={dataset.data}
      spec={current.analysis ? specs[current.analysis.analysis_type] : undefined}
      onUpdate={updateBlock}
      onRebind={(req) => rebind.mutate({ block: current, req })}
      rebinding={rebind.isPending}
      onClose={() => setSelected(null)}
    />
  )

  return (
    <>
      {report.objectives.some((o) => o.error) && (
        <Callout tone="warning" className="mb-4" title="Some objectives need attention">
          {report.objectives.filter((o) => o.error).map((o) => <span key={o.id} className="block">“{o.text}” — {o.error}</span>)}
        </Callout>
      )}
      {wide ? (
        <div className="grid grid-cols-[340px_minmax(0,1fr)] gap-5">
          <aside className="sticky top-4 space-y-4 self-start">
            {exportBar}
            {checklist}
            {options}
          </aside>
          <div className="min-w-0">
            <div className="mb-2 flex justify-end">{status}</div>
            {preview}
          </div>
        </div>
      ) : (
        <Tabs value={mobileTab} onValueChange={setMobileTab}>
          <div className="mb-4 flex items-center justify-between gap-2">
            <TabsList>
              <TabsTrigger value="checklist">Checklist</TabsTrigger>
              <TabsTrigger value="preview">Preview</TabsTrigger>
              <TabsTrigger value="export">Export</TabsTrigger>
            </TabsList>
            {status}
          </div>
          <TabsContent value="checklist">{checklist}</TabsContent>
          <TabsContent value="preview"><div className="-mx-4 overflow-x-auto sm:mx-0">{preview}</div></TabsContent>
          <TabsContent value="export" className="space-y-4">{exportBar}{options}</TabsContent>
        </Tabs>
      )}
      <Sheet open={!!current} onOpenChange={(v) => !v && setSelected(null)} side="right" title="Edit report item">
        {editor}
      </Sheet>
      {libraryOpen && (
        <LibraryDialog
          reportId={reportId}
          onClose={() => setLibraryOpen(false)}
          onAdd={async (newBlocks) => {
            setLibraryOpen(false)
            const at = selected ? blocks.findIndex((x) => x.id === selected) + 1 : blocks.length
            const next = [...blocks]
            next.splice(at, 0, ...newBlocks)
            pending.current = { ...pending.current, blocks: next }
            setReport({ ...report, blocks: next })
            await flush()
          }}
        />
      )}
    </>
  )
}

function LibraryDialog({ reportId, onClose, onAdd }: { reportId: number; onClose: () => void; onAdd: (b: ReportBlock[]) => void }) {
  const lib = useQuery({
    queryKey: ['report-library', reportId],
    queryFn: () => api.get<{ items: { run_id: number; title: string; heading: string | null; tables: { id: string; title: string; kind: string }[]; charts: { id: string; title: string; type: string }[] }[] }>(`/reports/${reportId}/library`),
  })
  const [picked, setPicked] = useState<Record<string, ReportBlock>>({})
  const toggle = (key: string, block: ReportBlock) => setPicked((p) => {
    const n = { ...p }
    if (n[key]) delete n[key]
    else n[key] = block
    return n
  })
  return (
    <Dialog
      open
      onOpenChange={(v) => !v && onClose()}
      size="lg"
      title="Add from your analyses"
      description="Pick tables and charts from any analysis in this project. They are added after the selected item."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={!Object.keys(picked).length} onClick={() => onAdd(Object.values(picked))}>Add {Object.keys(picked).length || ''}</Button></>}
    >
      {lib.isLoading && <Skeleton className="h-40" />}
      {lib.data?.items.length === 0 && <p className="text-[13px] text-muted">No completed analyses yet. Run one from Analyze first.</p>}
      <div className="space-y-3">
        {lib.data?.items.map((it) => (
          <div key={it.run_id} className="rounded-md border border-line p-3">
            <div className="text-[13.5px] font-medium">{it.heading || it.title}</div>
            <div className="text-xs text-muted">{it.title}</div>
            <div className="mt-2 grid gap-x-4 sm:grid-cols-2">
              {it.tables.map((t) => (
                <CheckRow key={`t${it.run_id}${t.id}`} checked={!!picked[`t${it.run_id}${t.id}`]} label={<><Table2 className="mr-1 inline size-3.5 text-muted" />{t.title}</>}
                  onChange={() => toggle(`t${it.run_id}${t.id}`, { id: uid(), type: 'table', include: true, title: t.title, source: { run_id: it.run_id, table_id: t.id }, edits: {} })} />
              ))}
              {it.charts.map((c) => (
                <CheckRow key={`c${it.run_id}${c.id}`} checked={!!picked[`c${it.run_id}${c.id}`]} label={<><BarChart3 className="mr-1 inline size-3.5 text-muted" />{c.title}</>}
                  onChange={() => toggle(`c${it.run_id}${c.id}`, { id: uid(), type: 'chart', include: true, title: c.title, source: { run_id: it.run_id, chart_id: c.id }, edits: {} })} />
              ))}
              <CheckRow checked={!!picked[`x${it.run_id}`]} label={<><Type className="mr-1 inline size-3.5 text-muted" />Interpretation</>}
                onChange={() => toggle(`x${it.run_id}`, { id: uid(), type: 'text', include: true, title: 'Interpretation', text: null, source: { run_id: it.run_id, field: 'interpretation' } })} />
            </div>
          </div>
        ))}
      </div>
    </Dialog>
  )
}

