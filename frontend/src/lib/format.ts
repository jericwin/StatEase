import type { ColumnFmt, Level } from './types'

export type PStyle = 'apa' | 'academic'

/** p-values: three decimals, APA style drops the leading zero, values below .001 shown as "< .001". */
export function formatP(p: number | null | undefined, style: PStyle = 'apa', withSymbol = false): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return '—'
  let s: string
  if (p < 0.001) s = style === 'apa' ? '< .001' : '< 0.001'
  else {
    s = p.toFixed(3)
    if (style === 'apa') s = p >= 1 ? '1.000' : s.replace(/^0/, '')
  }
  if (!withSymbol) return s
  return s.startsWith('<') ? `p ${s}` : `p = ${s}`
}

export function formatR(r: number, decimals = 2, style: PStyle = 'apa'): string {
  const s = r.toFixed(decimals)
  return style === 'apa' ? s.replace(/^(-?)0\./, '$1.') : s
}

export function formatNumber(v: number, decimals = 2): string {
  if (!Number.isFinite(v)) return '—'
  return v.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

export function formatValue(v: unknown, fmt: ColumnFmt, decimals = 2, style: PStyle = 'apa'): string {
  if (v === null || v === undefined || v === '') return fmt === 'p' ? '—' : ''
  if (typeof v !== 'number') return String(v)
  if (!Number.isFinite(v)) return v > 0 ? '∞' : v < 0 ? '−∞' : '—'
  switch (fmt) {
    case 'int':
      return Math.round(v).toLocaleString('en-US')
    case 'p':
      return formatP(v, style)
    case 'pct':
      return v.toFixed(1)
    case 'r':
      return formatR(v, decimals, style)
    case 'text':
      return String(v)
    default:
      return formatNumber(v, decimals)
  }
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(2)} GB`
}

export function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} d ago`
  return formatDate(iso)
}

export const LEVEL_LABEL: Record<Level, string> = {
  numeric: 'Numeric',
  ordinal: 'Ordinal',
  nominal: 'Nominal',
  binary: 'Binary',
  date: 'Date',
  datetime: 'Date & time',
  text: 'Text',
  identifier: 'Identifier',
}

export const LEVEL_HELP: Record<Level, string> = {
  numeric: 'Measured quantity where differences are meaningful (age, income, score).',
  ordinal: 'Ordered categories or ratings (Likert scales, year level).',
  nominal: 'Unordered categories (program, region).',
  binary: 'Exactly two categories (yes/no, male/female).',
  date: 'Calendar date.',
  datetime: 'Date and time.',
  text: 'Free text; not used in analyses.',
  identifier: 'ID or record number; excluded from analyses.',
}

export const LEVELS: Level[] = ['numeric', 'ordinal', 'nominal', 'binary', 'date', 'datetime', 'text', 'identifier']

export function pluralize(n: number, word: string, plural?: string) {
  return `${n.toLocaleString('en-US')} ${n === 1 ? word : (plural ?? `${word}s`)}`
}
