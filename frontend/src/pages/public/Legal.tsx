import type { ReactNode } from 'react'
import { PublicLayout } from './PublicLayout'

function Doc({ title, updated, children }: { title: string; updated?: string; children: ReactNode }) {
  return (
    <PublicLayout>
      <article className="mx-auto max-w-2xl px-4 py-14 text-[15px] leading-relaxed sm:px-6 [&_h2]:mt-8 [&_h2]:mb-2 [&_h2]:text-[17px] [&_h2]:font-semibold [&_li]:mt-1 [&_p]:mt-3 [&_p]:text-fg-2 [&_ul]:mt-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:text-fg-2">
        <h1 className="text-[30px] font-semibold tracking-tight">{title}</h1>
        {updated && <p className="!mt-1 text-[13px] !text-muted">Last updated {updated}</p>}
        {children}
      </article>
    </PublicLayout>
  )
}

export function AboutPage() {
  return (
    <Doc title="About StatEase Analytics">
      <p>StatEase Analytics helps students, researchers and analysts go from a spreadsheet to a research-ready report without writing code or learning statistical software.</p>
      <h2>How results are computed</h2>
      <p>Every number comes from established open-source libraries (SciPy, statsmodels and pingouin) and is verified against published reference results. Interpretations are generated from the computed statistics with fixed templates — no AI writes or alters numbers.</p>
      <h2>Demos</h2>
      <p>The three demo projects use fictional sample data created for illustration. Their results must not be cited as real findings.</p>
    </Doc>
  )
}

export function PrivacyPage() {
  return (
    <Doc title="Privacy Policy" updated="October 2026">
      <p>This policy describes how an installation of StatEase Analytics handles your information. The operator of the installation you use is responsible for it.</p>
      <h2>What we store</h2>
      <ul>
        <li>Account details: your email address, optional name and a securely hashed password, or your Google account identifier if you sign in with Google.</li>
        <li>Your files, datasets, analysis settings, results and reports, kept so you can return to your projects.</li>
        <li>A security log of actions such as sign-ins, imports and exports. It does not contain passwords or data values.</li>
      </ul>
      <h2>What we do not do</h2>
      <ul>
        <li>Your data is not sold, shared with advertisers, or used to train models.</li>
        <li>No third-party analytics or advertising trackers are used.</li>
        <li>Google sign-in only receives your email address, name and account identifier.</li>
      </ul>
      <h2>Your choices</h2>
      <p>You can delete datasets and projects at any time; deleting a project removes its files from storage. To close your account, contact the operator of this installation.</p>
    </Doc>
  )
}

export function TermsPage() {
  return (
    <Doc title="Terms of Use" updated="October 2026">
      <p>By using StatEase Analytics you agree to these terms.</p>
      <h2>Your data</h2>
      <p>You keep all rights to the data you upload. You are responsible for having permission to use it, including any ethics or data-protection approvals your research requires.</p>
      <h2>Statistical results</h2>
      <p>Results are computed with established methods and tested against reference values, but you remain responsible for choosing appropriate analyses for your research design and for how results are interpreted and reported.</p>
      <h2>Acceptable use</h2>
      <p>Do not upload data you are not allowed to process, attempt to access other users' projects, or interfere with the service.</p>
      <h2>No warranty</h2>
      <p>The service is provided as is, without warranties of any kind, to the extent permitted by law.</p>
    </Doc>
  )
}
