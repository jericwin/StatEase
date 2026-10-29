import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Database, Plug, Trash2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge, Callout, useToast } from '@/components/ui/feedback'
import { Field, Input, Select, Switch } from '@/components/ui/form'
import { Dialog } from '@/components/ui/overlay'
import { api, errorMessage } from '@/lib/api'

export interface Connection {
  id: number
  name: string
  engine: 'sqlite' | 'postgresql' | 'mysql'
  host: string | null
  port: number | null
  database: string | null
  username: string | null
  has_password: boolean
  allow_writes: boolean
}

export function ConnectionsDialog({ open, onOpenChange, connections }: { open: boolean; onOpenChange: (v: boolean) => void; connections: Connection[] }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ name: '', engine: 'postgresql', host: 'localhost', port: '', database: '', username: '', password: '', sslmode: 'prefer', allow_writes: false })
  const [error, setError] = useState<string | null>(null)
  const sqliteFile = useRef<HTMLInputElement>(null)
  const importFile = useRef<HTMLInputElement>(null)
  const [importTarget, setImportTarget] = useState<number | null>(null)
  const refresh = () => qc.invalidateQueries({ queryKey: ['sql-connections'] })

  const create = useMutation({
    mutationFn: () => api.post('/sql/connections', { ...form, port: form.port ? Number(form.port) : null, password: form.password || null, sslmode: form.engine === 'postgresql' ? form.sslmode : null }),
    onSuccess: () => {
      refresh()
      setForm({ ...form, name: '', database: '', username: '', password: '' })
      toast('success', 'Connection saved. The password is stored encrypted on the server.')
    },
    onError: (e) => setError(errorMessage(e)),
  })
  const test = useMutation({
    mutationFn: (id: number) => api.post<{ ok: boolean; latency_ms: number }>(`/sql/connections/${id}/test`),
    onSuccess: (r) => toast('success', `Connected (${Math.round(r.latency_ms)} ms).`),
    onError: (e) => toast('danger', errorMessage(e)),
  })
  const remove = useMutation({ mutationFn: (id: number) => api.del(`/sql/connections/${id}`), onSuccess: refresh })
  const sqlite = async (file: File | null) => {
    const fd = new FormData()
    fd.append('name', file ? file.name : `Local SQLite ${new Date().toLocaleDateString()}`)
    if (file) fd.append('file', file)
    try {
      await api.upload('/sql/connections/sqlite', fd)
      refresh()
      toast('success', file ? 'SQLite database uploaded (read-only).' : 'Empty SQLite database created (writable).')
    } catch (e) {
      toast('danger', errorMessage(e))
    }
  }
  const importTable = async (file: File) => {
    if (!importTarget) return
    const fd = new FormData()
    fd.append('table', file.name.replace(/\.[^.]+$/, ''))
    fd.append('file', file)
    try {
      const r = await api.upload<{ table: string; rows: number }>(`/sql/connections/${importTarget}/import-table`, fd)
      qc.invalidateQueries({ queryKey: ['sql-schema'] })
      toast('success', `Imported ${r.rows.toLocaleString()} rows into table “${r.table}”.`)
    } catch (e) {
      toast('danger', errorMessage(e))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="xl" title="Database connections" description="Credentials are encrypted on the server and never sent back to the browser.">
      <div className="grid gap-6 lg:grid-cols-2">
        <section>
          <h3 className="label-caps mb-2">Saved connections</h3>
          {connections.length === 0 && <p className="text-[13px] text-muted">No connections yet.</p>}
          <ul className="divide-y divide-line rounded-md border border-line">
            {connections.map((c) => (
              <li key={c.id} className="flex items-center gap-2 px-3 py-2 text-[13px]">
                <Database className="size-4 shrink-0 text-muted" />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{c.name}</div>
                  <div className="truncate text-xs text-muted">
                    {c.engine}
                    {c.host && ` · ${c.username}@${c.host}:${c.port}/${c.database}`}
                  </div>
                </div>
                <Badge tone={c.allow_writes ? 'warning' : 'neutral'}>{c.allow_writes ? 'Writable' : 'Read-only'}</Badge>
                {c.engine === 'sqlite' && c.allow_writes && (
                  <Button size="sm" variant="ghost" onClick={() => { setImportTarget(c.id); importFile.current?.click() }} title="Import CSV/Excel as table">
                    <Upload />
                  </Button>
                )}
                <Button size="sm" variant="ghost" onClick={() => test.mutate(c.id)} aria-label={`Test ${c.name}`}><Plug /></Button>
                <Button size="sm" variant="ghost" className="text-danger" onClick={() => remove.mutate(c.id)} aria-label={`Delete ${c.name}`}><Trash2 /></Button>
              </li>
            ))}
          </ul>
          <input ref={importFile} type="file" accept=".csv,.tsv,.xlsx,.xls" className="sr-only" onChange={(e) => e.target.files?.[0] && importTable(e.target.files[0])} aria-label="File to import as table" />
          <h3 className="label-caps mt-5 mb-2">SQLite</h3>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => sqliteFile.current?.click()}><Upload /> Upload .sqlite file</Button>
            <Button onClick={() => sqlite(null)}>Create empty database</Button>
            <input ref={sqliteFile} type="file" accept=".sqlite,.sqlite3,.db" className="sr-only" onChange={(e) => sqlite(e.target.files?.[0] ?? null)} aria-label="SQLite file" />
          </div>
          <p className="mt-2 text-xs text-muted">SQLite files are stored in the server's managed directory; arbitrary server paths cannot be opened.</p>
        </section>
        <section>
          <h3 className="label-caps mb-2">New PostgreSQL / MySQL connection</h3>
          <form
            className="grid gap-3 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault()
              setError(null)
              create.mutate()
            }}
          >
            <Field label="Name">{(id) => <Input id={id} required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}</Field>
            <Field label="Engine">
              {(id) => (
                <Select id={id} value={form.engine} onChange={(e) => setForm({ ...form, engine: e.target.value })}>
                  <option value="postgresql">PostgreSQL</option>
                  <option value="mysql">MySQL / MariaDB</option>
                </Select>
              )}
            </Field>
            <Field label="Host">{(id) => <Input id={id} required value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} />}</Field>
            <Field label="Port">{(id) => <Input id={id} inputMode="numeric" placeholder={form.engine === 'postgresql' ? '5432' : '3306'} value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} />}</Field>
            <Field label="Database">{(id) => <Input id={id} required value={form.database} onChange={(e) => setForm({ ...form, database: e.target.value })} />}</Field>
            <Field label="Username">{(id) => <Input id={id} required autoComplete="off" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />}</Field>
            <Field label="Password" className="sm:col-span-2">{(id) => <Input id={id} type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />}</Field>
            <div className="flex items-center justify-between gap-2 text-[13px] sm:col-span-2">
              <label htmlFor="allow-writes">Allow write statements (administrators only, with confirmation)</label>
              <Switch id="allow-writes" checked={form.allow_writes} onCheckedChange={(v) => setForm({ ...form, allow_writes: v })} />
            </div>
            {error && <Callout tone="danger" className="sm:col-span-2">{error}</Callout>}
            <div className="sm:col-span-2">
              <Button type="submit" variant="primary" loading={create.isPending}>Save connection</Button>
            </div>
          </form>
          <p className="mt-3 text-xs text-muted">Use a least-privilege database account. Read-only sessions are enforced by the database where supported (PostgreSQL default_transaction_read_only, MySQL READ ONLY transactions).</p>
        </section>
      </div>
    </Dialog>
  )
}
