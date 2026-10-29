import { formatValue, type PStyle } from '@/lib/format'
import type { ResultTable } from '@/lib/types'
import { cn } from '@/lib/utils'

/** APA-style statistical table. Values keep full precision in data; rounding is display-only. */
export function StatTable({ table, decimals, style, alpha, number, showEmpty }: { table: ResultTable; decimals: number; style: PStyle; alpha: number; number?: number; showEmpty?: boolean }) {
  const cols = showEmpty ? table.columns : table.columns.filter((c) => c.fmt === 'text' || table.rows.some((r) => r[c.key] !== null && r[c.key] !== undefined && r[c.key] !== ''))
  return (
    <figure className="min-w-0">
      <figcaption className="mb-2 text-[13px]">
        {number !== undefined && <span className="font-semibold">Table {number}. </span>}
        <span className={cn(number !== undefined && 'italic')}>{table.title}</span>
      </figcaption>
      <div className="scroll-thin overflow-x-auto [contain:paint]">
        <table className="stat-table">
          <thead>
            <tr>
              {cols.map((c, i) => (
                <th key={c.key} scope="col" className={cn(c.fmt !== 'text' && 'text-right', i === 0 && 'sticky left-0 bg-surface')} title={c.help}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, ri) => (
              <tr key={ri} className={cn(row._style === 'total' && 'font-semibold', row._style === 'muted' && 'text-muted italic')}>
                {cols.map((c, i) => {
                  const v = row[c.key]
                  const sig = c.fmt === 'p' && typeof v === 'number' && v < alpha
                  const stars = row[`${c.key}_sig`] as string | undefined
                  const manual = ((row as { _manual?: string[] })._manual ?? []).includes(c.key)
                  return (
                    <td
                      key={c.key}
                      className={cn(
                        c.fmt !== 'text' && 'num text-right',
                        i === 0 && 'sticky left-0 bg-surface',
                        sig && 'font-semibold',
                      )}
                    >
                      {formatValue(v, typeof v === 'string' ? 'text' : c.fmt, decimals, style)}
                      {manual && v !== null && v !== undefined && v !== '' && (
                        <span className="ml-0.5 text-warning" title="Entered manually; not computed">
                          †<span className="sr-only"> (entered manually)</span>
                        </span>
                      )}
                      {stars && <sup className="ml-0.5 text-[10px]">{stars}</sup>}
                      {sig && <span className="sr-only"> (significant)</span>}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table.notes.filter(Boolean).length > 0 && (
        <p className="mt-2 text-xs text-muted">
          <span className="italic">Note. </span>
          {table.notes.filter(Boolean).join(' ')}
        </p>
      )}
    </figure>
  )
}
