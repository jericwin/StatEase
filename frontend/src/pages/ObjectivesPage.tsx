import { Link, useNavigate } from 'react-router-dom'
import { PageBody, PageHeader } from '@/components/layout/AppShell'
import { ObjectivesStep } from '@/features/report/ObjectivesStep'
import { useProjectId } from '@/lib/active'
import { useProject } from '@/lib/queries'

export default function ObjectivesPage() {
  const pid = useProjectId()
  const project = useProject(pid)
  const navigate = useNavigate()
  return (
    <>
      <PageHeader
        breadcrumb={<Link to={`/p/${pid}`} className="hover:underline">{project.data?.name ?? 'Project'}</Link>}
        title="Objectives"
        description="Start from your research questions. StatEase finds the variables each one needs and reports only those results."
      />
      <PageBody>
        <ObjectivesStep projectId={pid} skipLink={`/p/${pid}/analyze`} onCreated={(r) => navigate(`/p/${pid}/report?id=${r.id}`)} />
      </PageBody>
    </>
  )
}
