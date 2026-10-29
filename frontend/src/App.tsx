import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter, Navigate, RouterProvider, useParams } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { RouteError } from './components/RouteError'
import { Spinner, ToastProvider } from './components/ui/feedback'
import { TooltipProvider } from './components/ui/overlay'
import { AuthProvider, RequireAuth } from './lib/auth'
import { ForgotPasswordPage, LoginPage, OAuthCallbackPage, ResetPasswordPage, SignupPage, VerifyEmailPage } from './pages/public/AuthPages'

const Landing = lazy(() => import('./pages/public/Landing'))
const DemoPreviewPage = lazy(() => import('./pages/public/DemoPreview'))
const Legal = {
  About: lazy(() => import('./pages/public/Legal').then((m) => ({ default: m.AboutPage }))),
  Privacy: lazy(() => import('./pages/public/Legal').then((m) => ({ default: m.PrivacyPage }))),
  Terms: lazy(() => import('./pages/public/Legal').then((m) => ({ default: m.TermsPage }))),
}
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const ProjectsPage = lazy(() => import('./pages/ProjectsPage'))
const OverviewPage = lazy(() => import('./pages/OverviewPage'))
const ImportPage = lazy(() => import('./pages/ImportPage'))
const DataPage = lazy(() => import('./pages/DataPage'))
const AnalyzePage = lazy(() => import('./pages/AnalyzePage'))
const ResultsPage = lazy(() => import('./pages/ResultsPage'))
const ReportPage = lazy(() => import('./pages/ReportPage'))
const ObjectivesPage = lazy(() => import('./pages/ObjectivesPage'))
const CleanPage = lazy(() => import('./pages/CleanPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const SqlPage = lazy(() => import('./pages/dev/SqlPage'))
const PythonPage = lazy(() => import('./pages/dev/PythonPage'))
const HelpPage = lazy(() => import('./pages/HelpPage'))

function Page({ children }: { children: ReactNode }) {
  return <Suspense fallback={<Spinner className="p-6" />}>{children}</Suspense>
}

function ExportRedirect() {
  const { projectId } = useParams()
  return <Navigate to={`/p/${projectId}/report`} replace />
}

const notFound = () => {
  throw new Response('Not Found', { status: 404, statusText: 'Not Found' })
}

const router = createBrowserRouter([
  {
    // Any error thrown while rendering or loading a page lands here instead of React Router's developer screen.
    errorElement: <RouteError />,
    children: [
      {
        path: '/',
        element: (
          <Page>
            <Landing />
          </Page>
        ),
      },
      { path: '/login', element: <LoginPage /> },
      { path: '/signup', element: <SignupPage /> },
      { path: '/verify-email', element: <VerifyEmailPage /> },
      { path: '/forgot-password', element: <ForgotPasswordPage /> },
      { path: '/reset-password', element: <ResetPasswordPage /> },
      { path: '/auth/callback', element: <OAuthCallbackPage /> },
      {
        path: '/demo/formulation',
        element: <Navigate to="/demo/fertilizer" replace />,
      },
      {
        path: '/demo/:key',
        element: (
          <Page>
            <DemoPreviewPage />
          </Page>
        ),
      },
      {
        path: '/about',
        element: (
          <Page>
            <Legal.About />
          </Page>
        ),
      },
      {
        path: '/privacy',
        element: (
          <Page>
            <Legal.Privacy />
          </Page>
        ),
      },
      {
        path: '/terms',
        element: (
          <Page>
            <Legal.Terms />
          </Page>
        ),
      },
      {
        element: (
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        ),
        children: [
          {
            // Errors inside the app keep the sidebar, so the person can move to another page.
            errorElement: <RouteError inApp />,
            children: [
              {
                path: '/app',
                element: (
                  <Page>
                    <DashboardPage />
                  </Page>
                ),
              },
              {
                path: '/app/projects',
                element: (
                  <Page>
                    <ProjectsPage />
                  </Page>
                ),
              },
              {
                path: '/p/:projectId',
                element: (
                  <Page>
                    <OverviewPage />
                  </Page>
                ),
              },
              {
                path: '/p/:projectId/import',
                element: (
                  <Page>
                    <ImportPage />
                  </Page>
                ),
              },
              {
                path: '/p/:projectId/data',
                element: (
                  <Page>
                    <DataPage />
                  </Page>
                ),
              },
              {
                path: '/p/:projectId/clean',
                element: (
                  <Page>
                    <CleanPage />
                  </Page>
                ),
              },
              {
                path: '/p/:projectId/objectives',
                element: (
                  <Page>
                    <ObjectivesPage />
                  </Page>
                ),
              },
              {
                path: '/p/:projectId/analyze',
                element: (
                  <Page>
                    <AnalyzePage />
                  </Page>
                ),
              },
              {
                path: '/p/:projectId/results',
                element: (
                  <Page>
                    <ResultsPage />
                  </Page>
                ),
              },
              {
                path: '/p/:projectId/report',
                element: (
                  <Page>
                    <ReportPage />
                  </Page>
                ),
              },
              { path: '/p/:projectId/export', element: <ExportRedirect /> },
              {
                path: '/settings',
                element: (
                  <Page>
                    <SettingsPage />
                  </Page>
                ),
              },
              {
                path: '/tools/sql',
                element: (
                  <Page>
                    <SqlPage />
                  </Page>
                ),
              },
              {
                path: '/tools/python',
                element: (
                  <Page>
                    <PythonPage />
                  </Page>
                ),
              },
              {
                path: '/help',
                element: (
                  <Page>
                    <HelpPage />
                  </Page>
                ),
              },
            ],
          },
        ],
      },
      { path: '*', loader: notFound },
    ],
  },
])

export function App() {
  return (
    <ToastProvider>
      <TooltipProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </TooltipProvider>
    </ToastProvider>
  )
}
