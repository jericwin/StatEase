import { expect, type Page, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const SHOTS = process.env.E2E_SCREENSHOTS
const SERVER_LOG = process.env.E2E_SERVER_LOG ?? '../backend/var/e2e-server.log'

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: join(SHOTS, `${test.info().project.name}-${name}.png`) })
}

async function noHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow, 'page should not scroll horizontally').toBeLessThanOrEqual(1)
}

function formulationCsv(): string {
  const rows = ['Panelist,Formulation,Taste,Texture,Aroma,Overall Acceptability']
  let seed = 11
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
  for (let i = 1; i <= 40; i++) {
    const f = i <= 20 ? 'Formulation 1' : 'Formulation 2'
    const shift = i <= 20 ? 0 : 1.1
    const s = (b: number) => Math.max(1, Math.min(9, Math.round(b + shift + (rnd() - 0.5) * 3)))
    rows.push([`P${i}`, f, s(6), s(6.5), s(6.2), (6 + shift + (rnd() - 0.5) * 2).toFixed(2)].join(','))
  }
  return rows.join('\n')
}

async function signUp(page: Page) {
  const email = `e2e-${test.info().project.name}-${Date.now()}@example.com`
  await page.goto('/signup')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill('test-pass-123')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/verify-email/)
  await expect(page.getByRole('heading', { name: 'Check your inbox' })).toBeVisible()
  await shot(page, '02a-verify')
  // With SMTP off, the server logs the e-mail it would have sent; read the code from there.
  let code = ''
  await expect
    .poll(() => {
      const log = readFileSync(SERVER_LOG, 'utf8')
      const at = log.lastIndexOf(email)
      code = at < 0 ? '' : (/verification code is: (\d{6})/.exec(log.slice(at))?.[1] ?? '')
      return code
    })
    .toMatch(/^\d{6}$/)
  await page.getByLabel('Digit 1').fill(code)
  await expect(page).toHaveURL(/\/app$/)
  return email
}

test('landing → sign up → upload → compare → objectives → edit report → export', async ({ page }, info) => {
  const mobile = info.project.name === 'mobile'
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: /results chapter/i })).toBeVisible()
  await expect(page.getByText('Growth of pechay by fertilizer treatment').first()).toBeVisible()
  await shot(page, '01-landing')
  await noHorizontalOverflow(page)

  await signUp(page)
  await expect(page.getByRole('button', { name: /Upload data/ })).toBeVisible()
  await shot(page, '02-dashboard')

  // Upload from the dashboard: the project is created and the import wizard starts automatically.
  await page.getByLabel('Choose a data file').setInputFiles({ name: 'formulations.csv', mimeType: 'text/csv', buffer: Buffer.from(formulationCsv()) })
  await expect(page.getByText(/First 40 rows/)).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: 'Continue to variables' }).click()
  await page.getByLabel('Measurement level of Taste').selectOption('numeric')
  await page.getByLabel('Measurement level of Texture').selectOption('numeric')
  await page.getByLabel('Measurement level of Aroma').selectOption('numeric')
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await page.getByRole('button', { name: 'Import data' }).click()

  // Import lands on data cleaning; this file is clean, so skip to objectives, then skip those too
  // (the report step below uses them).
  await expect(page.getByRole('heading', { name: 'Clean data', level: 1 })).toBeVisible()
  await expect(page.getByText(/No common problems found/)).toBeVisible()
  await page.getByRole('link', { name: /Skip — the data is already clean/ }).click()
  await expect(page.getByRole('heading', { name: 'Statement of the problem' })).toBeVisible()
  await shot(page, '03a-objectives-page')
  await page.getByRole('link', { name: /Skip/ }).click()

  await expect(page.getByRole('heading', { name: 'Analyze data' })).toBeVisible()
  await expect(page.getByText('Compare Formulation 1 and Formulation 2').first()).toBeVisible()
  await shot(page, '03-recommended')

  // Compare: Formulation 1 vs Formulation 2 across all measures.
  await page.getByRole('tab', { name: 'Compare' }).click()
  await expect(page.getByRole('button', { name: 'Formulation 1' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'Compare', exact: true }).click()
  await expect(page.getByText('Comparison of Formulation 1 and Formulation 2').first()).toBeVisible({ timeout: 30_000 })
  await shot(page, '04-compare')
  await noHorizontalOverflow(page)

  // Objectives → report.
  await page.getByRole('button', { name: /Add to report/ }).click()
  await page.getByLabel('Objectives of the study').fill(
    '1. Determine the acceptability of Formulation 1.\n2. Determine the acceptability of Formulation 2.\n3. Determine whether there is a significant difference between Formulation 1 and Formulation 2.',
  )
  await page.getByRole('button', { name: 'Find the variables' }).click()
  await expect(page.getByText('Two-Group Comparison').first()).toBeVisible()
  await shot(page, '05-objectives')
  await page.getByRole('button', { name: /Analyze objectives/ }).click()
  await expect(page).toHaveURL(/\/report\?id=\d+/, { timeout: 60_000 })
  if (!mobile) await expect(page.getByText('Objectives of the Study')).toBeVisible()

  if (mobile) await page.getByRole('tab', { name: 'Checklist' }).click()
  const items = page.getByRole('list', { name: 'Report items' })
  await expect(items.getByText(/Table 1/)).toBeVisible()
  await shot(page, '06-report')

  // Edit a table: rename it.
  await items.getByRole('button', { name: /^Table 1/ }).click()
  const title = page.getByRole('dialog').getByLabel('Title')
  await title.fill('Acceptability of Formulation 1')
  await shot(page, '07-table-editor')
  // Recompute the same table for Formulation 2 (values must change, label follows the data).
  await page.getByRole('dialog').getByRole('tab', { name: 'Data' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Formulation 1' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Formulation 2' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Recalculate' }).click()
  await expect(page.getByText('Recalculated from your data.')).toBeVisible({ timeout: 30_000 })
  await page.keyboard.press('Escape')
  await expect(page.getByText(/Saved/).first()).toBeVisible({ timeout: 15_000 })

  if (mobile) await page.getByRole('tab', { name: 'Export' }).click()
  const [docx] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /Word \(\.docx\)/ }).click()])
  expect(readFileSync(await docx.path()).subarray(0, 2).toString()).toBe('PK')
  const [xlsx] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /Excel \(\.xlsx\)/ }).click()])
  expect(readFileSync(await xlsx.path()).subarray(0, 2).toString()).toBe('PK')
  await noHorizontalOverflow(page)

  // The report and its edits persist after reload.
  await page.reload()
  if (mobile) await page.getByRole('tab', { name: 'Checklist' }).click()
  await expect(page.getByRole('list', { name: 'Report items' }).getByText(/Acceptability of Formulation 1|Descriptive Statistics/).first()).toBeVisible()
})

test('public demo preview works without signing in', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: /Experimental Group Comparison/ }).click()
  await expect(page.getByText('Fictional sample data').first()).toBeVisible()
  await expect(page.getByText(/Comparison of Control and Treatment/).first()).toBeVisible()
  await shot(page, '08-demo-preview')
  await noHorizontalOverflow(page)
  await page.getByRole('link', { name: /Try it with this data/ }).click()
  await expect(page).toHaveURL(/\/signup\?demo=experiment/)
})

test('auth pages: validation, password toggle, forgot password', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByText('Enter a valid email address.')).toBeVisible()
  await page.getByLabel('Email').fill('nobody@example.com')
  const pw = page.getByLabel('Password', { exact: true })
  await pw.fill('wrong-password-1')
  await page.getByRole('button', { name: 'Show password' }).click()
  await expect(pw).toHaveAttribute('type', 'text')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByText('Email or password is incorrect.')).toBeVisible()
  await shot(page, '09-login')
  await page.getByRole('link', { name: 'Forgot password?' }).click()
  await page.getByLabel('Email').fill('nobody@example.com')
  await page.getByRole('button', { name: 'Send reset link' }).click()
  await expect(page.getByText(/If an account exists/)).toBeVisible()
  // Protected pages redirect to sign-in.
  await page.goto('/app')
  await expect(page).toHaveURL(/\/login\?next=%2Fapp/)
})

test('demo from dashboard and responsive layouts', async ({ page }) => {
  test.skip(test.info().project.name !== 'desktop', 'resizes through all widths once')
  await signUp(page)
  await page.getByRole('button', { name: /Open a demo/ }).click()
  await page.getByRole('button', { name: /Fertilizer Trial on Pechay/ }).click()
  await expect(page.getByText('Objectives of the Study')).toBeVisible({ timeout: 90_000 })
  // Switch a figure to a horizontal bar chart right on the report page; the choice is saved with the report.
  const style = page.getByRole('combobox', { name: 'Chart style' }).first()
  await style.selectOption('hbar')
  await expect(page.getByText(/Saved/).first()).toBeVisible({ timeout: 15_000 })
  await page.reload()
  await expect(page.getByRole('combobox', { name: 'Chart style' }).first()).toHaveValue('hbar')
  if (SHOTS) await page.screenshot({ path: join(SHOTS, 'demo-report-hbar.png') })
  const base = page.url().replace(/\/report.*/, '')
  for (const width of [360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 860 })
    for (const path of ['', '/data', '/analyze', '/report']) {
      await page.goto(base + path)
      await page.waitForLoadState('networkidle')
      await noHorizontalOverflow(page)
      if (SHOTS && [390, 1440].includes(width)) await page.screenshot({ path: join(SHOTS, `w${width}${path.replace('/', '-') || '-overview'}.png`) })
    }
    for (const path of ['/', '/app', '/login']) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      await noHorizontalOverflow(page)
    }
  }
})

test('accessible names on public pages', async ({ page }) => {
  test.skip(test.info().project.name !== 'desktop', 'desktop only')
  for (const path of ['/', '/login', '/signup']) {
    await page.goto(path)
    await page.waitForLoadState('networkidle')
    const unlabeled = await page.evaluate(() =>
      [...document.querySelectorAll('button, a, input, select, textarea')].filter((el) => {
        const e = el as HTMLElement
        const name = e.getAttribute('aria-label') || e.textContent?.trim() || (e as HTMLInputElement).labels?.[0]?.textContent || e.getAttribute('title') || e.getAttribute('placeholder')
        return !name && e.offsetParent !== null
      }).length,
    )
    expect(unlabeled, path).toBe(0)
  }
})

test('unknown pages show a 404 page, not a blank screen or a silent redirect', async ({ page }) => {
  await page.goto('/no-such-page')
  await expect(page.getByRole('heading', { name: /This page doesn.t exist/ })).toBeVisible()
  await expect(page.getByRole('link', { name: /Back to home/ })).toBeVisible()
  await shot(page, '12-not-found')
  await noHorizontalOverflow(page)
})

test('data cleaning: suggested fixes, preview, save a cleaned version and export it with the log', async ({ page }) => {
  await signUp(page)
  const messy = ['ID,Gender,Age,Q1', '1,Male,21,4', '2,male ,22,5', '3,F,23,3', '4,N/A,n/a,99', '5,M,24,5', '5,M,24,5', '6,Female,25,55', ',,,', '7,female,19,2'].join('\n')
  await page.getByLabel('Choose a data file').setInputFiles({ name: 'survey_raw.csv', mimeType: 'text/csv', buffer: Buffer.from(messy) })
  await page.getByRole('button', { name: 'Continue to variables' }).click({ timeout: 30_000 })
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await page.getByRole('button', { name: 'Import data' }).click()

  await expect(page.getByRole('heading', { name: 'Clean data', level: 1 })).toBeVisible()
  await expect(page.getByText('Gender: merge spellings of the same answer')).toBeVisible()
  await expect(page.getByText(/Remove 1 duplicate row/).first()).toBeVisible()
  await expect(page.getByText('Cleaning log')).toBeVisible()
  await shot(page, '13-clean')
  await noHorizontalOverflow(page)

  await page.getByRole('button', { name: 'Save cleaned version' }).click()
  await expect(page.getByText(/Cleaned data saved as version 2/)).toBeVisible({ timeout: 30_000 })
  const [xlsx] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /Cleaned data \(Excel \+ cleaning log\)/ }).first().click()])
  expect(readFileSync(await xlsx.path()).subarray(0, 2).toString()).toBe('PK')
  await shot(page, '14-clean-saved')
})
