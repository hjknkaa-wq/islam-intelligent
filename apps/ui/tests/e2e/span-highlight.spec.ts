import { test, expect, type Page, type TestInfo } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

function getEvidenceDir(): string {
  return path.resolve(__dirname, '../../../../.sisyphus/evidence');
}

async function saveEvidenceScreenshot(
  page: Page,
  testInfo: TestInfo,
  canonicalFileName: string,
) {
  const dir = getEvidenceDir();
  fs.mkdirSync(dir, { recursive: true });

  const perProject = canonicalFileName.replace(/\.png$/i, `-${testInfo.project.name}.png`);
  await page.screenshot({ path: path.join(dir, perProject), fullPage: true });

  // Avoid cross-browser write collisions on the canonical filenames.
  if (testInfo.project.name === 'chromium') {
    await page.screenshot({ path: path.join(dir, canonicalFileName), fullPage: true });
  }
}

test.describe('Evidence span highlighting (hash + offsets)', () => {
  test('opens evidence view and shows verified highlight', async ({ page }, testInfo) => {
    await page.goto('/dev/evidence-highlight');

    const verifiedSection = page.locator('section', { has: page.getByRole('heading', { name: 'Verified' }) });

    // Mimic an "open evidence" interaction even though this dev page is always expanded.
    await verifiedSection.getByRole('heading', { name: 'Verified' }).click();

    await expect(verifiedSection.getByText('verified', { exact: true })).toBeVisible();
    await expect(verifiedSection.getByText('span verification failed', { exact: true })).toHaveCount(0);

    // Highlighted text must match the snippet_text.
    await expect(verifiedSection.locator('mark')).toHaveText('بالعالم');

    await saveEvidenceScreenshot(page, testInfo, 'task-17-highlight.png');
  });

  test('shows span verification failed when mismatch occurs', async ({ page }, testInfo) => {
    await page.goto('/dev/evidence-highlight');

    const mismatchSection = page.locator('section', { has: page.getByRole('heading', { name: 'Mismatch' }) });

    await expect(mismatchSection.getByText('failed', { exact: true })).toBeVisible();
    await expect(mismatchSection.getByText('span verification failed', { exact: true })).toBeVisible();
    await expect(mismatchSection.locator('mark')).toHaveCount(0);

    await saveEvidenceScreenshot(page, testInfo, 'task-17-highlight-fail.png');
  });
});
