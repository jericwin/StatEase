import { useQuery } from '@tanstack/react-query'
import { LogOut } from 'lucide-react'
import { useState } from 'react'
import { PageBody, PageHeader } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Panel } from '@/components/ui/feedback'
import { SegmentedControl } from '@/components/ui/form'
import { api, getToken, setToken } from '@/lib/api'
import { useMe } from '@/lib/queries'
import { applyTheme, storageGet, type Theme } from '@/lib/utils'

export default function SettingsPage() {
  const [theme, setTheme] = useState<Theme>(() => storageGet('statease.theme', 'system') as Theme)
  const me = useMe()
  const limits = useQuery({ queryKey: ['limits'], queryFn: () => api.get<Record<string, unknown>>('/system/limits') })

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

