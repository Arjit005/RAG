import { test, expect } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';

test.describe('Next.js Knowledge Base: Drag-and-Drop Ingestion Flow', () => {
  const testPdfPath = path.join(__dirname, 'test_upload_sample.txt');

  test.beforeAll(async () => {
    fs.writeFileSync(testPdfPath, 'Sample test content for authenticated drag and drop ingestion verification.');
  });

  test.afterAll(async () => {
    if (fs.existsSync(testPdfPath)) {
      fs.unlinkSync(testPdfPath);
    }
  });

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

  test('E2E: Drag-and-drop / file selection, removal, size check, upload and job creation', async ({ page }) => {
    // 1. Navigate to Documents page
    await page.goto('http://localhost:3001/documents');
    await expect(page.locator('main').getByRole('heading', { level: 1 })).toHaveText('Knowledge Base');

    // 2. Open Drag & Drop tab
    const uploadTabBtn = page.getByRole('button', { name: /Drag & Drop Upload/i });
    await expect(uploadTabBtn).toBeVisible();
    await uploadTabBtn.click();

    // 3. Verify dropzone elements
    await expect(page.getByText('Drag & Drop your files here')).toBeVisible();
    await expect(page.getByText(/25 MB per file/i)).toBeVisible();

    // 4. File selection via input
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(testPdfPath);

    // 5. Verify staged file in list
    await expect(page.getByText('Staged for Ingestion')).toBeVisible();
    await expect(page.getByText('test_upload_sample.txt')).toBeVisible();

    // 6. Test file removal
    const removeBtn = page.locator('button:has(svg.lucide-x)').first();
    await expect(removeBtn).toBeVisible();
    await removeBtn.click();
    await expect(page.getByText('test_upload_sample.txt')).not.toBeVisible();

    // 7. Re-stage file for real upload
    await fileInput.setInputFiles(testPdfPath);
    await expect(page.getByText('test_upload_sample.txt')).toBeVisible();

    // 8. Click Upload & Ingest
    const uploadBtn = page.getByRole('button', { name: /Upload & Ingest/i });
    await expect(uploadBtn).toBeVisible();
    await uploadBtn.click();

    // 9. Verify success result with Job ID
    await expect(page.getByText(/Accepted \(Job:/i)).toBeVisible({ timeout: 15000 });

    // 10. Navigate to Pipeline Monitor and verify the ingestion job is tracked
    await page.goto('http://localhost:3001/pipeline');
    await expect(page.locator('main').getByRole('heading', { level: 1 })).toHaveText('Pipeline Monitor');
    await expect(page.getByText('job-').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('COMPLETED').first()).toBeVisible({ timeout: 10000 });
  });
});
