import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import type {
  Catalog,
  Configuration,
  Dataset,
  DatasetSummary,
  ExportRecord,
  Paged,
  Project,
  Recommendations,
  ResultItem,
  User,
} from './types'

export const keys = {
  projects: (status: string) => ['projects', status] as const,
  project: (id: number) => ['project', id] as const,
  datasets: (projectId: number) => ['datasets', projectId] as const,
  dataset: (id: number) => ['dataset', id] as const,
  catalog: ['catalog'] as const,
  configs: (projectId: number) => ['configs', projectId] as const,
  results: (projectId: number) => ['results', projectId] as const,
  recs: (datasetId: number) => ['recs', datasetId] as const,
  exports: (projectId: number) => ['exports', projectId] as const,
}

export function useProjects(status = 'active') {
  return useQuery({ queryKey: keys.projects(status), queryFn: () => api.get<Paged<Project>>('/projects', { status, limit: 200 }) })
}

export function useProject(id: number) {
  return useQuery({ queryKey: keys.project(id), queryFn: () => api.get<Project>(`/projects/${id}`), enabled: id > 0 })
}

export function useDatasets(projectId: number) {
  return useQuery({
    queryKey: keys.datasets(projectId),
    queryFn: () => api.get<Paged<DatasetSummary>>(`/projects/${projectId}/datasets`),
    enabled: projectId > 0,
  })
}

export function useDataset(id: number | null | undefined) {
  return useQuery({ queryKey: keys.dataset(id ?? 0), queryFn: () => api.get<Dataset>(`/datasets/${id}`), enabled: !!id })
}

export function useCatalog() {
  return useQuery({ queryKey: keys.catalog, queryFn: () => api.get<Catalog>('/analyses/catalog'), staleTime: Infinity })
}

export function useConfigs(projectId: number, poll = false) {
  return useQuery({
    queryKey: keys.configs(projectId),
    queryFn: () => api.get<Paged<Configuration>>('/analyses/configurations', { project_id: projectId }),
    enabled: projectId > 0,
    refetchInterval: (q) => {
      const items = q.state.data?.items ?? []
      const active = items.some((c) => c.last_run && ['queued', 'running'].includes(c.last_run.status))
      return poll || active ? 1000 : false
    },
  })
}

export function useResults(projectId: number) {
  return useQuery({
    queryKey: keys.results(projectId),
    queryFn: () => api.get<{ items: ResultItem[] }>('/analyses/results', { project_id: projectId }),
    enabled: projectId > 0,
  })
}

export function useRecommendations(datasetId: number | null | undefined) {
  return useQuery({
    queryKey: keys.recs(datasetId ?? 0),
    queryFn: () => api.get<Recommendations>('/analyses/recommendations', { dataset_id: datasetId! }),
    enabled: !!datasetId,
  })
}

export function useExports(projectId: number) {
  return useQuery({
    queryKey: keys.exports(projectId),
    queryFn: () => api.get<Paged<ExportRecord>>('/exports', { project_id: projectId }),
    enabled: projectId > 0,
  })
}

export function useAuthConfig() {
  return useQuery({
    queryKey: ['auth-config'],
    queryFn: () => api.get<{ mode: 'local' | 'password'; allow_registration: boolean; python_console: boolean }>('/auth/config'),
    staleTime: Infinity,
  })
}

export function useMe(enabled = true) {
  return useQuery({ queryKey: ['me'], queryFn: () => api.get<User>('/auth/me'), enabled, retry: false })
}
