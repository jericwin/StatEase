import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useDatasets } from './queries'
import { storageGet, storageSet } from './utils'

export function useProjectId(): number {
  const { projectId } = useParams()
  return Number(projectId ?? 0)
}

/** The dataset the user is working on in a project (remembered per project in this browser). */
export function useActiveDataset(projectId: number) {
  const datasets = useDatasets(projectId)
  const key = `statease.dataset.${projectId}`
  const [stored, setStored] = useState<number | null>(() => {
    const v = Number(storageGet(key, '0'))
    return v > 0 ? v : null
  })
  const items = datasets.data?.items ?? []
  const valid = stored && items.some((d) => d.id === stored) ? stored : (items.at(-1)?.id ?? null)
  useEffect(() => {
    const h = (e: Event) => {
      const d = (e as CustomEvent<{ key: string; id: number }>).detail
      if (d.key === key) setStored(d.id)
    }
    window.addEventListener('statease:dataset', h)
    return () => window.removeEventListener('statease:dataset', h)
  }, [key])
  const set = useCallback(
    (id: number) => {
      setStored(id)
      storageSet(key, String(id))
      window.dispatchEvent(new CustomEvent('statease:dataset', { detail: { key, id } }))
    },
    [key],
  )
  return { datasetId: valid, setDatasetId: set, datasets: items, query: datasets }
}
