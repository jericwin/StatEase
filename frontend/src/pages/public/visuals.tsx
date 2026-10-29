import { formatP } from '@/lib/format'
import type { ResultTable } from '@/lib/types'
import { cn } from '@/lib/utils'

interface Series {
  name: string
  values: (number | null)[]
  lower?: (number | null)[]
  upper?: (number | null)[]
}

/** Small grouped bar chart with CI whiskers, drawn in ink — used for figures in the editorial layout. */
export function MiniMeans({ categories, series, height = 120, max, className, labels = true }: {
  categories: string[]
  series: Series[]
  height?: number
  max?: number
  className?: string
  labels?: boolean
}) {
  const W = 300
  const H = height
  const bottom = labels ? 22 : 4
  const top = 6
  const vals = series.flatMap((s) => [...s.values, ...(s.upper ?? [])]).filter((v): v is number => typeof v === 'number')
  const hi = max ?? Math.ceil(Math.max(1, ...vals))
  const band = W / Math.max(categories.length, 1)
  const bw = Math.min(16, (band * 0.62) / Math.max(series.length, 1))
  const y = (v: number) => top + (H - top - bottom) * (1 - v / hi)
  const fills = ['fill-ink-2/45', 'fill-ink']
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={cn('w-full', className)} role="img" aria-label={`Bar chart of ${categories.join(', ')}`}>
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <line key={f} x1={0} x2={W} y1={y(hi * f)} y2={y(hi * f)} className="stroke-paper-line" strokeWidth={0.8} />
      ))}
      <line x1={0} x2={W} y1={y(0)} y2={y(0)} className="stroke-ink" strokeWidth={1} />
      {categories.map((c, i) => {
        const cx = band * i + band / 2
        return (
          <g key={c}>
            {series.map((s, si) => {
              const v = s.values[i]
              if (typeof v !== 'number') return null
              const x = cx + (si - (series.length - 1) / 2) * (bw + 3) - bw / 2
              const lo = s.lower?.[i]
              const up = s.upper?.[i]
              return (
                <g key={s.name}>
                  <rect x={x} y={y(v)} width={bw} height={y(0) - y(v)} className={fills[si % 2]} />
                  {typeof lo === 'number' && typeof up === 'number' && (
                    <g className="stroke-rust" strokeWidth={1}>
                      <line x1={x + bw / 2} x2={x + bw / 2} y1={y(up)} y2={y(lo)} />
                      <line x1={x + bw / 2 - 3} x2={x + bw / 2 + 3} y1={y(up)} y2={y(up)} />
                      <line x1={x + bw / 2 - 3} x2={x + bw / 2 + 3} y1={y(lo)} y2={y(lo)} />
                    </g>
                  )}
                </g>
              )
            })}
            {labels && (
              <text x={cx} y={H - 6} textAnchor="middle" className="fill-ink-2" style={{ font: '9px var(--font-sans)' }}>
                {c.length > 12 ? `${c.slice(0, 11)}…` : c}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}

export interface Means {
  categories: string[]
  series: Series[]
}

/** One measure of a "means" chart, re-shaped so each group becomes a bar. */
export function focusMeans(m: Means | null, measure: string): Means | null {
  const i = m?.categories.indexOf(measure) ?? -1
  if (!m || i < 0) return null
  return {
    categories: m.series.map((s) => s.name),
    series: [{ name: measure, values: m.series.map((s) => s.values[i]), lower: m.series.map((s) => s.lower?.[i] ?? null), upper: m.series.map((s) => s.upper?.[i] ?? null) }],
  }
}

/** An APA-style table set like a printed page: group means per measure and the p value of the test chosen for it. */
export function PaperTable({ main, desc, groups, caption, number }: { main: ResultTable; desc: ResultTable; groups: string[]; caption: string; number: number }) {
  const rows = main.rows.slice(0, 4)
  const mean = (measure: unknown, g: string) => desc.rows.find((r) => r.measure === measure && r.group === g)?.mean
  return (
    <figure className="font-serif text-[11px] leading-snug text-[#17191e]">
      <figcaption>
        <span className="font-semibold">Table {number}</span>
        <span className="block italic">{caption}</span>
      </figcaption>
      <table className="mt-1 w-full border-collapse text-[9px] sm:text-[10.5px]">
        <thead>
          <tr>
            {['Measure', ...groups, 'p'].map((h, i) => (
              <th key={h} className={cn('border-y border-[#17191e] px-1 py-0.5 font-normal whitespace-nowrap first:pl-0 last:pr-0', i ? 'text-right' : 'text-left', h === 'p' && 'italic')}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={i === rows.length - 1 ? 'border-b border-[#17191e]' : ''}>
              <td className="py-[2px] pr-1 pl-0 whitespace-nowrap">{String(r.measure).replace(/\s*\([^)]*\)$/, '')}</td>
              {groups.map((g) => <td key={g} className="px-1 text-right tabular-nums">{Number(mean(r.measure, g)).toFixed(1)}</td>)}
              <td className={cn('pr-0 pl-1 text-right whitespace-nowrap tabular-nums', Number(r.p) < 0.05 && 'font-semibold')}>{formatP(Number(r.p))}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-[9.5px] leading-tight text-ink-2"><span className="italic">Note.</span> Group means. One-way ANOVA or Kruskal–Wallis; fictional data.</p>
    </figure>
  )
}
