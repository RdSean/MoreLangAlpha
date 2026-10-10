import { readFileSync } from 'node:fs';
import { Buffer } from 'node:buffer';
import { test, expect, mockAPI, resetMockServer } from './fixtures.js';

const parent = { user_id: 'parent-1', name: '家长', role: 'parent', household_id: 'family-1', onboarding_completed: true, has_api_key: true };
const series = [{ set_code: 'me55', series_name: '30周年庆典', total: 21 }, { set_code: 'me55c', series_name: '经典（Classic）', total: 20 }];
const cards = Array.from({ length: 41 }, (_, index) => ({
  card_id: `card-${index + 1}`, source_card_id: `test-${index + 1}`, set_code: index < 21 ? 'me55' : 'me55c',
  series_name: index < 21 ? series[0].series_name : series[1].series_name,
  name: `皮卡丘 ${index + 1}`, category: '宝可梦', element: '雷', hp: 60, stage: '基础', card_number: String(index + 1).padStart(3, '0'),
  rarity: '稀有', illustrator: 'Artist', notes: '', image_width: 640, image_height: 880,
}));
const png = process.env.POKEMON_CARD_FIXTURE_PATH
  ? readFileSync(process.env.POKEMON_CARD_FIXTURE_PATH)
  : Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jN3sAAAAASUVORK5CYII=', 'base64');

async function setup(page, role = 'parent') {
  await resetMockServer();
  await mockAPI(page, {
    'GET /auth/me': { ...parent, role },
    'GET /auth/children': [],
    'GET /education/calendar/sources': [],
    'GET /education/pokemon-cards': route => {
      const params = new URL(route.request().url()).searchParams;
      const filtered = cards.filter(card => !params.get('set_code') || card.set_code === params.get('set_code'));
      const pageNumber = Math.min(Number(params.get('page') || 1), Math.max(1, Math.ceil(filtered.length / 20)));
      return route.fulfill({ json: { items: filtered.slice((pageNumber - 1) * 20, pageNumber * 20), total: filtered.length, page: pageNumber, page_size: 20, series } });
    },
    'GET /education/pokemon-cards/*/image': route => route.fulfill({ contentType: 'image/png', body: png }),
  });
}

for (const theme of ['light', 'nasa']) for (const [width, columns] of [[375, 2], [1280, 4], [1600, 5]]) {
  test(`${theme} ${width}px catalog entry, card details and pagination`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    await setup(page);
    await page.goto('/settings?tab=family');
    await page.getByRole('link', { name: '宝可梦卡牌' }).click();
    await expect(page).toHaveURL(/\/settings\/pokemon-cards$/);
    await expect(page.locator('.pokemon-catalog-card')).toHaveCount(20);
    const grid = page.getByLabel('卡牌目录', { exact: true });
    expect(await grid.evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length)).toBe(columns);
    expect(await page.locator('.pokemon-catalog-page').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    const firstImage = grid.locator('img').first();
    await expect.poll(() => firstImage.evaluate(element => element.complete && element.naturalWidth > 0)).toBe(true);
    expect(await firstImage.evaluate(element => getComputedStyle(element).objectFit)).toBe('contain');
    await page.screenshot({ path: testInfo.outputPath(`catalog-${theme}-${width}.png`), animations: 'disabled' });
    await page.getByRole('button', { name: '查看皮卡丘 1 · 001', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText('Artist')).toBeVisible();
    await expect.poll(() => dialog.locator('img').evaluate(element => element.complete && element.naturalWidth > 0)).toBe(true);
    const bounds = await dialog.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`card-detail-${theme}-${width}.png`), animations: 'disabled' });
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: '下一页' }).click();
    await expect(page.getByRole('button', { name: '查看皮卡丘 21 · 021', exact: true })).toBeVisible();
    await page.getByRole('button', { name: '下一页' }).click();
    await expect(page.locator('.pokemon-catalog-card')).toHaveCount(1);
    await expect(page.getByRole('button', { name: '下一页' })).toBeDisabled();
    await page.getByLabel('卡牌系列').selectOption('me55c');
    await expect(page.locator('.pokemon-catalog-card')).toHaveCount(20);
    await expect(page.getByLabel('页码')).toHaveValue('1');
    await page.getByLabel('卡牌系列').selectOption('');
    await expect(page.getByText('共 41 张卡牌')).toBeVisible();
    await page.getByRole('link', { name: '家庭账户', exact: true }).click();
    await expect(page).toHaveURL(/\/settings\?tab=family$/);
  });
}

test('student cannot open the parent catalog', async ({ page }) => {
  await setup(page, 'student');
  await page.goto('/settings/pokemon-cards');
  await expect(page.getByText('只有家长可以查看卡牌目录。')).toBeVisible();
  await expect(page.locator('.pokemon-catalog-card')).toHaveCount(0);
});
