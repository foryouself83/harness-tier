import { test, expect } from '@playwright/test';

// 메인화면 smoke — "앱이 뜨는가"의 결정적 검증(임의 시나리오 아님).
// baseURL 은 playwright.config 의 use.baseURL 로 주입된다(여기선 '/' 상대경로만 사용).
test('main screen loads', async ({ page }) => {
  const response = await page.goto('/');
  expect(response, '메인화면 응답이 있어야 한다').toBeTruthy();
  expect(response!.status(), '메인화면이 4xx/5xx 가 아니어야 한다').toBeLessThan(400);
  await expect(page, 'document title 이 비어있지 않아야 한다').toHaveTitle(/.+/);
});
