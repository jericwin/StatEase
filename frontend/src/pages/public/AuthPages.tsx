import { zodResolver } from '@hookform/resolvers/zod'
import { Eye, EyeOff } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Callout, Spinner } from '@/components/ui/feedback'
import { Field, Input } from '@/components/ui/form'
import { ApiError, api, errorMessage } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useQuery } from '@tanstack/react-query'
import type { DemoPreview } from '@/lib/types'
import { Logo } from './PublicLayout'
import { MiniMeans } from './visuals'

const GOOGLE_ERRORS: Record<string, string> = {
  google_cancelled: 'Google sign-in was cancelled.',
  google_state: 'The Google sign-in session expired. Please try again.',
  google_failed: 'Google sign-in could not be completed. Please try again.',
  google_unverified: 'Your Google email address is not verified.',
  registration_closed: 'Sign-up is closed on this server.',
  account_disabled: 'This account is disabled.',
}

function LoginAside() {
  const demo = useQuery({ queryKey: ['public-demo', 'experiment'], queryFn: () => api.get<DemoPreview>('/public/demos/experiment'), staleTime: Infinity })
  const chart = demo.data?.results[0]?.charts.find((c) => c.type === 'means')
  const data = chart?.data as unknown as { categories: string[]; series: { name: string; values: (number | null)[]; lower?: (number | null)[]; upper?: (number | null)[] }[] } | undefined
  return (
    <div className="relative">
      <p className="font-sans text-[11px] font-semibold tracking-[0.16em] text-paper/55 uppercase">From the intervention example</p>
      <figure className="mt-5 rounded-md bg-paper/[0.05] p-5 ring-1 ring-paper/10">
        <figcaption className="font-serif text-[14px] text-paper">
          <span className="font-semibold">Figure 1</span> <span className="italic text-paper/75">Mean test scores by group</span>
        </figcaption>
        <div className="mt-3 [--ink-2:#8d9ab3] [--ink:#f4efe4] [--paper-line:rgba(244,239,228,0.12)] [--rust:#e3916b]">
          {data ? <MiniMeans categories={data.categories.map((c) => c.split(' ')[0])} series={data.series} max={100} height={150} /> : <div className="h-[150px]" />}
        </div>
        <div className="mt-3 flex gap-4 text-[12px] text-paper/60">
          <span className="flex items-center gap-1.5"><span className="size-2.5 bg-[#8d9ab3]/70" /> Control</span>
          <span className="flex items-center gap-1.5"><span className="size-2.5 bg-[#f4efe4]" /> Treatment</span>
        </div>
      </figure>
      <p className="mt-8 font-serif text-[22px] leading-snug text-paper">Pick the two groups. StatEase chooses the test, checks it, and writes it up.</p>
    </div>
  )
}

function SignupAside() {
  const steps = [
    ['Upload', 'Excel or CSV. Columns are typed and checked for you.'],
    ['Compare', 'Accept the suggested comparison or pick your own groups.'],
    ['Export', 'Edit the tables and figures, then download Word or Excel.'],
  ]
  return (
    <div className="relative">
      <p className="font-sans text-[11px] font-semibold tracking-[0.16em] text-paper/55 uppercase">What happens next</p>
      <ol className="mt-6 space-y-6">
        {steps.map(([t, d], i) => (
          <li key={t} className="flex gap-5">
            <span className="display text-[34px] leading-none text-rust">{i + 1}</span>
            <div className="border-t border-paper/15 pt-2">
              <div className="text-[16px] font-semibold text-paper">{t}</div>
              <p className="mt-0.5 text-[14px] leading-relaxed text-paper/65">{d}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-10 border-t border-paper/15 pt-5 text-[13px] text-paper/55">Free to start. Three example studies are ready the moment you sign in.</p>
    </div>
  )
}

function AuthShell({ title, subtitle, children, footer, aside = 'login' }: { title: string; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode; aside?: 'login' | 'signup' }) {
  return (
    <div className="grid min-h-dvh bg-paper text-ink lg:grid-cols-[minmax(0,1fr)_minmax(0,560px)]">
      <div className="flex flex-col px-5 py-6 sm:px-12">
        <div className="flex items-center justify-between">
          <Logo />
          <Link to="/" className="text-[13px] text-ink-2 hover:text-ink">← Back to site</Link>
        </div>
        <div className="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center py-12">
          <div className="animate-in">
            <h1 className="display text-[36px] leading-tight">{title}</h1>
            {subtitle && <p className="mt-2 text-[15px] text-ink-2">{subtitle}</p>}
            <div className="mt-8 [&_input]:h-11 [&_input]:rounded-md [&_input]:border-paper-line [&_input]:bg-surface [&_input]:text-[14.5px] [&_label]:text-ink">{children}</div>
            {footer && <div className="mt-8 border-t border-paper-line pt-5 text-center text-[14px] text-ink-2">{footer}</div>}
          </div>
        </div>
        <p className="text-[12px] text-ink-2">© {new Date().getFullYear()} StatEase Analytics · <Link to="/privacy" className="hover:text-ink">Privacy</Link> · <Link to="/terms" className="hover:text-ink">Terms</Link></p>
      </div>
      <aside className="relative hidden overflow-hidden bg-ink text-paper [--ink:#14213a] [--paper:#f4efe4] [--rust:#e3916b] dark:[--ink:#18243a] lg:flex lg:flex-col lg:justify-center lg:px-14 lg:py-16">
        <svg className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.06]" aria-hidden>
          <defs>
            <pattern id="rules" width="28" height="28" patternUnits="userSpaceOnUse">
              <path d="M0 27.5H28" stroke="currentColor" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#rules)" />
        </svg>
        {aside === 'login' ? <LoginAside /> : <SignupAside />}
      </aside>
    </div>
  )
}

const GOOGLE_G = (
  <svg viewBox="0 0 48 48" className="size-[18px]" aria-hidden>
    <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
    <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
    <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
    <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
  </svg>
)

function GoogleButton({ next }: { next: string }) {
  const { config } = useAuth()
  const enabled = !!config?.google
  if (!enabled) return null
  return (
    <div className="mt-6">
      <div className="mb-5 flex items-center gap-3 text-[12px] text-ink-2">
        <span className="h-px flex-1 bg-paper-line" /> or <span className="h-px flex-1 bg-paper-line" />
      </div>
      <a
        href={`/api/v1/auth/google/start?next=${encodeURIComponent(next)}`}
        className="flex h-11 w-full items-center justify-center gap-2.5 rounded-full border border-paper-line bg-surface text-[14.5px] font-medium text-ink transition-colors hover:border-ink/40"
      >
        {GOOGLE_G}
        Continue with Google
      </a>
    </div>
  )
}


function PasswordInput({ id, autoComplete, ...rest }: React.InputHTMLAttributes<HTMLInputElement>) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <Input id={id} type={show ? 'text' : 'password'} autoComplete={autoComplete} className="h-10 pr-10" {...rest} />
      <button type="button" onClick={() => setShow(!show)} className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-muted hover:text-fg" aria-label={show ? 'Hide password' : 'Show password'} aria-pressed={show}>
        {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  )
}

/** After sign-in: open the requested demo (if any) or go to the requested page. */
function useAfterSignIn() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = params.get('next') || '/app'
  const demo = params.get('demo')
  return async () => {
    if (demo) {
      try {
        const p = await api.post<{ id: number; report_id: number | null }>('/demo', { key: demo })
        navigate(`/p/${p.id}/report`, { replace: true })
        return
      } catch {
        /* fall through to dashboard */
      }
    }
    navigate(next.startsWith('/') ? next : '/app', { replace: true })
  }
}

function LocalModeNotice() {
  return (
    <AuthShell title="No sign-in needed" subtitle="This installation runs in local mode for a single user.">
      <Link to="/app"><Button variant="primary" size="lg" className="h-11 w-full justify-center rounded-full !bg-ink !text-paper hover:opacity-90">Open dashboard</Button></Link>
    </AuthShell>
  )
}

const loginSchema = z.object({ email: z.string().email('Enter a valid email address.'), password: z.string().min(1, 'Enter your password.') })

export function LoginPage() {
  const { signIn, config, user } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const after = useAfterSignIn()
  const [error, setError] = useState<string | null>(GOOGLE_ERRORS[params.get('error') ?? ''] ?? null)
  const form = useForm<z.infer<typeof loginSchema>>({ resolver: zodResolver(loginSchema) })
  if (config?.mode === 'local') return <LocalModeNotice />
  if (user) return <Navigate to={params.get('next') || '/app'} replace />
  const qs = params.toString() ? `?${params.toString()}` : ''
  const submit = form.handleSubmit(async (v) => {
    setError(null)
    try {
      const r = await api.post<{ token: string }>('/auth/login', v)
      await signIn(r.token)
      await after()
    } catch (e) {
      if (e instanceof ApiError && e.code === 'email_unverified') {
        const q = new URLSearchParams(params)
        q.set('email', v.email)
        navigate(`/verify-email?${q.toString()}`)
        return
      }
      setError(errorMessage(e))
    }
  })
  return (
    <AuthShell title="Welcome back." subtitle="Sign in to pick up where you left off." footer={<>New to StatEase? <Link to={`/signup${qs}`} className="font-medium text-ink underline decoration-ink/30 underline-offset-4 hover:decoration-ink">Create an account</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label="Email" error={form.formState.errors.email?.message}>{(id) => <Input id={id} type="email" autoComplete="email" className="h-10" {...form.register('email')} />}</Field>
        <div className="relative">
          <Link to="/forgot-password" className="absolute top-0 right-0 text-[13px] text-ink-2 underline decoration-ink/20 underline-offset-4 hover:text-ink">Forgot password?</Link>
          <Field label="Password" error={form.formState.errors.password?.message}>
            {(id) => <PasswordInput id={id} autoComplete="current-password" {...form.register('password')} />}
          </Field>
        </div>
        {error && <Callout tone="danger">{error}</Callout>}
        <Button type="submit" variant="primary" size="lg" className="h-11 w-full justify-center rounded-full !bg-ink !text-paper hover:opacity-90" loading={form.formState.isSubmitting}>Sign in</Button>
      </form>
      <GoogleButton next={params.get('next') || '/app'} />
    </AuthShell>
  )
}

const signupSchema = z.object({
  display_name: z.string().max(120).optional(),
  email: z.string().email('Enter a valid email address.'),
  password: z.string().min(8, 'Use at least 8 characters.').refine((p) => /[^a-zA-Z]/.test(p), 'Include a number or symbol.'),
})

export function SignupPage() {
  const { signIn, config, user } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const after = useAfterSignIn()
  const [error, setError] = useState<string | null>(null)
  const form = useForm<z.infer<typeof signupSchema>>({ resolver: zodResolver(signupSchema) })
  if (config?.mode === 'local') return <LocalModeNotice />
  if (user) return <Navigate to="/app" replace />
  const qs = params.toString() ? `?${params.toString()}` : ''
  const submit = form.handleSubmit(async (v) => {
    setError(null)
    try {
      const r = await api.post<{ token?: string; verification_required?: boolean; email?: string }>('/auth/register', v)
      if (r.verification_required) {
        const q = new URLSearchParams(params)
        q.set('email', r.email ?? v.email)
        navigate(`/verify-email?${q.toString()}`)
        return
      }
      await signIn(r.token!)
      await after()
    } catch (e) {
      setError(errorMessage(e))
    }
  })
  if (config && !config.allow_registration)
    return <AuthShell title="Sign-up is closed" subtitle="Ask an administrator for an account."><Link to="/login" className="text-accent">Sign in</Link></AuthShell>
  return (
    <AuthShell aside="signup" title="Create your account" subtitle={params.get('demo') ? 'Your example study opens right after sign-up.' : 'It takes less than a minute.'} footer={<>Already have an account? <Link to={`/login${qs}`} className="font-medium text-ink underline decoration-ink/30 underline-offset-4 hover:decoration-ink">Sign in</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label="Name (optional)">{(id) => <Input id={id} autoComplete="name" className="h-10" {...form.register('display_name')} />}</Field>
        <Field label="Email" error={form.formState.errors.email?.message}>{(id) => <Input id={id} type="email" autoComplete="email" className="h-10" {...form.register('email')} />}</Field>
        <Field label="Password" help="At least 8 characters, including a number or symbol." error={form.formState.errors.password?.message}>
          {(id) => <PasswordInput id={id} autoComplete="new-password" {...form.register('password')} />}
        </Field>
        {error && <Callout tone="danger">{error}</Callout>}
        <Button type="submit" variant="primary" size="lg" className="h-11 w-full justify-center rounded-full !bg-ink !text-paper hover:opacity-90" loading={form.formState.isSubmitting}>Create account</Button>
        <p className="text-center text-[12px] text-muted">By continuing you agree to the <Link to="/terms" className="underline">Terms</Link> and <Link to="/privacy" className="underline">Privacy Policy</Link>.</p>
      </form>
      <GoogleButton next={params.get('demo') ? `/app?demo=${params.get('demo')}` : '/app'} />
    </AuthShell>
  )
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <AuthShell title="Reset your password" subtitle="We'll email you a link to choose a new password." footer={<Link to="/login" className="font-medium text-ink underline decoration-ink/30 underline-offset-4 hover:decoration-ink">Back to sign in</Link>}>
      {sent ? (
        <Callout tone="success">{sent}</Callout>
      ) : (
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault()
            if (!/^\S+@\S+\.\S+$/.test(email)) return setError('Enter a valid email address.')
            setBusy(true)
            setError(null)
            try {
              const r = await api.post<{ message: string }>('/auth/forgot-password', { email })
              setSent(r.message)
            } catch (err) {
              setError(errorMessage(err))
            } finally {
              setBusy(false)
            }
          }}
        >
          <Field label="Email" error={error}>{(id) => <Input id={id} type="email" autoComplete="email" className="h-10" value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
          <Button type="submit" variant="primary" size="lg" className="h-11 w-full justify-center rounded-full !bg-ink !text-paper hover:opacity-90" loading={busy}>Send reset link</Button>
        </form>
      )}
    </AuthShell>
  )
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!token) return <AuthShell title="Invalid link" subtitle="This reset link is incomplete."><Link to="/forgot-password" className="text-accent">Request a new link</Link></AuthShell>
  return (
    <AuthShell title="Choose a new password" subtitle="You'll be signed in on this device; other sessions are signed out.">
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault()
          if (pw.length < 8 || !/[^a-zA-Z]/.test(pw)) return setError('Use at least 8 characters, including a number or symbol.')
          if (pw !== pw2) return setError('The passwords do not match.')
          setBusy(true)
          setError(null)
          try {
            const r = await api.post<{ token: string }>('/auth/reset-password', { token, password: pw })
            await signIn(r.token)
            navigate('/app', { replace: true })
          } catch (err) {
            setError(errorMessage(err))
          } finally {
            setBusy(false)
          }
        }}
      >
        <Field label="New password">{(id) => <PasswordInput id={id} autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />}</Field>
        <Field label="Confirm password">{(id) => <PasswordInput id={id} autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} />}</Field>
        {error && <Callout tone="danger">{error}</Callout>}
        <Button type="submit" variant="primary" size="lg" className="h-11 w-full justify-center rounded-full !bg-ink !text-paper hover:opacity-90" loading={busy}>Save password</Button>
      </form>
    </AuthShell>
  )
}

/** Receives the token from the Google OAuth redirect (URL fragment, never sent to the server). */
export function OAuthCallbackPage() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const frag = new URLSearchParams(window.location.hash.slice(1))
    const token = frag.get('token')
    const next = frag.get('next') || '/app'
    window.history.replaceState(null, '', window.location.pathname)
    if (!token) {
      setError('Sign-in did not complete.')
      return
    }
    signIn(token).then(async () => {
      const demo = new URL(next, window.location.origin).searchParams.get('demo')
      if (demo) {
        try {
          const p = await api.post<{ id: number }>('/demo', { key: demo })
          return navigate(`/p/${p.id}/report`, { replace: true })
        } catch {
          /* ignore */
        }
      }
      navigate(next.startsWith('/') ? next.split('?')[0] : '/app', { replace: true })
    })
  }, [signIn, navigate])
  if (error) return <AuthShell title="Sign-in failed" subtitle={error}><Link to="/login" className="text-accent">Back to sign in</Link></AuthShell>
  return <Spinner className="p-8" label="Signing you in" />
}

/** Six-digit code e-mailed after sign-up. */
export function VerifyEmailPage() {
  const { signIn } = useAuth()
  const [params] = useSearchParams()
  const after = useAfterSignIn()
  const email = params.get('email') ?? ''
  const [digits, setDigits] = useState<string[]>(['', '', '', '', '', ''])
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [cooldown, setCooldown] = useState(30)
  const inputs = useRef<(HTMLInputElement | null)[]>([])

  useEffect(() => {
    if (cooldown <= 0) return
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000)
    return () => clearTimeout(t)
  }, [cooldown])
  useEffect(() => inputs.current[0]?.focus(), [])

  const submit = async (code: string) => {
    setBusy(true)
    setError(null)
    try {
      const r = await api.post<{ token: string }>('/auth/verify-email', { email, code })
      await signIn(r.token)
      await after()
    } catch (e) {
      setError(errorMessage(e))
      setDigits(['', '', '', '', '', ''])
      inputs.current[0]?.focus()
    } finally {
      setBusy(false)
    }
  }
  const setAt = (i: number, value: string) => {
    const clean = value.replace(/\D/g, '')
    if (clean.length > 1) {
      // Pasted code
      const next = clean.slice(0, 6).split('')
      const filled = [...next, ...Array(6 - next.length).fill('')]
      setDigits(filled)
      inputs.current[Math.min(next.length, 5)]?.focus()
      if (next.length === 6) submit(next.join(''))
      return
    }
    const next = [...digits]
    next[i] = clean
    setDigits(next)
    if (clean && i < 5) inputs.current[i + 1]?.focus()
    if (next.every((d) => d)) submit(next.join(''))
  }
  const resend = async () => {
    setError(null)
    try {
      const r = await api.post<{ message: string }>('/auth/resend-code', { email })
      setInfo(r.message)
      setCooldown(30)
    } catch (e) {
      setError(errorMessage(e))
    }
  }
  if (!email) return <AuthShell aside="signup" title="Check your email" subtitle="Open the link from the sign-up page again."><Link to="/signup" className="text-ink underline">Back to sign-up</Link></AuthShell>
  return (
    <AuthShell aside="signup" title="Check your inbox" subtitle={<>We sent a 6-digit code to <span className="font-medium text-ink">{email}</span>. It expires in 15 minutes.</>}
      footer={<>Wrong address? <Link to="/signup" className="font-medium text-ink underline decoration-ink/30 underline-offset-4">Start again</Link></>}>
      <form onSubmit={(e) => { e.preventDefault(); if (digits.every((d) => d)) submit(digits.join('')) }} className="space-y-5">
        <fieldset>
          <legend className="mb-2 text-[13px] font-medium">Verification code</legend>
          <div className="flex gap-2 sm:gap-3">
            {digits.map((d, i) => (
              <input
                key={i}
                ref={(el) => { inputs.current[i] = el }}
                value={d}
                onChange={(e) => setAt(i, e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Backspace' && !digits[i] && i > 0) inputs.current[i - 1]?.focus() }}
                inputMode="numeric"
                autoComplete={i === 0 ? 'one-time-code' : 'off'}
                maxLength={6}
                aria-label={`Digit ${i + 1}`}
                disabled={busy}
                className="!h-14 w-full min-w-0 !rounded-lg border border-paper-line bg-surface text-center font-serif text-[26px] text-ink focus:border-ink focus:outline-none"
              />
            ))}
          </div>
        </fieldset>
        {error && <Callout tone="danger">{error}</Callout>}
        {info && !error && <Callout tone="success">{info}</Callout>}
        <Button type="submit" variant="primary" size="lg" className="h-11 w-full justify-center rounded-full !bg-ink !text-paper hover:opacity-90" loading={busy} disabled={!digits.every((d) => d)}>Verify and continue</Button>
        <p className="text-center text-[13.5px] text-ink-2">
          Didn't get it? Check your spam folder or{' '}
          {cooldown > 0 ? <span>resend in {cooldown}s</span> : <button type="button" onClick={resend} className="font-medium text-ink underline decoration-ink/30 underline-offset-4">send a new code</button>}
        </p>
      </form>
    </AuthShell>
  )
}
