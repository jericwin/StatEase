import { useState } from 'react'
import { PageBody, PageHeader } from '@/components/layout/AppShell'
import { Skeleton } from '@/components/ui/feedback'
import { Input } from '@/components/ui/form'
import { LEVEL_LABEL } from '@/lib/format'
import { useCatalog } from '@/lib/queries'

/** Methods guide generated from the analysis registry, so it always matches what is implemented. */
export default function HelpPage() {
  const catalog = useCatalog()
  const [q, setQ] = useState('')
  const term = q.toLowerCase()
  return (
    <>
      <PageHeader title="Methods guide" description="Every analysis available in StatEase: what it answers, what it needs, and how it is computed." />
      <PageBody className="max-w-5xl">
        <Input placeholder="Search analyses" value={q} onChange={(e) => setQ(e.target.value)} className="mb-5 max-w-sm" aria-label="Search analyses" />
        {catalog.isLoading && <Skeleton className="h-96" />}
        {catalog.data?.categories.map((cat) => {
          const list = catalog.data.analyses.filter(
            (a) => a.category === cat.id && (!term || `${a.name} ${a.plain_name} ${a.description}`.toLowerCase().includes(term)),
          )
          if (!list.length) return null
          return (
            <section key={cat.id} className="mb-8">
              <h2 className="mb-3 border-b border-line pb-1.5 text-[15px] font-semibold">{cat.name}</h2>
              <div className="space-y-4">
                {list.map((a) => (
                  <article key={a.id} id={a.id} className="rounded-lg border border-line bg-surface p-4 text-[13px]">
                    <h3 className="text-[14px] font-semibold">{a.name}</h3>
                    <p className="text-muted">{a.plain_name}</p>
                    <p className="mt-2">{a.description}</p>
                    {a.when_to_use && <p className="mt-1"><span className="font-medium">When to use: </span>{a.when_to_use}</p>}
                    <dl className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-[140px_1fr]">
                      <dt className="text-muted">Variables</dt>
                      <dd>
                        <ul className="space-y-0.5">
                          {a.roles.map((r) => (
                            <li key={r.key}>
                              <span className="font-medium">{r.label}</span> — {r.levels.map((l) => LEVEL_LABEL[l]).join(' / ')}
                              {r.max === 1 ? ', one variable' : `, ${r.min}${r.max ? `–${r.max}` : '+'} variables`}
                              {r.min === 0 && ' (optional)'}
                            </li>
                          ))}
                        </ul>
                      </dd>
                      {a.assumptions.length > 0 && (
                        <>
                          <dt className="text-muted">Assumptions</dt>
                          <dd>{a.assumptions.join(' ')}</dd>
                        </>
                      )}
                      <dt className="text-muted">Calculation</dt>
                      <dd>{a.method}</dd>
                      <dt className="text-muted">Missing data</dt>
                      <dd>{a.missing_data}</dd>
                      {a.limitations.length > 0 && (
                        <>
                          <dt className="text-muted">Limitations</dt>
                          <dd>{a.limitations.join(' ')}</dd>
                        </>
                      )}
                      {a.references.length > 0 && (
                        <>
                          <dt className="text-muted">References</dt>
                          <dd className="text-xs text-fg-2">{a.references.join(' ')}</dd>
                        </>
                      )}
                    </dl>
                  </article>
                ))}
              </div>
            </section>
          )
        })}
      </PageBody>
    </>
  )
}
