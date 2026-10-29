import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Badge, Callout, ErrorState, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/feedback'
import { ChartView } from '@/features/results/ChartView'
import { StatTable } from '@/features/results/StatTable'
import { api, errorMessage } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import type { DemoPreview } from '@/lib/types'
import { PublicLayout } from './PublicLayout'

export default function DemoPreviewPage() {
  const { key = 'fertilizer' } = useParams()
  const { user, config } = useAuth()
  const navigate = useNavigate()
  const [tab, setTab] = useState('results')
  const demo = useQuery({ queryKey: ['public-demo', key], queryFn: () => api.get<DemoPreview>(`/public/demos/${key}`), staleTime: Infinity })
  const open = useMutation({
    mutationFn: () => api.post<{ id: number }>('/demo', { key }),
    onSuccess: (p) => navigate(`/p/${p.id}/report`),
  })
  const signedIn = !!user || config?.mode === 'local'
  const d = demo.data
  return (
    <PublicLayout>
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <Link to="/#demos" className="inline-flex items-center gap-1 text-[13px] text-muted hover:text-fg"><ArrowLeft className="size-4" /> All demos</Link>
        {demo.isError && <div className="mt-6"><ErrorState error={demo.error} /></div>}
        {!d && !demo.isError && <Skeleton className="mt-6 h-96" />}
        {d && (
          <div className="animate-in">
            <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-[28px] font-semibold tracking-tight">{d.title}</h1>
                  <Badge tone="warning">Fictional sample data</Badge>
                </div>
                <p className="mt-1 text-[14.5px] text-fg-2">{d.summary}</p>
              </div>
              {signedIn ? (
                <Button variant="primary" size="lg" onClick={() => open.mutate()} loading={open.isPending}>Open in my workspace <ArrowRight /></Button>
              ) : (
                <Link to={`/signup?demo=${key}`}><Button variant="primary" size="lg">Try it with this data <ArrowRight /></Button></Link>
              )}
            </div>
            {open.isError && <Callout tone="danger" className="mt-3">{errorMessage(open.error)}</Callout>}
            <Tabs value={tab} onValueChange={setTab} className="mt-6">
              <TabsList>
                <TabsTrigger value="results">Results</TabsTrigger>
                <TabsTrigger value="data" count={d.n_rows}>Data</TabsTrigger>
                <TabsTrigger value="objectives" count={d.objectives.length}>Objectives</TabsTrigger>
              </TabsList>
              <TabsContent value="results" className="space-y-6 pt-5">
                {d.results.map((r, i) => {
                  const main = r.tables.find((t) => t.id === 'main') ?? r.tables[0]
                  const chart = r.charts.find((c) => c.type === 'means' || c.type === 'heatmap' || c.type === 'scatter') ?? r.charts[0]
                  return (
                    <section key={i} className="rounded-xl border border-line bg-surface p-5">
                      <h2 className="text-[16px] font-semibold">{r.heading || r.plain_title}</h2>
                      <p className="text-[13px] text-muted">{r.title}</p>
                      <p className="mt-3 rounded-md bg-surface-2 p-3 text-[14px] leading-relaxed">{r.interpretation.plain}</p>
                      <div className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
                        {main && <StatTable table={main} decimals={2} style="apa" alpha={0.05} />}
                        {chart && <ChartView spec={chart} />}
                      </div>
                    </section>
                  )
                })}
                <p className="text-[12.5px] text-muted">{d.note}</p>
              </TabsContent>
              <TabsContent value="data" className="pt-5">
                <div className="scroll-thin overflow-x-auto rounded-xl border border-line [contain:paint]">
                  <table className="w-full text-[13px]">
                    <thead className="bg-surface-2"><tr>{d.columns.map((c) => <th key={c} className="border-b border-line px-3 py-2 text-left font-semibold whitespace-nowrap">{c}</th>)}</tr></thead>
                    <tbody>{d.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className={`border-b border-line px-3 py-1.5 whitespace-nowrap ${typeof v === 'number' ? 'num text-right' : ''}`}>{v === null ? '—' : String(v)}</td>)}</tr>)}</tbody>
                  </table>
                </div>
                <p className="mt-2 text-[12.5px] text-muted">First {d.rows.length} of {d.n_rows} rows. <a className="text-accent hover:underline" href={`/api/v1/public/demos/${key}/sample.csv`}>Download the full sample CSV</a></p>
              </TabsContent>
              <TabsContent value="objectives" className="pt-5">
                <ol className="space-y-2 rounded-xl border border-line bg-surface p-5 text-[14px]">
                  {d.objectives.map((o, i) => <li key={i} className="flex gap-3"><span className="num font-semibold text-accent">{i + 1}.</span>{o}</li>)}
                </ol>
                <p className="mt-2 text-[12.5px] text-muted">In the workspace, these objectives are turned into a report with a table, chart and interpretation under each one.</p>
              </TabsContent>
            </Tabs>
          </div>
        )}
      </div>
    </PublicLayout>
  )
}
