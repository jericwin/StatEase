import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LogOut } from 'lucide-react'
import { useState } from 'react'
import { PageBody, PageHeader } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Panel, Skeleton, useToast } from '@/components/ui/feedback'
import { Field, Input, SegmentedControl, Select } from '@/components/ui/form'
import { api, errorMessage, getToken, setToken } from '@/lib/api'
import { useMe, useProjects } from '@/lib/queries'
import type { Project, ProjectSettings } from '@/lib/types'
import { applyTheme, storageGet, type Theme } from '@/lib/utils'

export default function SettingsPage() {
  const [theme, setTheme] = useState<Theme>(() => storageGet('statease.theme', 'system') as Theme)
  const projects = useProjects('active')
  const me = useMe()
  const limits = useQuery({ queryKey: ['limits'], queryFn: () => api.get<Record<string, unknown>>('/system/limits') })
  const [projectId, setProjectId] = useState<number | null>(null)
  const project = (projects.data?.items ?? []).find((p) => p.id === projectId) ?? projects.data?.items[0]

  return (
    <>
      <PageHeader title="Settings" />
      <PageBody className="max-w-4xl space-y-5">
        <Panel title="Appearance">
          <SegmentedControl
            label="Theme"
            value={theme}
            onChange={(t) => {
              setTheme(t)
              applyTheme(t)
            }}
            options={[
              { value: 'system', label: 'System' },
              { value: 'light', label: 'Light' },
              { value: 'dark', label: 'Dark' },
            ]}
          />
        </Panel>

        <Panel title="Statistical reporting" description="Applies to new analysis runs and to exports of the selected project.">
          {projects.isLoading && <Skeleton className="h-24" />}
          {project ? (
            <>
              <Field label="Project" className="mb-4 max-w-sm">
                {(id) => (
                  <Select id={id} value={project.id} onChange={(e) => setProjectId(Number(e.target.value))}>
                    {projects.data!.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </Select>
                )}
              </Field>
              <ProjectSettingsForm key={project.id} project={project} />
            </>
          ) : (
            !projects.isLoading && <p className="text-[13px] text-muted">Create a project to configure reporting settings.</p>
          )}
        </Panel>

        <Panel title="Account">
          {me.data && (
            <dl className="grid gap-2 text-[13px] sm:grid-cols-[160px_1fr]">
              <dt className="text-muted">Signed in as</dt>
              <dd>{me.data.display_name ?? me.data.email}</dd>
              <dt className="text-muted">Role</dt>
              <dd className="capitalize">{me.data.role}</dd>
            </dl>
          )}
          {getToken() && (
            <Button
              className="mt-3"
              onClick={() => {
                setToken(null)
                window.location.href = '/'
              }}
            >
              <LogOut /> Sign out
            </Button>
          )}
        </Panel>

        <Panel title="Server limits" description="Configured by the administrator through environment variables.">
          {limits.data && (
            <dl className="grid gap-x-6 gap-y-1.5 text-[13px] sm:grid-cols-2">
              {Object.entries(limits.data).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 border-b border-line py-1">
                  <dt className="text-muted">{k.replace(/_/g, ' ')}</dt>
                  <dd className="num">{String(v)}</dd>
                </div>
              ))}
            </dl>
          )}
        </Panel>
      </PageBody>
    </>
  )
}

function ProjectSettingsForm({ project }: { project: Project }) {
  const [s, setS] = useState<ProjectSettings>(project.settings)
  const qc = useQueryClient()
  const toast = useToast()
  const save = useMutation({
    mutationFn: () => api.patch<Project>(`/projects/${project.id}`, { settings: s }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      qc.invalidateQueries({ queryKey: ['project', project.id] })
      toast('success', 'Settings saved. Re-run analyses to apply a new significance level.')
    },
    onError: (e) => toast('danger', errorMessage(e)),
  })
  return (
    <form
      className="grid gap-4 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate()
      }}
    >
      <Field label="Significance level (α)" help="Conventional default 0.05.">
        {(id) => (
          <Select id={id} value={s.alpha} onChange={(e) => setS({ ...s, alpha: Number(e.target.value) })}>
            {[0.1, 0.05, 0.01, 0.005, 0.001].map((a) => <option key={a} value={a}>{a}</option>)}
          </Select>
        )}
      </Field>
      <Field label="Default confidence level">
        {(id) => (
          <Select id={id} value={s.ci_level} onChange={(e) => setS({ ...s, ci_level: Number(e.target.value) })}>
            {[0.9, 0.95, 0.99].map((a) => <option key={a} value={a}>{a * 100}%</option>)}
          </Select>
        )}
      </Field>
      <Field label="p-value style">
        {(id) => (
          <Select id={id} value={s.p_style} onChange={(e) => setS({ ...s, p_style: e.target.value as 'apa' | 'academic' })}>
            <option value="apa">APA: p = .032, p &lt; .001</option>
            <option value="academic">Leading zero: p = 0.032</option>
          </Select>
        )}
      </Field>
      <Field label="Decimal places in tables">
        {(id) => <Input id={id} type="number" min={0} max={6} value={s.decimals} onChange={(e) => setS({ ...s, decimals: Number(e.target.value) })} />}
      </Field>
      <div className="sm:col-span-2">
        <Button type="submit" variant="primary" loading={save.isPending}>Save settings</Button>
      </div>
    </form>
  )
}
