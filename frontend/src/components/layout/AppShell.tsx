import * as Collapsible from '@radix-ui/react-collapsible'
import {
  BarChart3,
  BookOpen,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  Database,
  Eraser,
  FileText,
  FolderKanban,
  Home,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  Moon,
  Settings,
  Sun,
  Table2,
  Target,
  Terminal,
  Upload,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useParams } from 'react-router-dom'
import { Sheet, Tooltip } from '@/components/ui/overlay'
import { useAuth } from '@/lib/auth'
import { Mark } from '@/components/brand/Mark'
import { useProject } from '@/lib/queries'
import { applyTheme, cn, storageGet, storageSet, type Theme } from '@/lib/utils'

function Logo({ collapsed }: { collapsed?: boolean }) {
  return (
    <Link to="/app" className="flex h-12 items-center gap-2.5 px-4 text-nav-fg-strong" aria-label="StatEase Analytics home">
      <Mark className="size-6" tailClassName="fill-[#e3916b]" />
      {!collapsed && (
        <span className="text-[14px] font-semibold tracking-tight">
          StatEase <span className="font-normal text-nav-fg">Analytics</span>
        </span>
      )}
    </Link>
  )
}

interface NavItemProps {
  to: string
  icon: ReactNode
  label: string
  collapsed?: boolean
  end?: boolean
  onNavigate?: () => void
  activeOverride?: boolean
}

function NavItem({ to, icon, label, collapsed, end, onNavigate, activeOverride }: NavItemProps) {
  const link = (
    <NavLink
      to={to}
      end={end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          'flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] text-nav-fg transition-colors hover:bg-nav-2 hover:text-nav-fg-strong [&_svg]:size-4 [&_svg]:shrink-0',
          (activeOverride ?? isActive) && 'bg-nav-2 font-medium text-nav-fg-strong shadow-[inset_2px_0_0_#6a9be0]',
          collapsed && 'justify-center px-0',
        )
      }
    >
      {icon}
      {!collapsed && <span className="truncate">{label}</span>}
    </NavLink>
  )
  return collapsed ? (
    <Tooltip content={label} side="right">
      {link}
    </Tooltip>
  ) : (
    link
  )
}

function Section({ label, collapsed, children }: { label: string; collapsed?: boolean; children: ReactNode }) {
  return (
    <div className="space-y-0.5">
      {!collapsed ? (
        <div className="px-2.5 pt-4 pb-1 text-[10.5px] font-semibold tracking-[0.08em] text-nav-fg/70 uppercase">{label}</div>
      ) : (
        <div className="mx-3 my-3 border-t border-white/10" />
      )}
      {children}
    </div>
  )
}

function SidebarContent({ collapsed, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const { projectId } = useParams()
  const pid = Number(projectId ?? 0)
  const project = useProject(pid)
  const location = useLocation()
  const { user, config, signOut } = useAuth()
  const [toolsOpen, setToolsOpen] = useState(() => location.pathname.startsWith('/tools') || storageGet('statease.nav.tools', '0') === '1')
  const base = `/p/${pid}`

  return (
    <nav aria-label="Main" className="scroll-thin flex min-h-0 flex-1 flex-col overflow-y-auto px-2 pb-3">
      <div className="space-y-0.5 pt-1">
        <NavItem to="/app" end icon={<Home />} label="Dashboard" collapsed={collapsed} onNavigate={onNavigate} />
        <NavItem to="/app/projects" icon={<FolderKanban />} label="My projects" collapsed={collapsed} onNavigate={onNavigate} />
      </div>
      {pid > 0 && (
        <>
          {!collapsed && (
            <div className="mt-4 truncate px-2.5 text-[12px] font-medium text-nav-fg-strong" title={project.data?.name}>
              {project.data?.name ?? '…'}
            </div>
          )}
          <Section label="Project" collapsed={collapsed}>
            <NavItem to={base} end icon={<LayoutDashboard />} label="Overview" collapsed={collapsed} onNavigate={onNavigate} />
            <NavItem to={`${base}/import`} icon={<Upload />} label="Import data" collapsed={collapsed} onNavigate={onNavigate} />
            <NavItem to={`${base}/data`} icon={<Table2 />} label="Data" collapsed={collapsed} onNavigate={onNavigate} />
            <NavItem to={`${base}/clean`} icon={<Eraser />} label="Clean data" collapsed={collapsed} onNavigate={onNavigate} />
            <NavItem to={`${base}/objectives`} icon={<Target />} label="Objectives" collapsed={collapsed} onNavigate={onNavigate} />
            <NavItem to={`${base}/analyze`} icon={<ListChecks />} label="Analyze" collapsed={collapsed} onNavigate={onNavigate} />
            <NavItem to={`${base}/results`} icon={<BarChart3 />} label="Results" collapsed={collapsed} onNavigate={onNavigate} />
            <NavItem to={`${base}/report`} icon={<FileText />} label="Report" collapsed={collapsed} onNavigate={onNavigate} />
          </Section>
        </>
      )}
      <div className="flex-1" />
      <Collapsible.Root
        open={toolsOpen || collapsed}
        onOpenChange={(v) => {
          setToolsOpen(v)
          storageSet('statease.nav.tools', v ? '1' : '0')
        }}
      >
        {!collapsed && (
          <Collapsible.Trigger className="mt-4 flex w-full items-center justify-between px-2.5 pb-1 text-[10.5px] font-semibold tracking-[0.08em] text-nav-fg/70 uppercase hover:text-nav-fg-strong">
            Advanced tools
            <ChevronDown className={cn('size-3.5 transition-transform', toolsOpen && 'rotate-180')} />
          </Collapsible.Trigger>
        )}
        <Collapsible.Content className="space-y-0.5">
          {collapsed && <div className="mx-3 my-3 border-t border-white/10" />}
          <NavItem to="/tools/sql" icon={<Database />} label="SQL workbench" collapsed={collapsed} onNavigate={onNavigate} />
          <NavItem to="/tools/python" icon={<Terminal />} label="Python console" collapsed={collapsed} onNavigate={onNavigate} />
          <NavItem to="/help" icon={<BookOpen />} label="Methods guide" collapsed={collapsed} onNavigate={onNavigate} />
        </Collapsible.Content>
      </Collapsible.Root>
      <div className="mt-1 space-y-0.5">
        <NavItem to="/settings" icon={<Settings />} label="Settings" collapsed={collapsed} onNavigate={onNavigate} />
        {config?.mode === 'password' && (
          <button
            type="button"
            onClick={signOut}
            className={cn('flex h-8 w-full items-center gap-2.5 rounded-md px-2.5 text-[13px] text-nav-fg hover:bg-nav-2 hover:text-nav-fg-strong [&_svg]:size-4', collapsed && 'justify-center px-0')}
            title={user?.email}
          >
            <LogOut />
            {!collapsed && <span className="truncate">Sign out</span>}
          </button>
        )}
      </div>
    </nav>
  )
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => storageGet('statease.theme', 'system') as Theme)
  useEffect(() => {
    const h = () => setTheme(storageGet('statease.theme', 'system') as Theme)
    window.addEventListener('statease:theme', h)
    return () => window.removeEventListener('statease:theme', h)
  }, [])
  const isDark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
  return (
    <button
      type="button"
      className="flex size-8 items-center justify-center rounded-md text-muted hover:bg-surface-3 hover:text-fg"
      aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
      onClick={() => {
        const next: Theme = isDark ? 'light' : 'dark'
        applyTheme(next)
        setTheme(next)
      }}
      data-theme={theme}
    >
      {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  )
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(() => storageGet('statease.nav.collapsed', '0') === '1')
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  useEffect(() => setMobileOpen(false), [location.pathname, location.search])

  return (
    <div className="flex h-dvh overflow-hidden">
      <aside
        className={cn('hidden shrink-0 flex-col bg-nav transition-[width] duration-150 lg:flex', collapsed ? 'w-14' : 'w-[232px]')}
        aria-label="Sidebar"
      >
        <Logo collapsed={collapsed} />
        <SidebarContent collapsed={collapsed} />
        <button
          type="button"
          onClick={() => {
            setCollapsed(!collapsed)
            storageSet('statease.nav.collapsed', collapsed ? '0' : '1')
          }}
          className="flex h-9 items-center gap-2 border-t border-white/10 px-4 text-[12px] text-nav-fg hover:text-nav-fg-strong"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronsRight className="size-4" /> : <ChevronsLeft className="size-4" />}
          {!collapsed && 'Collapse'}
        </button>
      </aside>
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen} side="left" title="Navigation" className="bg-nav">
        <Logo />
        <SidebarContent onNavigate={() => setMobileOpen(false)} />
      </Sheet>
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileBar onMenu={() => setMobileOpen(true)} />
        <main id="main" className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          <div key={location.pathname} className="animate-in">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}

function MobileBar({ onMenu }: { onMenu: () => void }) {
  return (
    <div className="flex h-12 shrink-0 items-center gap-2 border-b border-line bg-surface px-3 lg:hidden">
      <button type="button" onClick={onMenu} className="flex size-9 items-center justify-center rounded-md hover:bg-surface-3" aria-label="Open navigation">
        <Menu className="size-5" />
      </button>
      <Link to="/app" className="text-[14px] font-semibold">
        StatEase <span className="font-normal text-muted">Analytics</span>
      </Link>
      <div className="flex-1" />
      <ThemeToggle />
    </div>
  )
}

/** Standard page header used by every screen. */
export function PageHeader({
  title,
  description,
  actions,
  breadcrumb,
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  breadcrumb?: ReactNode
}) {
  return (
    <div className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-end justify-between gap-x-4 gap-y-3 px-4 py-4 sm:px-6">
        <div className="min-w-0">
          {breadcrumb && <div className="mb-1 text-xs text-muted">{breadcrumb}</div>}
          <h1 className="text-[19px] leading-tight font-semibold">{title}</h1>
          {description && <p className="mt-1 max-w-3xl text-[13px] text-muted">{description}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {actions}
          <div className="hidden lg:block">
            <ThemeToggle />
          </div>
        </div>
      </div>
    </div>
  )
}

export function PageBody({ children, className, wide }: { children: ReactNode; className?: string; wide?: boolean }) {
  return <div className={cn('mx-auto px-4 py-5 sm:px-6', wide ? 'max-w-none' : 'max-w-[1440px]', className)}>{children}</div>
}
