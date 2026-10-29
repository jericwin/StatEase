import { Select } from '@/components/ui/form'
import type { DatasetSummary } from '@/lib/types'

export function DatasetPicker({
  datasets,
  value,
  onChange,
  className,
}: {
  datasets: DatasetSummary[]
  value: number | null
  onChange: (id: number) => void
  className?: string
}) {
  if (datasets.length <= 1) return null
  return (
    <Select aria-label="Dataset" className={className ?? 'w-64'} value={value ?? ''} onChange={(e) => onChange(Number(e.target.value))}>
      {datasets.map((d) => (
        <option key={d.id} value={d.id}>
          {d.name} ({d.row_count.toLocaleString()} rows)
        </option>
      ))}
    </Select>
  )
}
