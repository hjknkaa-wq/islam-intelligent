import { test, expect, type Page, type TestInfo } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

type GoldenCase = {
  case_id: string;
  query: string;
  expected_verdict: 'answer' | 'abstain';
};

type QuranUnit = {
  canonical_id: string;
  text: string;
};

function getRepoRoot(): string {
  return path.resolve(__dirname, '../../../../');
}

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

function loadGoldenCases(): GoldenCase[] {
  const file = path.join(getRepoRoot(), 'eval/cases/golden.yaml');
  const raw = fs.readFileSync(file, 'utf8');

  const cases: GoldenCase[] = [];
  let current: Partial<GoldenCase> | null = null;

  for (const line of raw.split(/\r?\n/)) {
    const caseStart = line.match(/^\s*-\s*case_id:\s*"?([^"\s]+)"?\s*$/);
    if (caseStart) {
      if (current?.case_id && current.query && current.expected_verdict) {
        cases.push(current as GoldenCase);
      }
      current = { case_id: caseStart[1] };
      continue;
    }

    if (!current) continue;

    const query = line.match(/^\s*query:\s*"(.*)"\s*$/);
    if (query) {
      current.query = query[1];
      continue;
    }

    const verdict = line.match(/^\s*expected_verdict:\s*(answer|abstain)\s*$/);
    if (verdict) {
      current.expected_verdict = verdict[1] as GoldenCase['expected_verdict'];
    }
  }

  if (current?.case_id && current.query && current.expected_verdict) {
    cases.push(current as GoldenCase);
  }

  return cases;
}

function pickGoldenCase(verdict: GoldenCase['expected_verdict'], preferCaseId?: string): GoldenCase {
  const cases = loadGoldenCases().filter((c) => c.expected_verdict === verdict);
  if (!cases.length) {
    throw new Error(`No golden cases found for verdict=${verdict}`);
  }

  if (preferCaseId) {
    const preferred = cases.find((c) => c.case_id === preferCaseId);
    if (preferred) return preferred;
  }

  return cases[0];
}

function loadQuranTexts(): string[] {
  const file = path.join(getRepoRoot(), 'data/fixtures/quran_minimal.yaml');
  const raw = fs.readFileSync(file, 'utf8');

  const texts: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    const m = line.match(/^\s*text:\s*"(.*)"\s*$/);
    if (m) texts.push(m[1]);
  }
  return texts;
}

function loadQuranUnits(): QuranUnit[] {
  const file = path.join(getRepoRoot(), 'data/fixtures/quran_minimal.yaml');
  const raw = fs.readFileSync(file, 'utf8');

  const units: QuranUnit[] = [];
  let pendingCanonicalId: string | null = null;

  for (const line of raw.split(/\r?\n/)) {
    const id = line.match(/^\s*-\s*canonical_id:\s*"(quran:[^"]+)"\s*$/);
    if (id) {
      pendingCanonicalId = id[1];
      continue;
    }

    const text = line.match(/^\s*text:\s*"(.*)"\s*$/);
    if (text && pendingCanonicalId) {
      units.push({ canonical_id: pendingCanonicalId, text: text[1] });
      pendingCanonicalId = null;
    }
  }

  return units;
}

function pickAnswerableLexicalQueryFromQuranFixtures(): string {
  const texts = loadQuranTexts();
  if (!texts.length) throw new Error('No Quran fixture texts found');

  const tokenCounts = new Map<string, number>();
  for (const text of texts) {
    // Keep letters/marks (diacritics), normalize separators to spaces.
    const normalized = text.replace(/[^\p{L}\p{M}\s]+/gu, ' ');
    const tokens = normalized
      .split(/\s+/)
      .map((t) => t.trim())
      .filter(Boolean)
      .filter((t) => t.length >= 3);

    // Count unique tokens per line to reduce overweighting repeated tokens.
    for (const token of new Set(tokens)) {
      tokenCounts.set(token, (tokenCounts.get(token) ?? 0) + 1);
    }
  }

  const candidates = [...tokenCounts.entries()]
    .filter(([, count]) => count >= 2)
    .sort((a, b) => {
      // Prefer tokens that appear in many ayahs, then longer tokens.
      if (b[1] !== a[1]) return b[1] - a[1];
      return b[0].length - a[0].length;
    });

  if (!candidates.length) {
    // Fallback: a common token in many Arabic texts.
    return 'اللَّه';
  }

  return candidates[0][0];
}

async function submitQuery(page: Page, query: string) {
  await page.goto('/');
  await page.getByPlaceholder('Ask about Islam...').fill(query);
  await page.getByRole('button', { name: 'Ask' }).click();
}

async function mockRagQuery(
  page: Page,
  responder: (query: string) => Record<string, unknown>,
) {
  await page.route('**/rag/query', async (route) => {
    const request = route.request();
    if (request.method().toUpperCase() !== 'POST') {
      await route.fallback();
      return;
    }

    let query = '';
    try {
      const body = JSON.parse(request.postData() ?? '{}') as { query?: string };
      query = typeof body.query === 'string' ? body.query : '';
    } catch {
      query = '';
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(responder(query)),
    });
  });
}

test.describe('Provenance-first UI', () => {
  test('answer_shows_citations', async ({ page }, testInfo) => {
    const answerQuery = pickAnswerableLexicalQueryFromQuranFixtures();

    const quranUnits = loadQuranUnits();
    const citationsFromFixtures = quranUnits.slice(0, 3).map((u, idx) => {
      return {
        evidence_span_id: `fixture-quran-${idx + 1}`,
        canonical_id: u.canonical_id,
        snippet: u.text,
      };
    });

    await mockRagQuery(page, (query) => {
      if (query !== answerQuery) {
        return {
          verdict: 'abstain',
          statements: [],
          abstain_reason: 'insufficient_evidence',
          fail_reason: 'insufficient_evidence',
          retrieved_count: 0,
          sufficiency_score: 0.0,
        };
      }

      return {
        verdict: 'answer',
        statements: [
          {
            text: 'Statement 1 must be backed by evidence.',
            citations: [citationsFromFixtures[0]].filter(Boolean),
          },
          {
            text: 'Statement 2 must be backed by evidence.',
            citations: [citationsFromFixtures[1]].filter(Boolean),
          },
          {
            text: 'Statement 3 must be backed by evidence.',
            citations: [citationsFromFixtures[2]].filter(Boolean),
          },
        ],
        abstain_reason: null,
        fail_reason: null,
        retrieved_count: citationsFromFixtures.length,
        sufficiency_score: 1.0,
      };
    });

    await submitQuery(page, answerQuery);

    await expect(page.getByText('Answer', { exact: true })).toBeVisible();
    await expect(page.getByText('Abstain', { exact: true })).toHaveCount(0);

    const statementCards = page.locator('div.mb-6').filter({ has: page.locator('sup') });
    const statementCount = await statementCards.count();
    expect(statementCount).toBeGreaterThan(0);

    for (let i = 0; i < statementCount; i++) {
      const citations = statementCards.nth(i).locator('sup');
      const citationCount = await citations.count();
      expect(citationCount).toBeGreaterThan(0);
      await expect(citations.first()).toBeVisible();
    }

    // Citations are clickable and open evidence details.
    const firstStatement = statementCards.first();
    await firstStatement.locator('sup').first().click();
    await expect(firstStatement.getByText('Source:', { exact: false })).toBeVisible();
    await expect(firstStatement.getByText('Evidence ID:', { exact: false })).toBeVisible();

    await saveEvidenceScreenshot(page, testInfo, 'task-26-ui-answer.png');
  });

  test('abstain_shows_missing_requirements', async ({ page }, testInfo) => {
    const abstainCase = pickGoldenCase('abstain', 'abstain_004_obscure_topic');

    await mockRagQuery(page, () => {
      return {
        verdict: 'abstain',
        statements: [],
        abstain_reason: 'insufficient_evidence',
        fail_reason: 'insufficient_evidence',
        retrieved_count: 0,
        sufficiency_score: 0.0,
      };
    });

    await submitQuery(page, abstainCase.query);

    await expect(page.getByText('Abstain', { exact: true })).toBeVisible();

    // Abstain mode must surface what was missing and what was retrieved.
    await expect(page.getByRole('heading', { name: 'Retrieved evidence' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Missing requirements' })).toBeVisible();
    await expect(page.getByText('Evidence retrieved:', { exact: false })).toBeVisible();

    await saveEvidenceScreenshot(page, testInfo, 'task-26-ui-abstain.png');
  });
});
