import { ChartView } from '@/features/results/ChartView'
import { StatTable } from '@/features/results/StatTable'
import { resolveChart, resolveTable, type ChartEdits, type TableEdits } from '@/lib/blocks'
import type { PStyle } from '@/lib/format'
import type { ChartSpec, Report, ReportBlock, ResultTable } from '@/lib/types'
import { cn } from '@/lib/utils'

export function tableOf(b: ReportBlock, hideDetails: boolean): ResultTable | null {
  if (!b.source_table) return null
  const t = resolveTable(b.source_table, b.edits as TableEdits, hideDetails)
  return { ...t, title: b.title || t.title }
}

export function chartOf(b: ReportBlock): ChartSpec | null {
  if (!b.source_chart) return null
  return resolveChart(b.source_chart, b.edits as ChartEdits, b.title)
}

export function blockText(b: ReportBlock): string {
  if (b.type === 'heading') return b.text ?? b.resolved_text ?? ''
  if (b.type === 'text') return b.text ?? b.resolved_text ?? ''
  return b.title ?? ''
}

/** Table/figure numbers for included blocks, in document order. */
export function numbering(blocks: ReportBlock[]): Record<string, string> {
  let t = 0
  let f = 0
  const out: Record<string, string> = {}
  for (const b of blocks) {
    if (!b.include || b.missing) continue
    if (b.type === 'table') out[b.id] = `Table ${++t}`
    if (b.type === 'chart') out[b.id] = `Figure ${++f}`
  }
  return out
}

export function ReportDocument({
  report,
  blocks,
  selected,
  onSelect,
  onBlockChange,
}: {
  report: Report
  blocks: ReportBlock[]
  selected?: string | null
  onSelect?: (id: string) => void
  /** When given, a chart's style can be switched right on the page and is saved with the report. */
  onBlockChange?: (b: ReportBlock) => void
}) {
  const style = (report.options.style ?? 'apa') as PStyle
  const decimals = report.options.decimals ?? 2
  const hideDetails = report.options.include_details === false
  const nums = numbering(blocks)
  const included = blocks.filter((b) => b.include && !b.missing)
  const objectives = report.objectives.filter((o) => o.text)
  return (
    <div className="mx-auto w-full max-w-[816px] rounded-sm border border-line bg-white px-6 py-10 text-[#16181d] shadow-[0_10px_40px_-20px_rgba(16,28,46,0.35)] sm:px-14 sm:py-14 dark:[color-scheme:light]">
      <div style={style === 'apa' ? { fontFamily: '"Times New Roman", Times, serif' } : undefined} className="[--accent-soft:#eaf1fa] [--bg:#fff] [--border:#d8dce3] [--border-strong:#c3c9d2] [--muted:#5d6675] [--surface-2:#f6f7f9] [--surface-3:#eef0f3] [--surface:#fff] [--text-2:#2f3642] [--text:#16181d]">
        <h1 className="text-center text-[22px] font-bold">{report.title}</h1>
        {report.options.subtitle && <p className="mt-1 text-center text-[14px]">{report.options.subtitle}</p>}
        {objectives.length > 0 && (
          <section className="mt-8">
            <h2 className="text-[16px] font-bold">Objectives of the Study</h2>
            <ol className="mt-2 list-decimal space-y-1 pl-6 text-[14px]">
              {objectives.map((o) => <li key={o.id}>{o.text}</li>)}
            </ol>
          </section>
        )}
        {included.length === 0 && <p className="mt-10 text-center text-[14px] text-[#5d6675]">Nothing is selected. Tick items in the checklist to include them.</p>}
        <div className="mt-6 space-y-6">
          {included.map((b) => {
            const active = selected === b.id
            const wrap = (child: React.ReactNode) => (
              <div
                key={b.id}
                id={`block-${b.id}`}
                onClick={onSelect ? () => onSelect(b.id) : undefined}
                className={cn('-mx-3 rounded px-3 py-2 transition-colors', onSelect && 'cursor-pointer hover:bg-[#f3f6fb]', active && 'bg-[#eaf1fa] ring-1 ring-[#1d4f91]/40')}
              >
                {child}
              </div>
            )
            if (b.type === 'heading') return wrap(<h2 className="text-[17px] font-bold">{blockText(b)}</h2>)
            if (b.type === 'text') return wrap(<p className="text-[14.5px] leading-relaxed whitespace-pre-line">{blockText(b)}</p>)
            if (b.type === 'table') {
              const t = tableOf(b, hideDetails)
              if (!t) return null
              return wrap(
                <div className="text-[13px]">
                  <StatTable table={t} decimals={decimals} style={style} alpha={b.analysis?.settings?.alpha ?? 0.05} number={Number(nums[b.id]?.split(' ')[1])} showEmpty />
                </div>,
              )
            }
            const c = chartOf(b)
            if (!c) return null
            return wrap(
              <ChartView
                spec={c}
                number={Number(nums[b.id]?.split(' ')[1])}
                paper
                onStyleChange={onBlockChange ? (st) => onBlockChange({ ...b, edits: { ...(b.edits ?? {}), style: st } }) : undefined}
              />,
            )
          })}
        </div>
      </div>
    </div>
  )
}
