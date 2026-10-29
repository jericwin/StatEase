/**
 * Presentation edits for report tables and charts. Mirrors backend/app/reports/blocks.py exactly, so the
 * live preview matches the exported document. Values are never altered except by explicit manual cells,
 * which are flagged and footnoted.
 */
import type { ChartSpec, ChartStyle, ResultColumn, ResultRow, ResultTable } from './types'

export const MANUAL_NOTE = '† Value entered manually; not computed by StatEase.'
const DETAIL_GROUPS = new Set(['statistic', 'df', 'ci', 'effect'])

export interface ColumnEdit {
  key: string
  label?: string
  hidden?: boolean
  manual?: boolean
}

export interface TableEdits {
  columns?: ColumnEdit[]
  hidden_rows?: number[]
  cells?: Record<string, unknown>
  extra_rows?: Record<string, unknown>[]
  notes?: string | null
}

export interface ChartEdits {
  type?: string
  style?: ChartStyle
  x_label?: string
  y_label?: string
  caption?: string
  hidden?: string[]
  order?: string[]
  labels?: Record<string, string>
}

export type ManualRow = ResultRow & { _manual?: string[] }

export function resolveTable(source: ResultTable, edits: TableEdits | undefined, hideDetails = false): ResultTable & { rows: ManualRow[] } {
  const e = edits ?? {}
  const src = new Map(source.columns.map((c) => [c.key, c]))
  const ordered: (ResultColumn & { hidden?: boolean; manual?: boolean })[] = []
  const seen = new Set<string>()
  for (const ce of e.columns ?? []) {
    let c: ResultColumn & { hidden?: boolean; manual?: boolean }
    if (src.has(ce.key)) c = { ...src.get(ce.key)! }
    else if (ce.manual) c = { key: ce.key, label: ce.label || 'New column', fmt: 'text', manual: true }
    else continue
    if (ce.label) c.label = ce.label
    c.hidden = !!ce.hidden
    ordered.push(c)
    seen.add(ce.key)
  }
  for (const c of source.columns) if (!seen.has(c.key)) ordered.push({ ...c, hidden: false })
  const cols = ordered.filter((c) => !c.hidden && !(hideDetails && c.group && DETAIL_GROUPS.has(c.group)))
  const hidden = new Set(e.hidden_rows ?? [])
  const cells = e.cells ?? {}
  let anyManual = false
  const rows: ManualRow[] = []
  source.rows.forEach((r, i) => {
    if (hidden.has(i)) return
    const row: ManualRow = { ...r }
    const manual: string[] = []
    for (const c of cols) {
      const k = `${i}:${c.key}`
      if (k in cells) {
        row[c.key] = cells[k]
        manual.push(c.key)
      } else if ((c as { manual?: boolean }).manual) row[c.key] = null
    }
    if (manual.length) {
      row._manual = manual
      anyManual = true
    }
    rows.push(row)
  })
  for (const extra of e.extra_rows ?? []) {
    rows.push({ ...Object.fromEntries(cols.map((c) => [c.key, extra[c.key] ?? null])), _manual: cols.map((c) => c.key) })
    anyManual = true
  }
  const notes = e.notes === undefined || e.notes === null ? [...source.notes] : e.notes ? [e.notes] : []
  if (anyManual) notes.push(MANUAL_NOTE)
  return { ...source, columns: cols.map(({ hidden: _h, ...c }) => c), rows, notes }
}

type D = Record<string, unknown>
interface Series {
  name: string
  values: (number | null)[]
  lower?: (number | null)[]
  upper?: (number | null)[]
}

export function chartTypes(spec: ChartSpec): string[] {
  if (spec.type === 'meanci') return ['meanci', 'means']
  if (spec.type === 'means') return ['means', 'bar', ...(((spec.data.series as Series[]) ?? []).length === 1 ? ['meanci'] : [])]
  return [spec.type]
}

function convert(spec: ChartSpec, target: string): ChartSpec {
  const d = spec.data as D
  if (spec.type === 'meanci' && target === 'means') {
    const groups = ((d.groups as D[]) ?? []).filter((g) => g.mean !== null && g.mean !== undefined)
    return { ...spec, type: 'means' as ChartSpec['type'], data: { categories: groups.map((g) => g.name), series: [{ name: spec.y_label || 'Mean', values: groups.map((g) => g.mean), lower: groups.map((g) => g.lower ?? null), upper: groups.map((g) => g.upper ?? null) }] } }
  }
  if (spec.type === 'means' && target === 'meanci' && ((d.series as Series[]) ?? []).length === 1) {
    const s = (d.series as Series[])[0]
    return { ...spec, type: 'meanci', data: { groups: ((d.categories as string[]) ?? []).map((c, i) => ({ name: c, mean: s.values[i], lower: s.lower?.[i] ?? null, upper: s.upper?.[i] ?? null })) } }
  }
  if (spec.type === 'means' && target === 'bar') {
    return { ...spec, type: 'bar', data: { categories: d.categories, series: ((d.series as Series[]) ?? []).map((s) => ({ name: s.name, values: s.values })) } }
  }
  return spec
}

export function resolveChart(source: ChartSpec, edits: ChartEdits | undefined, title?: string | null): ChartSpec {
  const e = edits ?? {}
  let spec: ChartSpec = JSON.parse(JSON.stringify(source))
  if (e.type && chartTypes(spec).includes(e.type)) spec = convert(spec, e.type)
  if (e.x_label !== undefined && e.x_label !== null) spec.x_label = e.x_label
  if (e.y_label !== undefined && e.y_label !== null) spec.y_label = e.y_label
  if (e.caption !== undefined && e.caption !== null) spec.caption = e.caption
  if (title) spec.title = title
  const hidden = new Set(e.hidden ?? [])
  const order = e.order ?? []
  const labels = e.labels ?? {}
  const rank = (n: string) => (order.includes(n) ? order.indexOf(n) : order.length + 1)
  const d = spec.data as D
  if (spec.type === 'box' || spec.type === 'meanci') {
    const groups = ((d.groups as D[]) ?? []).filter((g) => !hidden.has(String(g.name)))
    groups.sort((a, b) => rank(String(a.name)) - rank(String(b.name)))
    d.groups = groups.map((g) => ({ ...g, name: labels[String(g.name)] ?? g.name }))
  } else if (['means', 'bar', 'interaction'].includes(spec.type)) {
    const cats = (d.categories as string[]) ?? []
    const keep = cats.map((_, i) => i).filter((i) => !hidden.has(cats[i])).sort((a, b) => rank(cats[a]) - rank(cats[b]))
    d.categories = keep.map((i) => labels[cats[i]] ?? cats[i])
    const series = ((d.series as Series[]) ?? [])
      .filter((s) => !hidden.has(s.name))
      .map((s) => ({
        ...s,
        name: labels[s.name] ?? s.name,
        values: keep.map((i) => s.values[i]),
        ...(s.lower ? { lower: keep.map((i) => s.lower![i]) } : {}),
        ...(s.upper ? { upper: keep.map((i) => s.upper![i]) } : {}),
      }))
    series.sort((a, b) => rank(a.name) - rank(b.name))
    d.series = series
  }
  return withStyle(spec, e.style)
}

export const CHART_STYLE_LABEL: Record<ChartStyle, string> = { bar: 'Bar', hbar: 'Horizontal bar', line: 'Line', dot: 'Dot plot', stacked: 'Stacked bar', pie: 'Pie' }

/** How a category chart may be drawn (same rules as the server). Stacked and pie only for counts/percentages, never means. */
export function chartStyles(spec: ChartSpec): ChartStyle[] {
  if (!['means', 'bar', 'interaction', 'meanci'].includes(spec.type)) return []
  const styles: ChartStyle[] = ['bar', 'hbar', 'line', 'dot']
  if (spec.type === 'bar') {
    const series = ((spec.data as D).series as Series[]) ?? []
    if (series.length > 1) styles.push('stacked')
    if (series.length === 1 && series[0].values.every((v) => (v ?? 0) >= 0)) styles.push('pie')
  }
  return styles
}

/** The style a chart is drawn in when the user has not picked one. */
export function defaultStyle(spec: ChartSpec): ChartStyle | undefined {
  if (spec.style) return spec.style
  if (spec.type === 'interaction') return 'line'
  if (spec.type === 'meanci') return 'dot'
  if (spec.type === 'bar') return (spec.data as D).stacked ? 'stacked' : 'bar'
  if (spec.type === 'means') return 'bar'
  return undefined
}

export function withStyle(spec: ChartSpec, style: ChartStyle | undefined): ChartSpec {
  if (!style || !chartStyles(spec).includes(style)) return spec
  if (spec.type === 'meanci') {
    if (style === 'dot') return spec
    spec = convert(spec, 'means')
  }
  return { ...spec, style }
}

export function chartNames(spec: ChartSpec): { groups: string[]; series: string[] } {
  const d = spec.data as D
  if (spec.type === 'box' || spec.type === 'meanci') return { groups: ((d.groups as D[]) ?? []).map((g) => String(g.name)), series: [] }
  if (['means', 'bar', 'interaction'].includes(spec.type))
    return { groups: (d.categories as string[]) ?? [], series: ((d.series as Series[]) ?? []).map((s) => s.name) }
  return { groups: [], series: [] }
}
