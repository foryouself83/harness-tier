import { test, expect } from '@playwright/test';

// Main-screen smoke — a deterministic check of "does the app come up" (not an arbitrary scenario).
// baseURL is injected via use.baseURL in playwright.config (here we only use the '/' relative path).
test('main screen loads', async ({ page }) => {
  const response = await page.goto('/');
  expect(response, 'the main screen should return a response').toBeTruthy();
  expect(response!.status(), 'the main screen should not be a 4xx/5xx').toBeLessThan(400);
  await expect(page, 'the document title should not be empty').toHaveTitle(/.+/);
});
