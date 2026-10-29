import { python } from '@codemirror/lang-python'
import { Prec } from '@codemirror/state'
import { keymap } from '@codemirror/view'
import { useMutation, useQuery } from '@tanstack/react-query'
import CodeMirror from '@uiw/react-codemirror'
import { Play, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { PageHeader } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Badge, Callout, Panel } from '@/components/ui/feedback'
import { Field, Select } from '@/components/ui/form'
import { ResultGrid } from '@/features/dev/ResultGrid'
import { useEditorTheme } from '@/features/dev/useEditorTheme'
import { api, errorMessage } from '@/lib/api'
import { useProjects } from '@/lib/queries'
import type { DatasetSummary, Paged } from '@/lib/types'
import { storageGet, storageSet } from '@/lib/utils'

interface RunResult {
  status: 'completed' | 'error' | 'killed'
  stdout: string
  stderr: string
  tables: { title: string; columns: string[]; rows: unknown[][]; total_rows: number }[]
  figures: string[]
  duration_ms: number
  peak_memory_mb: number
}

export default function PythonPage() {
  const info = useQuery({ queryKey: ['py-templates'], queryFn: () => api.get<{ enabled: boolean; templates: { id: string; title: string; code: string }[]; limits: { timeout_seconds: number; memory_mb: number } }>('/python/templates') })
  const projects = useProjects('active')
  const [projectId, setProjectId] = useState<number | null>(null)
  const pid = projectId ?? projects.data?.items[0]?.id ?? null
  const datasets = useQuery({ queryKey: ['datasets', pid], queryFn: () => api.get<Paged<DatasetSummary>>(`/projects/${pid}/datasets`), enabled: !!pid })
  const [datasetId, setDatasetId] = useState<number | null>(null)
  const dsid = datasetId ?? datasets.data?.items.at(-1)?.id ?? null
  const [code, setCode] = useState(() => storageGet('statease.py.draft', "# The selected dataset is available as `df` (pandas).\n# show(frame) displays a table; matplotlib figures are captured.\nshow(df.describe().T, 'Summary')\n"))
  const theme = useEditorTheme()
  const run = useMutation({ mutationFn: () => api.post<RunResult>('/python/run', { code, dataset_id: dsid }) })
  const keys = useMemo(() => Prec.highest(keymap.of([{ key: 'Mod-Enter', run: () => { run.mutate(); return true } }])), [run])

  return (
    <>
      <PageHeader
        title="Python analysis console"
        description="Run Python for custom analyses and transformations. Code runs in a separate, restricted process — never inside the application server."
        actions={info.data && <Badge tone={info.data.enabled ? 'success' : 'neutral'}>{info.data.enabled ? 'Enabled' : 'Disabled on this server'}</Badge>}
      />
      <div className="mx-auto max-w-[1440px] space-y-4 px-4 py-5 sm:px-6">
        {info.isError && <Callout tone="danger">{errorMessage(info.error)}</Callout>}
        {info.data && !info.data.enabled && (
          <Callout tone="info" title="The console is disabled">
            An administrator can enable it by setting <code className="font-mono">STATEASE_ENABLE_PYTHON_CONSOLE=true</code>. Read docs/SECURITY.md first:
            for shared servers, run the console inside a container without network access.
          </Callout>
        )}
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0 overflow-hidden rounded-lg border border-line">
            <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface px-3 py-2">
              <Button size="sm" variant="primary" onClick={() => { storageSet('statease.py.draft', code); run.mutate() }} loading={run.isPending} disabled={!info.data?.enabled}>
                <Play /> Run (Ctrl+Enter)
              </Button>
              {info.data && <span className="text-xs text-muted">Limits: {info.data.limits.timeout_seconds}s, {info.data.limits.memory_mb} MB · no network · writes only to a temporary folder</span>}
            </div>
            <CodeMirror value={code} onChange={setCode} height="360px" theme="none" extensions={[python(), keys, ...theme]} aria-label="Python editor" />
          </div>
          <div className="space-y-4">
            <Panel title="Data">
              <div className="space-y-3">
                <Field label="Project">
                  {(id) => (
                    <Select id={id} value={pid ?? ''} onChange={(e) => { setProjectId(Number(e.target.value)); setDatasetId(null) }}>
                      {(projects.data?.items ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </Select>
                  )}
                </Field>
                <Field label="Dataset (available as df)">
                  {(id) => (
                    <Select id={id} value={dsid ?? ''} onChange={(e) => setDatasetId(Number(e.target.value))}>
                      {(datasets.data?.items ?? []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </Select>
                  )}
                </Field>
              </div>
            </Panel>
            <Panel title="Templates" bodyClassName="p-0">
              <ul className="divide-y divide-line">
                {(info.data?.templates ?? []).map((t) => (
                  <li key={t.id}><button className="w-full px-4 py-2 text-left text-[13px] hover:bg-surface-2" onClick={() => setCode(t.code)}>{t.title}</button></li>
                ))}
              </ul>
            </Panel>
          </div>
        </div>

        {run.isError && <Callout tone="danger">{errorMessage(run.error)}</Callout>}
        {run.data && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
              <Badge tone={run.data.status === 'completed' ? 'success' : 'danger'}>{run.data.status}</Badge>
              <span className="num">{Math.round(run.data.duration_ms)} ms · peak {run.data.peak_memory_mb.toFixed(0)} MB</span>
            </div>
            {run.data.stdout && <Panel title="Output"><pre className="scroll-thin max-h-80 overflow-auto font-mono text-xs whitespace-pre-wrap">{run.data.stdout}</pre></Panel>}
            {run.data.stderr && (
              <Panel title={<span className="flex items-center gap-1.5 text-danger"><ShieldAlert className="size-4" /> Errors</span>}>
                <pre className="scroll-thin max-h-80 overflow-auto font-mono text-xs whitespace-pre-wrap text-danger">{run.data.stderr}</pre>
              </Panel>
            )}
            {run.data.tables.map((t, i) => (
              <Panel key={i} title={t.title} description={`${t.total_rows.toLocaleString()} rows${t.total_rows > t.rows.length ? `, first ${t.rows.length} shown` : ''}`} bodyClassName="h-80 p-0">
                <ResultGrid columns={t.columns.map((c) => ({ name: c }))} rows={t.rows} />
              </Panel>
            ))}
            {run.data.figures.map((f, i) => (
              <Panel key={i} title={`Figure ${i + 1}`}>
                <img src={`data:image/png;base64,${f}`} alt={`Figure ${i + 1} produced by the script`} className="max-w-full" />
              </Panel>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
