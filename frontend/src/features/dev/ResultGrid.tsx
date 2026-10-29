import { ArrowDown, ArrowUp } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { Input } from '@/components/ui/form'
import { cn } from '@/lib/utils'

const PAGE = 100

/** Query result table with client-side sorting, filtering, pagination and resizable columns. */
export function ResultGrid({ columns, rows }: { columns: { name: string; type?: string }[]; rows: unknown[][] }) {
  const [sort, setSort] = useState<{ i: number; desc: boolean } | null>(null)
  const [filter, setFilter] = useState('')
  const [page, setPage] = useState(0)
  const [widths, setWidths] = useState<Record<number, number>>({})
  const drag = useRef<{ i: number; x: number; w: number } | null>(null)

  const view = useMemo(() => {
    const term = filter.toLowerCase()
    let r = term ? rows.filter((row) => row.some((v) => String(v ?? '').toLowerCase().includes(term))) : rows
    if (sort) {
      r = [...r].sort((a, b) => {
        const x = a[sort.i]
        const y = b[sort.i]
        if (x === y) return 0
        if (x === null || x === undefined) return 1
        if (y === null || y === undefined) return -1
        const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))
        return sort.desc ? -c : c
      })
    }
    return r
  }, [rows, filter, sort])
  const pages = Math.max(1, Math.ceil(view.length / PAGE))
  const shown = view.slice(page * PAGE, page * PAGE + PAGE)

  const startDrag = (i: number, e: React.PointerEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const th = (e.target as HTMLElement).parentElement!
    drag.current = { i, x: e.clientX, w: th.getBoundingClientRect().width }
    const move = (ev: PointerEvent) => {
      if (!drag.current) return
      setWidths((w) => ({ ...w, [drag.current!.i]: Math.max(60, drag.current!.w + ev.clientX - drag.current!.x) }))
    }
    const up = () => {
      drag.current = null
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-2 py-1.5">
        <Input value={filter} onChange={(e) => { setFilter(e.target.value); setPage(0) }} placeholder="Filter rows" className="h-7 w-48" aria-label="Filter result rows" />
        <span className="num text-xs text-muted">{view.length.toLocaleString()} of {rows.length.toLocaleString()} rows</span>
        <div className="ml-auto flex items-center gap-1 text-xs">
          <button className="rounded px-2 py-0.5 hover:bg-surface-3 disabled:opacity-40" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
          <span className="num text-muted">{page + 1} / {pages}</span>
          <button className="rounded px-2 py-0.5 hover:bg-surface-3 disabled:opacity-40" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-auto">
        <table className="border-collapse text-[12.5px]" style={{ tableLayout: 'fixed', width: 'max-content' }}>
          <thead className="sticky top-0 z-10 bg-surface-2">
            <tr>
              <th className="num w-12 border-r border-b border-line px-2 py-1 text-right text-[11px] font-normal text-muted">#</th>
              {columns.map((c, i) => (
                <th
                  key={i}
                  style={{ width: widths[i] ?? Math.min(280, Math.max(90, c.name.length * 8 + 40)) }}
                  className="relative border-r border-b border-line px-2 py-1 text-left font-semibold"
                  aria-sort={sort?.i === i ? (sort.desc ? 'descending' : 'ascending') : 'none'}
                >
                  <button className="flex w-full items-center gap-1 truncate text-left" onClick={() => setSort(sort?.i === i ? (sort.desc ? null : { i, desc: true }) : { i, desc: false })} title={c.type}>
                    <span className="truncate">{c.name}</span>
                    {sort?.i === i && (sort.desc ? <ArrowDown className="size-3 shrink-0" /> : <ArrowUp className="size-3 shrink-0" />)}
                  </button>
                  <span onPointerDown={(e) => startDrag(i, e)} className="absolute top-0 right-0 h-full w-1.5 cursor-col-resize hover:bg-accent/40" aria-hidden />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, r) => (
              <tr key={r} className="hover:bg-surface-2">
                <td className="num border-r border-b border-line px-2 py-0.5 text-right text-[11px] text-muted">{page * PAGE + r + 1}</td>
                {row.map((v, j) => (
                  <td key={j} className={cn('truncate border-r border-b border-line px-2 py-0.5', typeof v === 'number' && 'num text-right')} title={v === null ? 'NULL' : String(v)}>
                    {v === null || v === undefined ? <span className="text-muted/70 italic">NULL</span> : String(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
