import { test, expect } from '@playwright/test';

test.describe('Next.js Enterprise Multimodal RAG Application', () => {
  const TEST_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLWFkbWluLWRlZmF1bHQiLCJlbWFpbCI6ImFkbWluQGVudGVycHJpc2UuaW50ZXJuYWwiLCJ0ZW5hbnRfaWQiOiJkZWZhdWx0LXRlbmFudCIsInJvbGUiOiJzeXN0ZW1fYWRtaW4iLCJleHAiOjE3OTQ1NTIwOTAsImlhdCI6MTc5NDQ2NTY5MCwiaXNzIjoicmFnLWludGVsbGlnZW5jZS1hcGkifQ.udz0XPMVfRvsWPSK4NB2ze3ZOkTDOtecEccRKQWEwU0';

  test.beforeEach(async ({ context, page }) => {
    await context.addCookies([
      {
        name: 'rag_session',
        value: TEST_TOKEN,
        domain: 'localhost',
        path: '/',
        httpOnly: true,
        sameSite: 'Lax',
      },
    ]);
    await page.goto('http://localhost:3001');
    await page.evaluate((tok) => {
      localStorage.setItem('rag_tenant_id', 'default-tenant');
    }, TEST_TOKEN);
    await page.reload();
  });

  test('Module 1: Overview Dashboard renders live PostgreSQL & Qdrant metrics', async ({ page }) => {
    await expect(page.locator('main').getByRole('heading', { level: 1 })).toHaveText('Overview Dashboard');
    await expect(page.getByText('TOTAL DOCUMENTS')).toBeVisible();
    await expect(page.getByText('DOCUMENT CHUNKS')).toBeVisible();
    await expect(page.locator('div.text-3xl.font-bold').first()).toBeVisible();
  });

  test('Module 2: Research Chat submits inquiry and displays citations', async ({ page }) => {
    await page.goto('http://localhost:3001/chat');
    await expect(page.locator('main').getByRole('heading', { level: 1 })).toHaveText('AI Research Workspace');

    const promptBtn = page.getByRole('button', { name: /What is the self-attention mechanism/i });
    await expect(promptBtn).toBeVisible();
    await promptBtn.click();

    await expect(page.getByText('What is the self-attention mechanism')).toBeVisible();
    await expect(page.getByText(/Verified Evidence & Citations/i)).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('attention.pdf').first()).toBeVisible();
  });

  test('Module 3: Knowledge Base shows live inventory and hero dropzone', async ({ page }) => {
    await page.goto('http://localhost:3001/documents');
    await expect(page.locator('main').getByRole('heading', { level: 1 })).toHaveText('Knowledge Base');

    await expect(page.getByText('embedding.pdf')).toBeVisible();
    await expect(page.getByText('python_intro.txt')).toBeVisible();

    await page.click('button:has-text("Drag & Drop Upload")');
    await expect(page.getByText('Drag & Drop your files here')).toBeVisible();
    await expect(page.getByText(/25 MB per file/i)).toBeVisible();
  });

  test('Module 4: Retrieval Explorer evaluates dense, sparse, and reranking stages', async ({ page }) => {
    await page.goto('http://localhost:3001/retrieval');
    await expect(page.locator('main').getByRole('heading', { level: 1 })).toHaveText('Retrieval Explorer');

    await page.click('button:has-text("Inspect Pipeline")');
    await expect(page.getByText(/Retrieved Chunks & Calibration Scores/i)).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Stage 1: Dense')).toBeVisible();
    await expect(page.getByText('Stage 4: Reranker')).toBeVisible();
  });

  test('Module 5: Pipeline Monitor loads persisted jobs', async ({ page }) => {
    await page.goto('http://localhost:3001/pipeline');
    await expect(page.locator('main').getByRole('heading', { level: 1 })).toHaveText('Pipeline Monitor');
    await expect(page.getByText('Persisted Ingestion Jobs')).toBeVisible();
  });

  test('Module 6: System Health displays live component status', async ({ page }) => {
    await page.goto('http://localhost:3001/health');
    await expect(page.locator('main').getByRole('heading', { level: 1 })).toHaveText('System Health');
    await expect(page.getByText('FastAPI Gateway')).toBeVisible();
    await expect(page.getByText('Neon PostgreSQL')).toBeVisible();
    await expect(page.getByText('Vector Store (Qdrant)')).toBeVisible();
  });

  test('Module 7: Activity & Audit logs operational events', async ({ page }) => {
    await page.goto('http://localhost:3001/audit');
    await expect(page.locator('main').getByRole('heading', { level: 1 })).toHaveText('Activity & Audit');
    await expect(page.getByText('DOCUMENT_INDEXED').first()).toBeVisible();
  });

  test('Module 8: Settings updates retrieval configuration', async ({ page }) => {
    await page.goto('http://localhost:3001/settings');
    await expect(page.locator('main').getByRole('heading', { level: 1 })).toHaveText('Settings');
    await expect(page.getByText('Default Retrieval Configuration')).toBeVisible();

    await page.click('button:has-text("Save Configuration")');
    await expect(page.getByText(/Tenant settings saved successfully/i)).toBeVisible();
  });
});
