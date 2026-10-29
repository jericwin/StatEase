import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, FolderOpen, Loader2, PlayCircle, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { PageBody, PageHeader } from '@/components/layout/AppShell'
import { Badge, Callout, EmptyState, Skeleton } from '@/components/ui/feedback'
import { Dialog } from '@/components/ui/overlay'
import { api, errorMessage } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { relativeTime } from '@/lib/format'
import { useProjects } from '@/lib/queries'
import type { Project } from '@/lib/types'
import { DEMO_META } from './public/Landing'

const DEMOS = [
  { key: 'fertilizer', title: 'Fertilizer Trial on Pechay' },
  { key: 'experiment', title: 'Experimental Group Comparison' },
  { key: 'survey', title: 'Survey Data Analysis' },
]

export function useOpenDemo() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (key: string) => api.post<Project & { report_id: number | null }>('/demo', { key }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/p/${p.id}/report`)
    },
  })
}

export function DemoPicker({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const demo = useOpenDemo()
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Open a demo" description="Each demo creates a project with fictional sample data, finished analyses and an editable report." size="lg">
      <div className="grid gap-3 sm:grid-cols-3">
        {DEMOS.map((d) => {
          const M = DEMO_META[d.key]
          const busy = demo.isPending && demo.variables === d.key
          return (
            <button
              key={d.key}
              onClick={() => demo.mutate(d.key)}
              disabled={demo.isPending}
              className="lift flex flex-col items-start rounded-lg border border-line p-4 text-left hover:border-accent/40 disabled:opacity-60"
            >
              <span className="flex size-9 items-center justify-center rounded-md bg-accent-soft text-accent">{busy ? <Loader2 className="size-4 animate-spin" /> : <M.icon className="size-4" />}</span>
              <span className="mt-3 text-[14px] font-semibold">{d.title}</span>
              <span className="mt-1 text-[12.5px] text-muted">{M.blurb}</span>
            </button>
          )
        })}
      </div>
      {demo.isPending && <p className="mt-3 text-[13px] text-muted">Preparing the demo and running its analyses…</p>}
      {demo.isError && <Callout tone="danger" className="mt-3">{errorMessage(demo.error)}</Callout>}
    </Dialog>
  )
}

export default function DashboardPage() {
  const { user } = useAuth()
  const projects = useProjects('active')
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [demoOpen, setDemoOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const openDemo = useOpenDemo()

  // Arriving from "Try this demo" via Google sign-in.
  const demoParam = params.get('demo')
  useEffect(() => {
    if (demoParam && !openDemo.isPending) {
      setParams({}, { replace: true })
      openDemo.mutate(demoParam)
    }
  }, [demoParam]) // eslint-disable-line react-hooks/exhaustive-deps

  const startUpload = async (file: File) => {
    setError(null)
    try {
      const name = file.name.replace(/\.[^.]+$/, '') || 'New project'
      const p = await api.post<Project>('/projects', { name })
      qc.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/p/${p.id}/import`, { state: { file } })
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const first = (user?.display_name || '').split(' ')[0]
  const recent = (projects.data?.items ?? []).slice(0, 6)
  const tiles = [
    { icon: Upload, title: 'Upload data', text: 'Excel or CSV — we take it from there.', onClick: () => fileInput.current?.click(), primary: true },
    { icon: PlayCircle, title: 'Open a demo', text: 'Explore with fictional sample data.', onClick: () => setDemoOpen(true) },
    { icon: FolderOpen, title: 'My projects', text: `${projects.data?.total ?? 0} project${projects.data?.total === 1 ? '' : 's'}`, onClick: () => navigate('/app/projects') },
  ]
  return (
    <>
      <PageHeader title={first ? `Welcome back, ${first}` : 'Welcome'} description="What would you like to do?" />
      <PageBody className="space-y-8">
        <input ref={fileInput} type="file" accept=".csv,.tsv,.txt,.xlsx,.xls,.xlsm" className="sr-only" aria-label="Choose a data file" onChange={(e) => e.target.files?.[0] && startUpload(e.target.files[0])} />
        <div className="grid gap-4 md:grid-cols-3">
          {tiles.map((t, i) => (
            <button
              key={t.title}
              onClick={t.onClick}
              style={{ animationDelay: `${i * 50}ms` }}
              className={`animate-in lift flex items-center gap-4 rounded-xl border p-5 text-left ${t.primary ? 'border-accent bg-accent text-accent-fg' : 'border-line bg-surface hover:border-accent/40'}`}
            >
              <span className={`flex size-11 shrink-0 items-center justify-center rounded-lg ${t.primary ? 'bg-white/15' : 'bg-accent-soft text-accent'}`}>
                <t.icon className="size-5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[15.5px] font-semibold">{t.title}</span>
                <span className={`block text-[13px] ${t.primary ? 'text-accent-fg/80' : 'text-muted'}`}>{t.text}</span>
              </span>
              <ArrowRight className="size-4 shrink-0 opacity-60" />
            </button>
          ))}
        </div>
        {error && <Callout tone="danger">{error}</Callout>}
        {openDemo.isPending && <Callout tone="info">Preparing your demo project…</Callout>}

        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[15px] font-semibold">Recent projects</h2>
            {recent.length > 0 && <Link to="/app/projects" className="text-[13px] font-medium text-accent hover:underline">View all</Link>}
          </div>
          {projects.isLoading && <Skeleton className="h-40" />}
          {projects.isSuccess && recent.length === 0 && (
            <div className="rounded-xl border border-dashed border-line-strong">
              <EmptyState title="No projects yet" description="Upload a file or open a demo to get started." />
            </div>
          )}
          {recent.length > 0 && (
            <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
              {recent.map((p) => (
                <li key={p.id}>
                  <Link to={`/p/${p.id}`} className="flex items-center gap-4 px-4 py-3 hover:bg-surface-2">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-surface-3 text-[13px] font-semibold text-fg-2">{p.name.slice(0, 1).toUpperCase()}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-medium">{p.name}</span>
                      <span className="block text-[12.5px] text-muted">Edited {relativeTime(p.updated_at)}</span>
                    </span>
                    {p.is_demo ? <Badge tone="warning">Demo</Badge> : p.counts.results > 0 ? <Badge tone="success">{p.counts.results} results</Badge> : p.counts.datasets > 0 ? <Badge tone="accent">Data imported</Badge> : <Badge>Empty</Badge>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </PageBody>
      <DemoPicker open={demoOpen} onOpenChange={setDemoOpen} />
    </>
  )
}
