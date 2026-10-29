import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Archive, ArchiveRestore, Copy, FileJson, FlaskConical, FolderPlus, Pencil, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PageBody, PageHeader } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Badge, EmptyState, ErrorState, Skeleton, useToast } from '@/components/ui/feedback'
import { Field, Input, SegmentedControl, Textarea } from '@/components/ui/form'
import { ActionMenu } from '@/components/ui/menu'
import { ConfirmDialog, Dialog } from '@/components/ui/overlay'
import { api, download, errorMessage } from '@/lib/api'
import { relativeTime } from '@/lib/format'
import { useProjects } from '@/lib/queries'
import { DemoPicker } from './DashboardPage'
import type { Project } from '@/lib/types'

export default function ProjectsPage() {
  const [status, setStatus] = useState<'active' | 'archived'>('active')
  const projects = useProjects(status)
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Project | null>(null)
  const [deleting, setDeleting] = useState<Project | null>(null)

  const refresh = () => qc.invalidateQueries({ queryKey: ['projects'] })
  const [demoOpen, setDemoOpen] = useState(false)
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => api.patch<Project>(`/projects/${id}`, body),
    onSuccess: refresh,
    onError: (e) => toast('danger', errorMessage(e)),
  })
  const duplicate = useMutation({
    mutationFn: (id: number) => api.post<Project>(`/projects/${id}/duplicate`),
    onSuccess: (p) => {
      refresh()
      toast('success', `Created “${p.name}”.`)
    },
    onError: (e) => toast('danger', errorMessage(e)),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/projects/${id}`),
    onSuccess: () => {
      setDeleting(null)
      refresh()
      toast('success', 'Project deleted.')
    },
    onError: (e) => toast('danger', errorMessage(e)),
  })

  const items = projects.data?.items ?? []

  return (
    <>
      <PageHeader
        title="Projects"
        description="Each project keeps its datasets, analysis settings, results and exports together."
        actions={
          <>
            <Button onClick={() => setDemoOpen(true)}>
              <FlaskConical /> Open demo project
            </Button>
            <Button variant="primary" onClick={() => setCreating(true)}>
              <FolderPlus /> New project
            </Button>
          </>
        }
      />
      <PageBody>
        <div className="mb-4 flex items-center justify-between gap-3">
          <SegmentedControl
            label="Project status"
            value={status}
            onChange={setStatus}
            options={[
              { value: 'active', label: 'Active' },
              { value: 'archived', label: 'Archived' },
            ]}
          />
          {projects.data && <span className="text-xs text-muted">{projects.data.total} project(s)</span>}
        </div>

        {projects.isError && <ErrorState error={projects.error} retry={() => projects.refetch()} />}
        {projects.isLoading && (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        )}

        {projects.isSuccess && items.length === 0 && status === 'active' && <Onboarding onCreate={() => setCreating(true)} onDemo={() => setDemoOpen(true)} />}
        {projects.isSuccess && items.length === 0 && status === 'archived' && (
          <EmptyState title="No archived projects" description="Archived projects are kept intact and can be restored at any time." />
        )}

        {items.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-line bg-surface">
            <table className="w-full text-[13px]">
              <thead className="hidden border-b border-line bg-surface-2 text-left text-xs text-muted sm:table-header-group">
                <tr>
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 text-right font-medium">Datasets</th>
                  <th className="px-4 py-2 text-right font-medium">Analyses</th>
                  <th className="px-4 py-2 text-right font-medium">Results</th>
                  <th className="px-4 py-2 font-medium">Updated</th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {items.map((p) => (
                  <tr key={p.id} className="hover:bg-surface-2">
                    <td className="px-4 py-3">
                      <Link to={`/p/${p.id}`} className="font-medium text-fg hover:text-accent hover:underline">
                        {p.name}
                      </Link>
                      {p.is_demo && (
                        <Badge tone="warning" className="ml-2">
                          Demo · fictional data
                        </Badge>
                      )}
                      {p.description && <p className="mt-0.5 line-clamp-1 text-xs text-muted">{p.description}</p>}
                      <p className="mt-1 text-xs text-muted sm:hidden">
                        {p.counts.datasets} datasets · {p.counts.analyses} analyses · {relativeTime(p.updated_at)}
                      </p>
                    </td>
                    <td className="num hidden px-4 py-3 text-right sm:table-cell">{p.counts.datasets}</td>
                    <td className="num hidden px-4 py-3 text-right sm:table-cell">{p.counts.analyses}</td>
                    <td className="num hidden px-4 py-3 text-right sm:table-cell">{p.counts.results}</td>
                    <td className="hidden px-4 py-3 whitespace-nowrap text-muted sm:table-cell">{relativeTime(p.updated_at)}</td>
                    <td className="px-2 py-3 text-right">
                      <ActionMenu
                        label={`Actions for ${p.name}`}
                        actions={[
                          { label: 'Rename', icon: <Pencil />, onSelect: () => setEditing(p) },
                          { label: 'Duplicate', icon: <Copy />, onSelect: () => duplicate.mutate(p.id) },
                          {
                            label: 'Export metadata (JSON)',
                            icon: <FileJson />,
                            onSelect: () =>
                              api.get(`/projects/${p.id}/export-metadata`).then((data) => {
                                const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
                                const a = document.createElement('a')
                                a.href = URL.createObjectURL(blob)
                                a.download = `${p.name}-metadata.json`
                                a.click()
                              }),
                          },
                          p.status === 'active'
                            ? { label: 'Archive', icon: <Archive />, onSelect: () => update.mutate({ id: p.id, body: { status: 'archived' } }) }
                            : { label: 'Restore', icon: <ArchiveRestore />, onSelect: () => update.mutate({ id: p.id, body: { status: 'active' } }) },
                          'separator',
                          { label: 'Delete…', icon: <Trash2 />, danger: true, onSelect: () => setDeleting(p) },
                        ]}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </PageBody>

      <ProjectDialog
        open={creating || !!editing}
        project={editing}
        onOpenChange={(v) => {
          if (!v) {
            setCreating(false)
            setEditing(null)
          }
        }}
        onSaved={(p, isNew) => {
          refresh()
          setCreating(false)
          setEditing(null)
          if (isNew) navigate(`/p/${p.id}/import`)
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(v) => !v && setDeleting(null)}
        title="Delete project?"
        danger
        confirmLabel="Delete project"
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        description={
          <>
            “{deleting?.name}” and all of its datasets, analyses, results and exports will be permanently deleted. Archive the project
            instead if you may need it later.
          </>
        }
      />
      <DemoPicker open={demoOpen} onOpenChange={setDemoOpen} />
    </>
  )
}

function Onboarding({ onCreate, onDemo }: { onCreate: () => void; onDemo: () => void }) {
  const steps = [
    ['Import', 'Upload an Excel, CSV or similar file. Variable types are detected for you to review.'],
    ['Analyze', 'Accept recommended analyses or pick tests from a checklist. Assumptions are checked automatically.'],
    ['Export', 'Choose tables, charts and interpretations, then download an editable Word or Excel report.'],
  ]
  return (
    <div className="rounded-lg border border-line bg-surface">
      <div className="border-b border-line px-6 py-5">
        <h2 className="text-[16px] font-semibold">Start your first analysis</h2>
        <p className="mt-1 text-[13px] text-muted">No programming or statistical software required.</p>
      </div>
      <ol className="grid divide-y divide-line sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        {steps.map(([t, d], i) => (
          <li key={t} className="px-6 py-5">
            <div className="num text-xs font-semibold text-accent">Step {i + 1}</div>
            <div className="mt-1 text-[14px] font-medium">{t}</div>
            <p className="mt-1 text-[13px] text-muted">{d}</p>
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap gap-2 border-t border-line px-6 py-4">
        <Button variant="primary" onClick={onCreate}>
          <FolderPlus /> Create a project
        </Button>
        <Button onClick={onDemo}>
          <FlaskConical /> Open a demo (fictional data)
        </Button>
        <Button variant="ghost" onClick={() => download('/public/demos/fertilizer/sample.csv', { fallbackName: 'sample_fertilizer_fictional.csv' })}>
          Download sample CSV
        </Button>
      </div>
    </div>
  )
}

function ProjectDialog({
  open,
  project,
  onOpenChange,
  onSaved,
}: {
  open: boolean
  project: Project | null
  onOpenChange: (v: boolean) => void
  onSaved: (p: Project, isNew: boolean) => void
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [lastOpen, setLastOpen] = useState(false)
  if (open !== lastOpen) {
    setLastOpen(open)
    if (open) {
      setName(project?.name ?? '')
      setDescription(project?.description ?? '')
      setError(null)
    }
  }
  const save = async () => {
    if (!name.trim()) return setError('Enter a project name.')
    setBusy(true)
    try {
      const p = project
        ? await api.patch<Project>(`/projects/${project.id}`, { name, description })
        : await api.post<Project>('/projects', { name, description: description || null })
      onSaved(p, !project)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={project ? 'Rename project' : 'New project'}
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" onClick={save} loading={busy}>
            {project ? 'Save' : 'Create and import data'}
          </Button>
        </>
      }
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          save()
        }}
      >
        <Field label="Name" error={error}>
          {(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} autoFocus placeholder="e.g. Thesis — customer satisfaction" />}
        </Field>
        <Field label="Description (optional)">
          {(id) => <Textarea id={id} value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />}
        </Field>
      </form>
    </Dialog>
  )
}
