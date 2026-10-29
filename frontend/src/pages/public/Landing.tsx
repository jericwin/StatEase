import { useQueries, useQuery } from '@tanstack/react-query'
import { ArrowRight, ArrowUpRight, Check, GitCompareArrows, Sprout, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import { formatP } from '@/lib/format'
import type { DemoPreview } from '@/lib/types'
import { PublicLayout } from './PublicLayout'
import { focusMeans, type Means, MiniMeans, PaperTable } from './visuals'

export const DEMO_META: Record<string, { icon: typeof Sprout; blurb: string; field: string }> = {
  fertilizer: { icon: Sprout, field: 'Agriculture · Field experiment', blurb: 'Pechay grown with no fertilizer, vermicompost or inorganic fertilizer, compared on four growth measures.' },
  experiment: { icon: GitCompareArrows, field: 'Education · Intervention study', blurb: 'A control and a treatment group, tested before and after an intervention.' },
  survey: { icon: Users, field: 'Business · Customer survey', blurb: 'Respondent profile, Likert scales and how service quality relates to satisfaction.' },
}

function meansOf(d?: DemoPreview): Means | null {
  const c = d?.results[0]?.charts.find((x) => x.type === 'means')
  const m = c ? (c.data as unknown as Means) : null
  // Measures on different scales (height, leaves, weight) are shown one at a time.
  return d?.key === 'fertilizer' ? focusMeans(m, 'Fresh Weight (g)') : m
}

/* ------------------------------------------------------------------ hero composition */

function DocumentStack() {
  const demo = useQuery({ queryKey: ['public-demo', 'fertilizer'], queryFn: () => api.get<DemoPreview>('/public/demos/fertilizer'), staleTime: Infinity })
  const d = demo.data
  const main = d?.results[0]?.tables.find((t) => t.id === 'main')
  const desc = d?.results[0]?.tables.find((t) => t.id === 'desc')
  const means = meansOf(d)
  const weight = main?.rows.find((r) => r.measure === 'Fresh Weight (g)')
  return (
    <div className="relative mx-auto h-[480px] w-full max-w-[500px] sm:h-[520px]" aria-label="Example output from the fertilizer demo">
      {/* the spreadsheet */}
      <div className="animate-in absolute top-0 left-0 w-[60%] sm:w-[62%] -rotate-[4deg] rounded-md border border-paper-line bg-surface shadow-[0_18px_40px_-24px_rgba(20,33,58,0.5)]" style={{ animationDelay: '60ms' }}>
        <div className="flex items-center justify-between border-b border-paper-line px-3 py-1.5">
          <span className="font-mono text-[10.5px] text-ink-2">pechay_trial.xlsx</span>
          <span className="font-mono text-[10px] text-ink-2/70">{d?.n_rows ?? '…'} rows</span>
        </div>
        <table className="w-full font-mono text-[10px] text-ink-2">
          <tbody>
            {(d?.rows ?? []).slice(0, 6).map((r, i) => (
              <tr key={i} className="border-b border-paper-line/70 last:border-0">
                {r.slice(1, 5).map((v, j) => (
                  <td key={j} className="px-2 py-1 whitespace-nowrap">{String(v)}</td>
                ))}
              </tr>
            ))}
            {!d && Array.from({ length: 6 }).map((_, i) => <tr key={i}><td className="h-5 px-2"><div className="h-2 w-full rounded bg-paper-2" /></td></tr>)}
          </tbody>
        </table>
      </div>

      {/* the report page */}
      <div className="animate-in absolute top-4 right-0 w-[92%] sm:w-[78%] rotate-[1.5deg] rounded-[3px] bg-white px-4 pt-4 pb-4 sm:px-6 sm:pt-5 sm:pb-4 shadow-[0_24px_60px_-24px_rgba(20,33,58,0.5)] ring-1 ring-black/5 sm:top-6" style={{ animationDelay: '160ms' }}>
        <div className="mb-2 flex items-center justify-between font-serif text-[10px] text-[#6b6f78]">
          <span>Chapter 4 · Results</span>
          <span>12</span>
        </div>
        {main && desc ? <PaperTable main={main} desc={desc} groups={['Control', 'Vermicompost', 'Inorganic']} caption="Growth of pechay by fertilizer treatment" number={2} /> : <div className="h-32 animate-pulse rounded bg-[#f1efea]" />}
        {means && (
          <figure className="mt-2.5">
            <div className="font-serif text-[11px] leading-tight text-[#17191e]">
              <span className="font-semibold">Figure 1</span>
              <span className="block italic">Mean fresh weight (g) by treatment, with 95% CIs</span>
            </div>
            <div className="mt-1 [--ink-2:#7b8496] [--ink:#14213a] [--paper-line:#ece8df] [--rust:#b4532a]">
              <MiniMeans categories={means.categories} series={means.series} height={96} />
            </div>
          </figure>
        )}
      </div>

      {/* margin note */}
      {weight && (
        <div className="animate-in absolute bottom-4 left-0 hidden w-[104px] -rotate-[3deg] sm:block" style={{ animationDelay: '320ms' }}>
          <p className="font-serif text-[13.5px] leading-tight text-rust italic">
            Vermicompost: heaviest plants
            <span className="mt-0.5 block not-italic tabular-nums">p {formatP(Number(weight.p)).startsWith('<') ? '' : '= '}{formatP(Number(weight.p))}</span>
          </p>
          <svg viewBox="0 0 110 36" className="mt-1 h-8 w-[104px] text-rust" aria-hidden>
            <path d="M4 4 C 30 30, 70 30, 104 14" fill="none" stroke="currentColor" strokeWidth="1.2" />
            <path d="M96 12 L105 13 L100 21" fill="none" stroke="currentColor" strokeWidth="1.2" />
          </svg>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ method fragments */

function UploadFragment() {
  return (
    <div className="rounded-md border border-dashed border-ink-2/40 bg-surface/60 p-3 text-[12px]">
      <div className="flex items-center justify-between font-mono text-[11px]">
        <span>survey_2026.xlsx</span>
        <span className="text-ink-2">Sheet 1</span>
      </div>
      <div className="mt-2 h-1 rounded-full bg-paper-line"><div className="h-1 w-full rounded-full bg-ink" /></div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {[['Gender', 'group'], ['Program', 'group'], ['Satisfaction', 'score'], ['Age', 'number']].map(([n, t]) => (
          <span key={n} className="rounded-full border border-paper-line bg-paper px-2 py-0.5 text-[11px]">
            {n} <span className="text-ink-2">· {t}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

function CompareFragment() {
  return (
    <div className="rounded-md border border-paper-line bg-surface/60 p-3 text-[12px]">
      <div className="flex flex-wrap gap-1.5">
        {['Control', 'Vermicompost', 'Inorganic'].map((f) => (
          <span key={f} className="inline-flex items-center gap-1 rounded-full bg-ink px-2.5 py-0.5 text-[11px] text-paper"><Check className="size-3" />{f}</span>
        ))}
      </div>
      <p className="mt-3 leading-snug text-ink-2"><span className="font-medium text-ink">One-way ANOVA</span> with Tukey post hoc tests, chosen per measure — three independent groups.</p>
    </div>
  )
}

function ExportFragment() {
  return (
    <div className="rounded-md border border-paper-line bg-surface/60 p-3 text-[12px]">
      {['Table 1 · Growth by treatment', 'Table 2 · Comparison of treatments', 'Figure 1 · Mean fresh weight'].map((t, i) => (
        <div key={t} className="flex items-center gap-2 py-0.5">
          <span className={`flex size-3.5 items-center justify-center rounded-[3px] ${i < 3 ? 'bg-ink text-paper' : 'border border-ink-2'}`}><Check className="size-2.5" /></span>
          <span className="truncate">{t}</span>
        </div>
      ))}
      <div className="mt-2.5 grid grid-cols-2 gap-1.5 text-center text-[11px] font-medium">
        <span className="rounded bg-ink py-1 text-paper">Word .docx</span>
        <span className="rounded border border-ink/25 py-1">Excel .xlsx</span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ page */

const REFERENCE = [
  ['Welch t-test, sleep data', 't', '−1.8608', 'df 17.776 · p .0794'],
  ['Paired t-test, sleep data', 't', '−4.0621', 'p .00283'],
  ['One-way ANOVA, PlantGrowth', 'F', '4.8461', 'p .0159'],
  ['Tukey HSD, trt2 − trt1', 'p', '.0120', 'adjusted'],
  ['Pearson correlation, cars', 'r', '.8069', 'CI .682, .886'],
  ['Chi-square, Agresti (2007)', 'χ²', '30.07', 'df 2'],
]

export default function Landing() {
  const previews = useQueries({
    queries: ['fertilizer', 'experiment', 'survey'].map((k) => ({ queryKey: ['public-demo', k], queryFn: () => api.get<DemoPreview>(`/public/demos/${k}`), staleTime: Infinity })),
  })
  const steps = [
    { title: 'Upload your file', text: 'Excel or CSV. Columns are read, typed and checked — groups, scores and ID columns are recognised, missing values reported.', ui: <UploadFragment /> },
    { title: 'Accept a comparison', text: 'Pick the groups or take the suggestion. The test is chosen from your data and its assumptions are checked in plain language.', ui: <CompareFragment /> },
    { title: 'Export the chapter', text: 'Your objectives become sections. Rename, reorder and edit tables and figures, then download Word or Excel.', ui: <ExportFragment /> },
  ]
  return (
    <PublicLayout>
      {/* ---------------------------------------------------------------- hero */}
      <section className="relative overflow-hidden">
        <div className="mx-auto grid max-w-6xl items-center gap-14 px-5 pt-14 pb-20 sm:px-8 lg:grid-cols-[1.02fr_1fr] lg:pt-20 lg:pb-28">
          <div className="animate-in">
            <p className="kicker">Statistics for research reports</p>
            <h1 className="display mt-5 text-[44px] leading-[1.02] sm:text-[64px]">
              From spreadsheet to <em className="font-normal text-rust italic">results chapter</em>.
            </h1>
            <p className="mt-6 max-w-[30rem] text-[17px] leading-relaxed text-ink-2">
              Upload your data, accept the recommended comparison, and download editable Word and Excel tables — with the right test, checked
              assumptions and a plain-language interpretation.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-x-6 gap-y-4">
              <Link to="/signup" className="inline-flex h-12 items-center gap-2 rounded-full bg-ink px-6 text-[15px] font-medium text-paper transition-transform hover:-translate-y-0.5">
                Start analyzing <ArrowRight className="size-4" />
              </Link>
              <Link to="/demo/fertilizer" className="group inline-flex items-center gap-1.5 text-[15px] font-medium text-ink underline decoration-ink/30 underline-offset-[6px] hover:decoration-ink">
                See a worked example <ArrowUpRight className="size-4 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
              </Link>
            </div>
            <dl className="mt-12 grid max-w-md grid-cols-3 gap-6 border-t border-paper-line pt-6">
              {[['29', 'statistical procedures'], ['0', 'lines of code needed'], ['.docx', 'and .xlsx, editable']].map(([n, l]) => (
                <div key={l}>
                  <dt className="display text-[26px] leading-none">{n}</dt>
                  <dd className="mt-1.5 text-[12.5px] leading-snug text-ink-2">{l}</dd>
                </div>
              ))}
            </dl>
          </div>
          <DocumentStack />
        </div>
      </section>

      {/* ---------------------------------------------------------------- method */}
      <section id="method" className="border-t border-paper-line bg-paper-2/60">
        <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-24">
          <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr] lg:items-end">
            <h2 className="display text-[34px] leading-tight sm:text-[42px]">The whole workflow<br className="hidden sm:block" /> fits on one page.</h2>
            <p className="max-w-lg text-[15.5px] leading-relaxed text-ink-2 lg:justify-self-end">No menus of tests to memorise. StatEase reads the structure of your data and proposes the comparisons a reviewer would expect.</p>
          </div>
          <ol className="mt-14 grid gap-12 md:grid-cols-3 md:gap-8">
            {steps.map((s, i) => (
              <li key={s.title} className="flex flex-col">
                <div className="flex items-baseline gap-3 border-b border-ink pb-3">
                  <span className="display text-[40px] leading-none text-rust">{i + 1}</span>
                  <h3 className="text-[17px] font-semibold">{s.title}</h3>
                </div>
                <p className="mt-4 flex-1 text-[14.5px] leading-relaxed text-ink-2">{s.text}</p>
                <div className="mt-6">{s.ui}</div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ---------------------------------------------------------------- examples */}
      <section id="examples" className="border-t border-paper-line">
        <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-24">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="kicker">Worked examples</p>
              <h2 className="display mt-3 text-[34px] leading-tight sm:text-[42px]">Open a study. No sign-in.</h2>
            </div>
            <p className="max-w-sm text-[14.5px] text-ink-2">Each example has a small fictional dataset, its objectives, and the finished tables and charts.</p>
          </div>
          <div className="mt-12 grid gap-px overflow-hidden rounded-lg border border-paper-line bg-paper-line md:grid-cols-3">
            {(['fertilizer', 'experiment', 'survey'] as const).map((key, i) => {
              const d = previews[i].data
              const m = meansOf(d)
              const main = d?.results[0]?.tables.find((t) => t.id === 'main')
              const sig = main?.rows.filter((r) => Number(r.p) < 0.05).length ?? 0
              return (
                <Link key={key} to={`/demo/${key}`} className="group flex flex-col bg-paper p-7 transition-colors hover:bg-surface">
                  <p className="kicker">{DEMO_META[key].field}</p>
                  <h3 className="display mt-3 text-[23px] leading-snug group-hover:underline group-hover:decoration-rust group-hover:decoration-1 group-hover:underline-offset-4">{d?.title ?? '…'}</h3>
                  <p className="mt-2 text-[14px] leading-relaxed text-ink-2">{DEMO_META[key].blurb}</p>
                  <div className="mt-6 flex-1">
                    {m ? <MiniMeans categories={m.categories.map((c) => c.split(' ')[0])} series={m.series} height={104} /> : <div className="h-[104px] rounded bg-paper-2" />}
                  </div>
                  <div className="mt-5 flex items-center justify-between border-t border-paper-line pt-4 text-[12.5px] text-ink-2">
                    <span>n = {d?.n_rows ?? '…'} · {sig} significant {sig === 1 ? 'difference' : 'differences'}</span>
                    <span className="inline-flex items-center gap-1 font-medium text-ink">Open <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" /></span>
                  </div>
                </Link>
              )
            })}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- accuracy */}
      <section id="accuracy" className="bg-ink text-paper [--ink:#14213a] [--paper:#f4efe4] [--rust:#e3916b] dark:[--ink:#18243a]">
        <div className="mx-auto grid max-w-6xl gap-14 px-5 py-20 sm:px-8 lg:grid-cols-[1fr_1.15fr] lg:py-24">
          <div>
            <p className="font-sans text-[11px] font-semibold tracking-[0.16em] text-paper/60 uppercase">Accuracy</p>
            <h2 className="display mt-3 text-[34px] leading-tight sm:text-[42px]">Numbers you can defend in your oral exam.</h2>
            <p className="mt-5 max-w-md text-[15.5px] leading-relaxed text-paper/70">
              Every statistic is computed with SciPy and statsmodels and checked against published R output in the test suite. Interpretations are
              written from the computed values by fixed rules — nothing is generated or guessed.
            </p>
            <ul className="mt-8 space-y-2.5 text-[14.5px] text-paper/85">
              {['Assumptions checked and explained, never silently swapped', 'Effect sizes and confidence intervals reported', 'Reproducible Python code for every result'].map((t) => (
                <li key={t} className="flex gap-2.5"><Check className="mt-0.5 size-4 shrink-0 text-rust" />{t}</li>
              ))}
            </ul>
          </div>
          <div className="self-center rounded-lg border border-paper/15 bg-paper/[0.04] p-1">
            <table className="w-full text-[13px]">
              <caption className="px-4 pt-3 pb-2 text-left text-[12px] text-paper/60">Reference values reproduced by the StatEase test suite</caption>
              <thead>
                <tr className="text-[11px] tracking-wider text-paper/55 uppercase">
                  <th className="px-4 py-2 text-left font-medium">Check (R dataset)</th>
                  <th className="px-2 py-2 text-right font-medium">Statistic</th>
                  <th className="hidden px-4 py-2 text-right font-medium sm:table-cell">Also matched</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {REFERENCE.map(([name, sym, val, extra]) => (
                  <tr key={name} className="border-t border-paper/10">
                    <td className="px-4 py-2.5 font-sans text-paper/85">{name}</td>
                    <td className="px-2 py-2.5 text-right whitespace-nowrap"><span className="font-serif text-paper/55 italic">{sym}</span> = {val}</td>
                    <td className="hidden px-4 py-2.5 text-right text-paper/55 sm:table-cell">{extra}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- what you get */}
      <section className="border-b border-paper-line">
        <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-24">
          <h2 className="display max-w-xl text-[34px] leading-tight sm:text-[42px]">Made for the way results chapters are written.</h2>
          <dl className="mt-12 grid gap-x-14 sm:grid-cols-2">
            {[
              ['Objectives become sections', 'Paste your objectives; each one gets its tables, figure and interpretation, in order.'],
              ['Tables you can still edit', 'Rename, reorder, hide rows or columns. Switch Control to Vermicompost and the values recalculate.'],
              ['The right comparison', 'Independent, paired and multi-group designs are handled correctly, with corrected post hoc tests.'],
              ['Typed values are marked', 'Anything you enter by hand is flagged with a dagger, so computed and manual numbers never mix.'],
              ['APA-style output', 'Numbered tables and figures, p < .001 notation, effect sizes and notes, ready to paste.'],
              ['Your data stays yours', 'Projects are private to your account and can be deleted at any time.'],
            ].map(([t, d]) => (
              <div key={t} className="border-t border-paper-line py-5">
                <dt className="display text-[18px]">{t}</dt>
                <dd className="mt-1.5 text-[14.5px] leading-relaxed text-ink-2">{d}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ---------------------------------------------------------------- closing */}
      <section>
        <div className="mx-auto flex max-w-6xl flex-col items-start gap-8 px-5 py-20 sm:px-8 md:flex-row md:items-end md:justify-between lg:py-24">
          <h2 className="display max-w-2xl text-[40px] leading-[1.05] sm:text-[56px]">
            Write the results, <em className="font-normal text-rust italic">not the code.</em>
          </h2>
          <Link to="/signup" className="inline-flex h-12 shrink-0 items-center gap-2 rounded-full bg-ink px-6 text-[15px] font-medium text-paper transition-transform hover:-translate-y-0.5">
            Create a free account <ArrowRight className="size-4" />
          </Link>
        </div>
      </section>
    </PublicLayout>
  )
}
