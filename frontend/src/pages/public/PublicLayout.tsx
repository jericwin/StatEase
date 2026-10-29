import { ArrowRight, Menu, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Mark } from '@/components/brand/Mark'
import { ThemeToggle } from '@/components/layout/AppShell'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'

export { Mark } from '@/components/brand/Mark'

export function Logo({ className }: { className?: string }) {
  return (
    <Link to="/" className={cn('flex items-center gap-2.5 text-ink', className)} aria-label="StatEase Analytics home">
      <Mark />
      <span className="display text-[19px] leading-none">
        StatEase<span className="ml-1 font-sans text-[13px] font-medium tracking-normal text-ink-2">Analytics</span>
      </span>
    </Link>
  )
}

export function PublicLayout({ children }: { children: ReactNode }) {
  const { user, config } = useAuth()
  const [open, setOpen] = useState(false)
  const signedIn = !!user || config?.mode === 'local'
  const nav = [
    { href: '/#method', label: 'How it works' },
    { href: '/#examples', label: 'Examples' },
    { href: '/#accuracy', label: 'Accuracy' },
  ]
  return (
    <div className="flex min-h-dvh flex-col bg-paper text-ink">
      <header className="sticky top-0 z-40 border-b border-paper-line bg-paper/90 backdrop-blur-sm">
        <div className="mx-auto flex h-[68px] max-w-6xl items-center gap-8 px-5 sm:px-8">
          <Logo />
          <nav className="hidden items-center gap-7 text-[13.5px] text-ink-2 md:flex" aria-label="Site">
            {nav.map((n) => (
              <a key={n.href} href={n.href} className="transition-colors hover:text-ink">{n.label}</a>
            ))}
          </nav>
          <div className="flex-1" />
          <div className="hidden items-center gap-1 md:flex">
            <ThemeToggle />
            {signedIn ? (
              <Link to="/app" className="ml-2 inline-flex h-9 items-center gap-1.5 rounded-full bg-ink px-4 text-[13.5px] font-medium text-paper hover:opacity-90">
                Open dashboard <ArrowRight className="size-3.5" />
              </Link>
            ) : (
              <>
                <Link to="/login" className="inline-flex h-9 items-center px-3 text-[13.5px] font-medium text-ink-2 hover:text-ink">Sign in</Link>
                <Link to="/signup" className="ml-1 inline-flex h-9 items-center gap-1.5 rounded-full bg-ink px-4 text-[13.5px] font-medium text-paper transition-opacity hover:opacity-90">
                  Start analyzing <ArrowRight className="size-3.5" />
                </Link>
              </>
            )}
          </div>
          <button className="flex size-10 items-center justify-center rounded-full hover:bg-paper-2 md:hidden" onClick={() => setOpen(!open)} aria-label="Menu" aria-expanded={open}>
            {open ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
        {open && (
          <div className="border-t border-paper-line px-5 py-4 md:hidden">
            <nav className="flex flex-col text-[15px]" aria-label="Site menu">
              {nav.map((n) => (
                <a key={n.href} href={n.href} onClick={() => setOpen(false)} className="border-b border-paper-line py-3">{n.label}</a>
              ))}
              {signedIn ? (
                <Link to="/app" className="mt-4 rounded-full bg-ink px-4 py-3 text-center font-medium text-paper">Open dashboard</Link>
              ) : (
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <Link to="/login" className="rounded-full border border-paper-line py-3 text-center font-medium">Sign in</Link>
                  <Link to="/signup" className="rounded-full bg-ink py-3 text-center font-medium text-paper">Start analyzing</Link>
                </div>
              )}
            </nav>
          </div>
        )}
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-paper-line">
        <div className="mx-auto grid max-w-6xl gap-10 px-5 py-14 sm:px-8 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div>
            <Logo />
            <p className="mt-4 max-w-xs text-[13.5px] leading-relaxed text-ink-2">Statistics for research reports — from your spreadsheet to editable Word and Excel tables.</p>
          </div>
          <FooterCol title="Product" links={[['How it works', '/#method'], ['Accuracy', '/#accuracy'], ['Start analyzing', '/signup']]} />
          <FooterCol title="Examples" links={[['Fertilizer trial', '/demo/fertilizer'], ['Group experiment', '/demo/experiment'], ['Survey analysis', '/demo/survey']]} />
          <FooterCol title="Company" links={[['About', '/about'], ['Privacy Policy', '/privacy'], ['Terms', '/terms']]} />
        </div>
        <div className="border-t border-paper-line">
          <div className="mx-auto flex max-w-6xl flex-wrap justify-between gap-2 px-5 py-5 text-[12.5px] text-ink-2 sm:px-8">
            <span>© {new Date().getFullYear()} StatEase Analytics</span>
            <span>Example projects use fictional sample data.</span>
          </div>
        </div>
      </footer>
    </div>
  )
}

function FooterCol({ title, links }: { title: string; links: [string, string][] }) {
  return (
    <div>
      <h2 className="kicker">{title}</h2>
      <ul className="mt-4 space-y-2.5 text-[14px]">
        {links.map(([label, href]) => (
          <li key={href}>
            {href.startsWith('/#') ? <a href={href} className="text-ink-2 hover:text-ink">{label}</a> : <Link to={href} className="text-ink-2 hover:text-ink">{label}</Link>}
          </li>
        ))}
      </ul>
    </div>
  )
}
