import { keymap } from '@codemirror/view'
import { Prec } from '@codemirror/state'
import { MySQL, PostgreSQL, sql, SQLite, StandardSQL } from '@codemirror/lang-sql'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import CodeMirror, { type ReactCodeMirrorRef } from '@uiw/react-codemirror'
import { BookOpen, ChevronRight, Database, Download, Eraser, KeyRound, Link2, PanelLeft, Play, Save, Settings2, Table2, TextCursorInput, Wand2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Badge, Callout, Tabs, TabsContent, TabsList, TabsTrigger, useToast } from '@/components/ui/feedback'
import { Field, Input, SegmentedControl, Select } from '@/components/ui/form'
import { ActionMenu } from '@/components/ui/menu'
import { ConfirmDialog, Dialog, Sheet } from '@/components/ui/overlay'
import { ConnectionsDialog, type Connection } from '@/features/dev/ConnectionsDialog'
import { ResultGrid } from '@/features/dev/ResultGrid'
import { useEditorTheme } from '@/features/dev/useEditorTheme'
import { ApiError, api, download, errorMessage } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { keys, useProjects } from '@/lib/queries'
import type { Dataset } from '@/lib/types'
import { cn, storageGet, storageSet } from '@/lib/utils'

interface SchemaTable {
  name: string
  type: string
  rows: number | null
  dataset_id?: number
  description?: string
  columns: { name: string; type: string; nullable: boolean; primary_key: boolean; level?: string | null }[]
  foreign_keys: { column: string; references: string }[]
}
interface QueryResult {
  columns: { name: string; type: string }[]
  rows: unknown[][]
  truncated: boolean
  row_count: number
  duration_ms: number
  statements: number
  messages: string[]
  max_rows: number
}
interface HistoryItem { id: number; sql: string; status: string; row_count: number | null; duration_ms: number | null; error: string | null; created_at: string }
interface Saved { id: number; name: string; body: string; project_id: number | null; connection_id: number | null }
interface Example { title: string; target: 'sample' | 'workspace'; sql: string }

type Target = { kind: 'project'; id: number } | { kind: 'connection'; id: number }

export default function SqlPage() {
  const projects = useProjects('active')
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const editor = useRef<ReactCodeMirrorRef>(null)
  const editorTheme = useEditorTheme()
  const [target, setTarget] = useState<Target | null>(() => {
    try {
      return JSON.parse(storageGet('statease.sql.target', 'null'))
    } catch {
      return null
    }
  })
  const [code, setCode] = useState(() => storageGet('statease.sql.draft', '-- Write a query, then press Ctrl+Enter to run it\nSELECT 1 AS example;'))
  const [maxRows, setMaxRows] = useState(1000)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState('results')
  const [mode, setMode] = useState<'simple' | 'advanced'>(() => storageGet('statease.sql.mode', 'simple') as 'simple' | 'advanced')
  const [connOpen, setConnOpen] = useState(false)
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveDsOpen, setSaveDsOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [pendingConfirm, setPendingConfirm] = useState<{ sql: string; statements: { type: string; sql: string }[] } | null>(null)
  const [resultsHeight, setResultsHeight] = useState(320)
  const [selectedTable, setSelectedTable] = useState<SchemaTable | null>(null)

  const connections = useQuery({ queryKey: ['sql-connections'], queryFn: () => api.get<{ items: Connection[] }>('/sql/connections') })
  const samples = useQuery({ queryKey: ['sql-samples'], queryFn: () => api.get<{ connection: Connection; examples: Example[] }>('/sql/samples') })
  const effective: Target | null = target ?? (projects.data?.items[0] ? { kind: 'project', id: projects.data.items[0].id } : samples.data ? { kind: 'connection', id: samples.data.connection.id } : null)
  const targetQuery = effective ? (effective.kind === 'project' ? { project_id: effective.id } : { connection_id: effective.id }) : {}
  const schema = useQuery({
    queryKey: ['sql-schema', effective],
    queryFn: () => api.get<{ tables: SchemaTable[]; dialect: string; read_only: boolean; target: string }>('/sql/schema', targetQuery),
    enabled: !!effective,
  })
  const history = useQuery({ queryKey: ['sql-history'], queryFn: () => api.get<{ items: HistoryItem[] }>('/sql/history', { limit: 100 }) })
  const saved = useQuery({ queryKey: ['sql-saved'], queryFn: () => api.get<{ items: Saved[] }>('/sql/saved') })

  useEffect(() => {
    const t = setTimeout(() => storageSet('statease.sql.draft', code), 500)
    return () => clearTimeout(t)
  }, [code])
  const chooseTarget = (t: Target) => {
    setTarget(t)
    storageSet('statease.sql.target', JSON.stringify(t))
    setResult(null)
    setError(null)
  }

  const dialect = schema.data?.dialect
  const language = useMemo(() => {
    const d = dialect === 'postgres' ? PostgreSQL : dialect === 'mysql' ? MySQL : dialect === 'sqlite' ? SQLite : StandardSQL
    const sch: Record<string, string[]> = {}
    for (const t of schema.data?.tables ?? []) sch[t.name] = t.columns.map((c) => c.name)
    return sql({ dialect: d, schema: sch, upperCaseKeywords: true })
  }, [dialect, schema.data])

  const execute = useMutation({
    mutationFn: ({ text, confirm }: { text: string; confirm?: boolean }) => api.post<QueryResult>('/sql/execute', { sql: text, max_rows: maxRows, confirm: !!confirm, ...targetQuery }),
    onSuccess: (r) => {
      setResult(r)
      setError(null)
      setTab(r.columns.length ? 'results' : 'messages')
      qc.invalidateQueries({ queryKey: ['sql-history'] })
      if (r.statements && !r.columns.length) qc.invalidateQueries({ queryKey: ['sql-schema'] })
    },
    onError: (e, vars) => {
      qc.invalidateQueries({ queryKey: ['sql-history'] })
      if (e instanceof ApiError && e.code === 'confirmation_required') {
        setPendingConfirm({ sql: vars.text, statements: ((e.details as { statements?: { type: string; sql: string }[] })?.statements) ?? [] })
        return
      }
      setError(errorMessage(e))
      setTab('messages')
    },
  })

  const selectionOrAll = useCallback((selectionOnly: boolean) => {
    const view = editor.current?.view
    if (!view) return code
    const sel = view.state.selection.main
    if (selectionOnly && !sel.empty) return view.state.sliceDoc(sel.from, sel.to)
    if (selectionOnly) {
      // Run the statement under the cursor (between semicolons).
      const doc = view.state.doc.toString()
      const pos = sel.head
      const start = doc.lastIndexOf(';', pos - 1) + 1
      const endIdx = doc.indexOf(';', pos)
      return doc.slice(start, endIdx === -1 ? doc.length : endIdx + 1)
    }
    return code
  }, [code])

  const run = useCallback((selectionOnly = false) => {
    const text = selectionOrAll(selectionOnly).trim()
    if (!text || !effective) return
    execute.mutate({ text })
  }, [selectionOrAll, effective, execute])

  const format = useCallback(async () => {
    try {
      const r = await api.post<{ sql: string }>('/sql/format', { sql: code, ...(effective?.kind === 'connection' ? { connection_id: effective.id } : {}) })
      setCode(r.sql)
    } catch (e) {
      toast('danger', errorMessage(e))
    }
  }, [code, effective, toast])

  const shortcuts = useMemo(
    () =>
      Prec.highest(
        keymap.of([
          { key: 'Mod-Enter', run: () => { run(false); return true } },
          { key: 'Mod-Shift-Enter', run: () => { run(true); return true } },
          { key: 'Shift-Alt-f', run: () => { format(); return true } },
          { key: 'Mod-s', run: () => { setSaveOpen(true); return true }, preventDefault: true },
        ]),
      ),
    [run, format],
  )

  const exportResult = (fmt: string) =>
    download('/api/v1/sql/export', { method: 'POST', body: { sql: selectionOrAll(false), format: fmt, ...targetQuery }, fallbackName: `query.${fmt}` }).catch((e) => toast('danger', errorMessage(e)))

  const startResize = (e: React.PointerEvent) => {
    const startY = e.clientY
    const startH = resultsHeight
    const move = (ev: PointerEvent) => setResultsHeight(Math.min(window.innerHeight - 200, Math.max(140, startH - (ev.clientY - startY))))
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const targetLabel = effective?.kind === 'project'
    ? `Project: ${projects.data?.items.find((p) => p.id === effective.id)?.name ?? effective.id}`
    : `Connection: ${[...(connections.data?.items ?? []), ...(samples.data ? [samples.data.connection] : [])].find((c) => c.id === effective?.id)?.name ?? ''}`

  const explorer = (
    <Explorer
      projects={projects.data?.items ?? []}
      connections={connections.data?.items ?? []}
      target={effective}
      onTarget={chooseTarget}
      schema={schema.data?.tables ?? []}
      schemaLoading={schema.isLoading}
      schemaError={schema.error}
      saved={saved.data?.items ?? []}
      examples={samples.data?.examples ?? []}
      sampleConnectionId={samples.data?.connection.id}
      onInsert={(s) => setCode(s)}
      onSelectTable={(t) => {
        setSelectedTable(t)
        setTab('schema')
      }}
      onPreview={(t) => {
        const name = /^[A-Za-z_][\w.]*$/.test(t.name) ? t.name : `"${t.name}"`
        const q = `SELECT *\nFROM ${name}\nLIMIT 100;`
        setCode(q)
        execute.mutate({ text: q })
      }}
      onManage={() => setConnOpen(true)}
      mode={mode}
    />
  )

  return (
    <div className="flex h-[calc(100dvh-3rem)] flex-col lg:h-dvh">
      <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface px-3 py-2">
        <Button size="sm" variant="ghost" className="lg:hidden" onClick={() => setSidebarOpen(true)} aria-label="Open schema explorer"><PanelLeft /></Button>
        <h1 className="mr-2 text-[15px] font-semibold">SQL workbench</h1>
        <Button size="sm" variant="primary" onClick={() => run(false)} loading={execute.isPending} title="Run all (Ctrl+Enter)"><Play /> Run</Button>
        <Button size="sm" onClick={() => run(true)} title="Run selection or current statement (Ctrl+Shift+Enter)"><TextCursorInput /> <span className="hidden sm:inline">Run selection</span></Button>
        <Button size="sm" variant="ghost" onClick={format} title="Format SQL (Shift+Alt+F)"><Wand2 /> <span className="hidden sm:inline">Format</span></Button>
        <Button size="sm" variant="ghost" onClick={() => setSaveOpen(true)} title="Save query (Ctrl+S)"><Save /> <span className="hidden sm:inline">Save</span></Button>
        <Button size="sm" variant="ghost" onClick={() => setCode('')} title="Clear editor"><Eraser /> <span className="hidden sm:inline">Clear</span></Button>
        <div className="flex-1" />
        <label className="flex items-center gap-1.5 text-xs text-muted">
          Row limit
          <Select value={maxRows} onChange={(e) => setMaxRows(Number(e.target.value))} className="w-24" aria-label="Row limit">
            {[100, 1000, 5000, 10000].map((n) => <option key={n} value={n}>{n.toLocaleString()}</option>)}
          </Select>
        </label>
        <SegmentedControl size="sm" label="Interface mode" value={mode} onChange={(m) => { setMode(m); storageSet('statease.sql.mode', m) }} options={[{ value: 'simple', label: 'Simple' }, { value: 'advanced', label: 'Advanced' }]} />
      </div>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-72 shrink-0 flex-col border-r border-line bg-surface lg:flex">{explorer}</aside>
        <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen} side="left" title="Schema explorer" className="flex flex-col">{explorer}</Sheet>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="min-h-[140px] flex-1 overflow-hidden">
            <CodeMirror
              ref={editor}
              value={code}
              onChange={setCode}
              height="100%"
              className="h-full"
              theme="none"
              extensions={[language, shortcuts, ...editorTheme]}
              basicSetup={{ foldGutter: false, highlightActiveLine: true, autocompletion: true, indentOnInput: true, bracketMatching: true }}
              aria-label="SQL editor"
            />
          </div>
          <div onPointerDown={startResize} className="h-1.5 shrink-0 cursor-row-resize border-y border-line bg-surface-2 hover:bg-accent/30" role="separator" aria-orientation="horizontal" aria-label="Resize results panel" />
          <div className="flex shrink-0 flex-col bg-surface" style={{ height: resultsHeight }}>
            <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
              <div className="flex items-center gap-2 pr-2">
                <TabsList className="flex-1 border-b-0 px-2">
                  <TabsTrigger value="results" count={result?.row_count}>Results</TabsTrigger>
                  <TabsTrigger value="messages">Messages</TabsTrigger>
                  <TabsTrigger value="history">History</TabsTrigger>
                  {mode === 'advanced' && <TabsTrigger value="schema">Schema</TabsTrigger>}
                  {mode === 'advanced' && <TabsTrigger value="details">Execution details</TabsTrigger>}
                </TabsList>
                {result && result.columns.length > 0 && (
                  <>
                    {effective?.kind === 'project' && (
                      <Button size="sm" onClick={() => setSaveDsOpen(true)}><Table2 /> <span className="hidden sm:inline">Save as dataset</span></Button>
                    )}
                    <ActionMenu
                      label="Export results"
                      trigger={<Button size="sm"><Download /> <span className="hidden sm:inline">Export</span></Button>}
                      actions={['csv', 'xlsx', 'parquet', 'json'].map((f) => ({ label: f.toUpperCase(), onSelect: () => exportResult(f) }))}
                    />
                  </>
                )}
              </div>
              <div className="min-h-0 flex-1 border-t border-line">
                <TabsContent value="results" className="h-full">
                  {result && result.columns.length > 0 ? (
                    <ResultGrid columns={result.columns} rows={result.rows} />
                  ) : (
                    <p className="p-4 text-[13px] text-muted">{execute.isPending ? 'Running…' : 'Run a query to see its results here.'}</p>
                  )}
                </TabsContent>
                <TabsContent value="messages" className="scroll-thin h-full overflow-auto p-3 text-[13px]">
                  {error ? <Callout tone="danger" title="Query failed">{error}</Callout> : result ? (
                    <ul className="space-y-1 font-mono text-xs">
                      <li>{result.statements} statement(s) executed in {result.duration_ms.toFixed(0)} ms.</li>
                      {result.columns.length > 0 && <li>{result.row_count.toLocaleString()} row(s) returned{result.truncated && ` — limited to ${result.max_rows.toLocaleString()} rows`}.</li>}
                      {result.messages.map((m) => <li key={m}>{m}</li>)}
                    </ul>
                  ) : <p className="text-muted">No messages.</p>}
                </TabsContent>
                <TabsContent value="history" className="scroll-thin h-full overflow-auto">
                  <ul className="divide-y divide-line text-[13px]">
                    {(history.data?.items ?? []).filter((h) => h.status !== undefined).map((h) => (
                      <li key={h.id} className="flex items-start gap-3 px-3 py-2">
                        <Badge tone={h.status === 'completed' ? 'success' : 'danger'}>{h.status}</Badge>
                        <button className="min-w-0 flex-1 text-left" onClick={() => setCode(h.sql)} title="Open in editor">
                          <code className="block truncate font-mono text-xs">{h.sql}</code>
                          <span className="text-xs text-muted">{formatDateTime(h.created_at)}{h.row_count !== null && ` · ${h.row_count} rows`}{h.duration_ms !== null && ` · ${Math.round(h.duration_ms)} ms`}{h.error && ` · ${h.error.slice(0, 80)}`}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </TabsContent>
                <TabsContent value="schema" className="scroll-thin h-full overflow-auto p-3">
                  {selectedTable ? <TableDetails table={selectedTable} /> : <p className="text-[13px] text-muted">Select a table in the explorer to see its structure.</p>}
                </TabsContent>
                <TabsContent value="details" className="scroll-thin h-full overflow-auto p-3">
                  <pre className="font-mono text-xs">{JSON.stringify({ target: targetLabel, dialect, read_only: schema.data?.read_only, statements: result?.statements, rows: result?.row_count, truncated: result?.truncated, duration_ms: result?.duration_ms, columns: result?.columns }, null, 2)}</pre>
                </TabsContent>
              </div>
            </Tabs>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-0.5 border-t border-line bg-surface-2 px-3 py-1 text-[11.5px] text-muted" role="status">
            <span className="flex items-center gap-1"><Database className="size-3.5" /> {targetLabel}</span>
            <span>{schema.data?.read_only ? 'Read-only' : 'Writes allowed (confirmation required)'}</span>
            <span>{execute.isPending ? 'Running…' : error ? 'Error' : result ? 'Completed' : 'Idle'}</span>
            {result && <span className="num">{result.row_count.toLocaleString()} rows · {result.duration_ms.toFixed(0)} ms</span>}
            <span className="ml-auto hidden sm:inline">Ctrl+Enter run · Ctrl+Shift+Enter run statement · Shift+Alt+F format · Ctrl+S save</span>
          </div>
        </div>
      </div>

      <ConnectionsDialog open={connOpen} onOpenChange={setConnOpen} connections={connections.data?.items ?? []} />
      <SaveQueryDialog open={saveOpen} onOpenChange={setSaveOpen} body={code} target={effective} />
      {saveDsOpen && effective?.kind === 'project' && (
        <SaveDatasetDialog
          projectId={effective.id}
          sqlText={selectionOrAll(false)}
          onClose={() => setSaveDsOpen(false)}
          onSaved={(d) => {
            qc.invalidateQueries({ queryKey: keys.datasets(effective.id) })
            qc.invalidateQueries({ queryKey: ['sql-schema'] })
            toast('success', `Saved “${d.name}” (${d.row_count.toLocaleString()} rows) as a new dataset.`)
            storageSet(`statease.dataset.${effective.id}`, String(d.id))
            navigate(`/p/${effective.id}/analyze`)
          }}
        />
      )}
      <ConfirmDialog
        open={!!pendingConfirm}
        onOpenChange={(v) => !v && setPendingConfirm(null)}
        danger
        title="Run a statement that changes data?"
        confirmLabel="Run statement"
        onConfirm={() => {
          if (pendingConfirm) execute.mutate({ text: pendingConfirm.sql, confirm: true })
          setPendingConfirm(null)
        }}
        description="These statements can modify or permanently delete data in the external database. This cannot be undone from StatEase."
      >
        <ul className="space-y-1">
          {pendingConfirm?.statements.map((s, i) => (
            <li key={i}><Badge tone="danger">{s.type}</Badge> <code className="font-mono text-xs">{s.sql.slice(0, 160)}</code></li>
          ))}
        </ul>
      </ConfirmDialog>
    </div>
  )
}

function Explorer(p: {
  projects: { id: number; name: string }[]
  connections: Connection[]
  target: Target | null
  onTarget: (t: Target) => void
  schema: SchemaTable[]
  schemaLoading: boolean
  schemaError: unknown
  saved: Saved[]
  examples: Example[]
  sampleConnectionId?: number
  onInsert: (sql: string) => void
  onSelectTable: (t: SchemaTable) => void
  onPreview: (t: SchemaTable) => void
  onManage: () => void
  mode: 'simple' | 'advanced'
}) {
  const [open, setOpen] = useState<Set<string>>(new Set())
  const value = p.target ? `${p.target.kind}:${p.target.id}` : ''
  const examples = p.examples.filter((e) => (p.target?.kind === 'project' ? e.target === 'workspace' : p.target?.id === p.sampleConnectionId ? e.target === 'sample' : false))
  return (
    <div className="scroll-thin flex min-h-0 flex-1 flex-col overflow-y-auto">
      <div className="space-y-2 border-b border-line p-3">
        <Field label="Data source">
          {(id) => (
            <Select id={id} value={value} onChange={(e) => { const [k, v] = e.target.value.split(':'); p.onTarget({ kind: k as Target['kind'], id: Number(v) }) }}>
              <optgroup label="Project datasets (read-only)">
                {p.projects.map((x) => <option key={x.id} value={`project:${x.id}`}>{x.name}</option>)}
              </optgroup>
              <optgroup label="Database connections">
                {p.sampleConnectionId && !p.connections.some((c) => c.id === p.sampleConnectionId) && <option value={`connection:${p.sampleConnectionId}`}>Sample store (SQLite)</option>}
                {p.connections.map((c) => <option key={c.id} value={`connection:${c.id}`}>{c.name}</option>)}
              </optgroup>
            </Select>
          )}
        </Field>
        <Button size="sm" variant="ghost" className="w-full justify-start" onClick={p.onManage}><Settings2 /> Manage connections</Button>
      </div>
      <div className="p-2">
        <div className="label-caps px-1 pb-1">{p.target?.kind === 'project' ? 'Datasets' : 'Tables & views'}</div>
        {p.schemaLoading && <p className="px-1 text-xs text-muted">Loading schema…</p>}
        {!!p.schemaError && <p className="px-1 text-xs text-danger">{errorMessage(p.schemaError)}</p>}
        <ul className="text-[13px]">
          {p.schema.map((t) => {
            const isOpen = open.has(t.name)
            return (
              <li key={t.name}>
                <div className="group flex items-center rounded hover:bg-surface-3">
                  <button className="flex min-w-0 flex-1 items-center gap-1 px-1 py-1 text-left" onClick={() => setOpen((s) => { const n = new Set(s); if (n.has(t.name)) n.delete(t.name); else n.add(t.name); return n })} aria-expanded={isOpen}>
                    <ChevronRight className={cn('size-3.5 shrink-0 text-muted transition-transform', isOpen && 'rotate-90')} />
                    <Table2 className="size-3.5 shrink-0 text-muted" />
                    <span className="truncate font-mono text-xs">{t.name}</span>
                    {t.rows !== null && <span className="num ml-auto pl-1 text-[11px] text-muted">{t.rows.toLocaleString()}</span>}
                  </button>
                  <button className="hidden rounded px-1 text-[11px] text-accent group-hover:block hover:underline" onClick={() => p.onPreview(t)}>Preview</button>
                  {p.mode === 'advanced' && <button className="hidden rounded px-1 text-[11px] text-accent group-hover:block hover:underline" onClick={() => p.onSelectTable(t)}>Info</button>}
                </div>
                {isOpen && (
                  <ul className="mb-1 ml-6 border-l border-line pl-2">
                    {t.columns.map((c) => (
                      <li key={c.name} className="flex items-center gap-1.5 py-0.5 text-xs">
                        {c.primary_key ? <KeyRound className="size-3 shrink-0 text-warning" aria-label="Primary key" /> : t.foreign_keys.some((f) => f.column === c.name) ? <Link2 className="size-3 shrink-0 text-accent" aria-label="Foreign key" /> : <span className="size-3 shrink-0" />}
                        <span className="truncate font-mono">{c.name}</span>
                        <span className="ml-auto shrink-0 pl-1 font-mono text-[10.5px] text-muted lowercase">{c.type}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            )
          })}
        </ul>
      </div>
      {p.saved.length > 0 && (
        <div className="border-t border-line p-2">
          <div className="label-caps px-1 pb-1">Saved queries</div>
          <ul>
            {p.saved.map((s) => (
              <li key={s.id}><button className="w-full truncate rounded px-1 py-1 text-left text-[13px] hover:bg-surface-3" onClick={() => p.onInsert(s.body)}>{s.name}</button></li>
            ))}
          </ul>
        </div>
      )}
      {examples.length > 0 && (
        <div className="border-t border-line p-2">
          <div className="label-caps flex items-center gap-1 px-1 pb-1"><BookOpen className="size-3" /> Example queries</div>
          <ul>
            {examples.map((e) => (
              <li key={e.title}><button className="w-full truncate rounded px-1 py-1 text-left text-[13px] hover:bg-surface-3" onClick={() => p.onInsert(e.sql)}>{e.title}</button></li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function TableDetails({ table }: { table: SchemaTable }) {
  return (
    <div className="space-y-3 text-[13px]">
      <div>
        <h3 className="font-mono font-semibold">{table.name}</h3>
        <p className="text-xs text-muted">{table.description ?? table.type}{table.rows !== null && ` · ${table.rows.toLocaleString()} rows`}</p>
      </div>
      <table className="stat-table">
        <thead><tr><th>Column</th><th>Type</th><th>Nullable</th><th>Key</th>{table.columns.some((c) => c.level) && <th>Measurement</th>}</tr></thead>
        <tbody>
          {table.columns.map((c) => (
            <tr key={c.name}>
              <td className="font-mono">{c.name}</td>
              <td className="font-mono text-muted">{c.type}</td>
              <td>{c.nullable ? 'yes' : 'no'}</td>
              <td>{c.primary_key ? 'PK' : table.foreign_keys.find((f) => f.column === c.name)?.references ? `FK → ${table.foreign_keys.find((f) => f.column === c.name)!.references}` : ''}</td>
              {table.columns.some((x) => x.level) && <td>{c.level}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SaveQueryDialog({ open, onOpenChange, body, target }: { open: boolean; onOpenChange: (v: boolean) => void; body: string; target: Target | null }) {
  const [name, setName] = useState('')
  const qc = useQueryClient()
  const toast = useToast()
  const save = useMutation({
    mutationFn: () => api.post('/sql/saved', { name, body, language: 'sql', project_id: target?.kind === 'project' ? target.id : null, connection_id: target?.kind === 'connection' ? target.id : null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sql-saved'] })
      toast('success', 'Query saved.')
      onOpenChange(false)
      setName('')
    },
    onError: (e) => toast('danger', errorMessage(e)),
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="sm" title="Save query" footer={<><Button onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="primary" disabled={!name.trim()} loading={save.isPending} onClick={() => save.mutate()}>Save</Button></>}>
      <Field label="Name">{(id) => <Input id={id} value={name} autoFocus onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && name.trim() && save.mutate()} />}</Field>
    </Dialog>
  )
}

function SaveDatasetDialog({ projectId, sqlText, onClose, onSaved }: { projectId: number; sqlText: string; onClose: () => void; onSaved: (d: Dataset) => void }) {
  const [name, setName] = useState('Query result')
  const [error, setError] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: () => api.post<Dataset>('/sql/save-dataset', { sql: sqlText, project_id: projectId, name }),
    onSuccess: onSaved,
    onError: (e) => setError(errorMessage(e)),
  })
  return (
    <Dialog
      open
      onOpenChange={(v) => !v && onClose()}
      title="Save result as a dataset"
      description="The full result of the query (not just the rows shown) is saved as a new dataset. Source datasets are not changed, and the query is recorded as lineage."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate()}>Save and analyze</Button></>}
    >
      <Field label="Dataset name">{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
      <pre className="mt-3 max-h-40 overflow-auto rounded-md bg-surface-3 p-2 font-mono text-xs">{sqlText}</pre>
      {error && <Callout tone="danger" className="mt-3">{error}</Callout>}
    </Dialog>
  )
}
