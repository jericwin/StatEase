import { useQuery } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowDown, ArrowUp, Columns3, Search, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ui/feedback'
import { CheckRow, Input, Select } from '@/components/ui/form'
import { Popover } from '@/components/ui/overlay'
import { api } from '@/lib/api'
import type { Variable } from '@/lib/types'
import { cn } from '@/lib/utils'

const BLOCK = 200
const ROW_H = 30

interface PageData {
  columns: string[]
  rows: unknown[][]
  total: number
}

interface Filter {
  column: string
  op: string
  value: string
}

/**
 * Spreadsheet-like viewer. Rows are fetched from the server in blocks as they scroll into view, so
 * large datasets are never loaded into the browser in full.
 */
export function DataGrid({ datasetId, versionId, variables }: { datasetId: number; versionId: number; variables: Variable[] }) {
  const [sort, setSort] = useState<{ col: string; desc: boolean } | null>(null)
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [filter, setFilter] = useState<Filter | null>(null)
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [blocks, setBlocks] = useState<Record<number, unknown[][]>>({})
  const parent = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 300)
    return () => clearTimeout(t)
  }, [search])

  const columns = useMemo(() => variables.map((v) => v.name).filter((c) => !hidden.has(c)), [variables, hidden])
  const query = useMemo(
    () => ({
      sort: sort?.col,
      desc: sort?.desc,
      search: debounced,
      filters: filter && filter.column ? JSON.stringify([coerceFilter(filter, variables)]) : undefined,
      columns: columns.join(','),
      version_id: versionId,
    }),
    [sort, debounced, filter, columns, versionId, variables],
  )
  const qkey = JSON.stringify(query)

  const first = useQuery({
    queryKey: ['grid', datasetId, qkey, 0],
    queryFn: () => api.get<PageData>(`/datasets/${datasetId}/preview`, { ...query, offset: 0, limit: BLOCK }),
    placeholderData: (prev) => prev,
  })

  useEffect(() => {
    setBlocks(first.data ? { 0: first.data.rows } : {})
    parent.current?.scrollTo({ top: 0 })
  }, [first.data])

  const total = first.data?.total ?? 0
  const virt = useVirtualizer({ count: total, getScrollElement: () => parent.current, estimateSize: () => ROW_H, overscan: 20 })
  const items = virt.getVirtualItems()

  // Fetch any missing blocks for the visible range.
  const pending = useRef(new Set<number>())
  useEffect(() => {
    if (!items.length) return
    const needed = new Set<number>()
    for (const it of [items[0], items[items.length - 1]]) needed.add(Math.floor(it.index / BLOCK))
    for (const b of needed) {
      if (blocks[b] || pending.current.has(b)) continue
      pending.current.add(b)
      api
        .get<PageData>(`/datasets/${datasetId}/preview`, { ...query, offset: b * BLOCK, limit: BLOCK })
        .then((d) => setBlocks((prev) => ({ ...prev, [b]: d.rows })))
        .finally(() => pending.current.delete(b))
    }
  }, [items, blocks, datasetId, query])

  const levelOf = useMemo(() => Object.fromEntries(variables.map((v) => [v.name, v.level])), [variables])
  const widths = useMemo(() => columns.map((c) => Math.min(260, Math.max(90, c.length * 8 + 36))), [columns])
  const totalWidth = 56 + widths.reduce((a, b) => a + b, 0)

  if (first.isError) return <ErrorState error={first.error} retry={() => first.refetch()} />

  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-line bg-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted" aria-hidden />
          <Input placeholder="Search all columns" value={search} onChange={(e) => setSearch(e.target.value)} className="pl-8" aria-label="Search data" />
        </div>
        <FilterControl variables={variables} filter={filter} onChange={setFilter} />
        <Popover
          trigger={
            <Button size="sm">
              <Columns3 /> Columns {hidden.size > 0 && `(${variables.length - hidden.size}/${variables.length})`}
            </Button>
          }
        >
          <div className="scroll-thin max-h-80 overflow-y-auto p-3">
            <div className="mb-2 flex justify-between text-xs">
              <button className="text-accent hover:underline" onClick={() => setHidden(new Set())}>Show all</button>
              <button className="text-accent hover:underline" onClick={() => setHidden(new Set(variables.map((v) => v.name)))}>Hide all</button>
            </div>
            {variables.map((v) => (
              <CheckRow
                key={v.name}
                checked={!hidden.has(v.name)}
                onChange={(on) => {
                  const next = new Set(hidden)
                  if (on) next.delete(v.name)
                  else next.add(v.name)
                  setHidden(next)
                }}
                label={v.name}
              />
            ))}
          </div>
        </Popover>
        <span className="num ml-auto text-xs text-muted">
          {first.isFetching ? 'Loading…' : `${total.toLocaleString()} row${total === 1 ? '' : 's'}`}
        </span>
      </div>
      <div ref={parent} className="scroll-thin relative h-[min(62dvh,640px)] overflow-auto" role="grid" aria-rowcount={total + 1} aria-colcount={columns.length}>
        <div style={{ width: totalWidth, minWidth: '100%' }}>
          <div className="sticky top-0 z-10 flex border-b border-line bg-surface-2 text-[12px] font-semibold" role="row">
            <div className="sticky left-0 z-10 w-14 shrink-0 border-r border-line bg-surface-2 px-2 py-1.5 text-right text-[11px] font-normal text-muted">#</div>
            {columns.map((c, i) => (
              <button
                key={c}
                role="columnheader"
                aria-sort={sort?.col === c ? (sort.desc ? 'descending' : 'ascending') : 'none'}
                style={{ width: widths[i] }}
                className="flex shrink-0 items-center gap-1 truncate border-r border-line px-2.5 py-1.5 text-left hover:bg-surface-3"
                onClick={() => setSort(sort?.col === c ? (sort.desc ? null : { col: c, desc: true }) : { col: c, desc: false })}
                title={`${c} (${levelOf[c]}) — click to sort`}
              >
                <span className="truncate">{c}</span>
                {sort?.col === c && (sort.desc ? <ArrowDown className="size-3.5 shrink-0" /> : <ArrowUp className="size-3.5 shrink-0" />)}
              </button>
            ))}
          </div>
          <div style={{ height: virt.getTotalSize(), position: 'relative' }}>
            {items.map((it) => {
              const row = blocks[Math.floor(it.index / BLOCK)]?.[it.index % BLOCK]
              return (
                <div
                  key={it.key}
                  role="row"
                  aria-rowindex={it.index + 2}
                  className="absolute left-0 flex w-full border-b border-line text-[12.5px] hover:bg-surface-2"
                  style={{ height: ROW_H, transform: `translateY(${it.start}px)` }}
                >
                  <div className="num sticky left-0 w-14 shrink-0 border-r border-line bg-surface px-2 py-1 text-right text-[11px] leading-5 text-muted">{it.index + 1}</div>
                  {columns.map((c, j) => {
                    const v = row?.[j]
                    return (
                      <div
                        key={c}
                        role="gridcell"
                        style={{ width: widths[j] }}
                        className={cn('shrink-0 truncate border-r border-line px-2.5 py-1 leading-5', typeof v === 'number' && 'num text-right')}
                      >
                        {row === undefined ? <span className="inline-block h-2.5 w-12 rounded bg-surface-3" /> : v === null ? <span className="text-muted/60 italic">·</span> : String(v)}
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

function coerceFilter(f: Filter, variables: Variable[]) {
  const v = variables.find((x) => x.name === f.column)
  const numeric = v && ['integer', 'decimal'].includes(v.data_type)
  const value = numeric && f.value !== '' && !Number.isNaN(Number(f.value)) ? Number(f.value) : f.value
  return { column: f.column, op: f.op, value }
}

function FilterControl({ variables, filter, onChange }: { variables: Variable[]; filter: Filter | null; onChange: (f: Filter | null) => void }) {
  const [draft, setDraft] = useState<Filter>(filter ?? { column: variables[0]?.name ?? '', op: 'eq', value: '' })
  const [open, setOpen] = useState(false)
  return (
    <div className="flex items-center gap-1">
      <Popover
        open={open}
        onOpenChange={setOpen}
        trigger={<Button size="sm">{filter ? `Filter: ${filter.column}` : 'Add filter'}</Button>}
      >
        <form
          className="space-y-2 p-3"
          onSubmit={(e) => {
            e.preventDefault()
            onChange(draft)
            setOpen(false)
          }}
        >
          <Select aria-label="Filter column" value={draft.column} onChange={(e) => setDraft({ ...draft, column: e.target.value })}>
            {variables.map((v) => (
              <option key={v.name}>{v.name}</option>
            ))}
          </Select>
          <Select aria-label="Filter operator" value={draft.op} onChange={(e) => setDraft({ ...draft, op: e.target.value })}>
            <option value="eq">equals</option>
            <option value="ne">does not equal</option>
            <option value="gt">greater than</option>
            <option value="ge">at least</option>
            <option value="lt">less than</option>
            <option value="le">at most</option>
            <option value="contains">contains</option>
            <option value="is_null">is missing</option>
            <option value="not_null">is not missing</option>
          </Select>
          {!['is_null', 'not_null'].includes(draft.op) && (
            <Input aria-label="Filter value" value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} placeholder="Value" />
          )}
          <Button type="submit" variant="primary" size="sm" className="w-full justify-center">Apply filter</Button>
        </form>
      </Popover>
      {filter && (
        <button className="rounded p-1 text-muted hover:bg-surface-3 hover:text-fg" onClick={() => onChange(null)} aria-label="Clear filter">
          <X className="size-4" />
        </button>
      )}
    </div>
  )
}
