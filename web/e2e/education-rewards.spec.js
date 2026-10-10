import { readFileSync } from 'node:fs';
import { Buffer } from 'node:buffer';
import { test, expect, mockAPI, resetMockServer } from './fixtures.js';

const parent = { user_id: 'parent', name: '家长', role: 'parent', household_id: 'family', onboarding_completed: true, has_api_key: true };
const student = { ...parent, user_id: 'student', name: '小明', role: 'student' };
const probabilities = { basic: .85, rare: .15, featured: 0, premium: 0, legendary: 0 };
const settings = { prices: { daily: 5, featured: 15, rare: 30 }, probabilities: { daily: probabilities, featured: probabilities, rare: probabilities }, effective_probabilities: { daily: probabilities, featured: probabilities, rare: probabilities }, pack_names: { daily: '日常包', featured: '精选包', rare: '稀有包' }, level_names: { basic: '基础', rare: '稀有', featured: '精选', premium: '高级', legendary: '传说' }, updated_at: null };
const card = { card_id: 'card', source_card_id: 'me55-001', set_code: 'me55', series_name: '30周年庆典', name: '皮卡丘', category: '宝可梦', element: '雷', hp: 60, stage: '基础', card_number: '001', rarity: '普通', illustrator: 'Artist', notes: '', image_width: 640, image_height: 880, quantity: 1, reward_level: 'basic' };
const pack = { pack_id: 'pack', source: 'daily', pack_type: 'daily', reward_date: '2026-10-11', price: null, streak_node: null, probabilities, policy_version: 'v1', card_id: null, reward_level: null, owned_before: null, returned_points: 0, effective_probabilities: null, created_at: '2026-10-11T00:00:00Z', opened_at: null };
const png = process.env.POKEMON_CARD_FIXTURE_PATH ? readFileSync(process.env.POKEMON_CARD_FIXTURE_PATH) : Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jN3sAAAAASUVORK5CYII=', 'base64');

async function setup(page, role = 'student', seedCards = 0) {
  await resetMockServer(); await page.clock.setFixedTime(new Date('2026-10-11T06:00:00Z'));
  await page.addInitScript(() => Object.defineProperty(window.crypto, 'randomUUID', { value: undefined }));
  const state = { completed: false, opened: false, balance: 40, purchase: null, purchases: [], failFirst: false, prices: { ...settings.prices } };
  const task = () => ({ task_id: 'task', household_id: 'family', assigned_student_id: 'student', occurrence_date: '2026-10-11', due_at: '2026-10-11T10:00:00Z', title: '完成今日阅读', description: '', subject_code: 'chinese', status: state.completed ? 'completed' : 'open' });
  const summary = () => ({ student_id: 'student', balance: state.balance, homework_points: state.completed ? 41 : 40, streak: state.completed ? 3 : 2, next_streak_node: state.completed ? 5 : 3, unopened_count: (state.completed && !state.opened ? 1 : 0) + (state.purchase ? 1 : 0), today_rewarded: state.completed, settled_through: '2026-10-10' });
  await mockAPI(page, {
    'GET /auth/me': role === 'parent' ? parent : student, 'GET /auth/members': [parent, student], 'GET /auth/children': [],
    'GET /education/dictionaries': { timezone: 'Asia/Tokyo', subjects: [{ code: 'chinese', name: '语文', sort_order: 1, color: '#D95D39', homework_types: [] }], grade_levels: [], practice_sources: [] },
    'GET /education/learning': [], 'GET /education/calendar/events': { household_id: 'family', timezone: 'Asia/Tokyo', events: [] },
    'GET /education/calendar/sources': [],
    'GET /education/tasks/calendar': route => route.fulfill({ json: { days: [{ date: '2026-10-11', tasks: [task()], task_count: 1, completed_count: state.completed ? 1 : 0, overdue_count: 0 }], stats: { today_count: 1, week_count: 1, completed_count: state.completed ? 1 : 0, overdue_count: 0, total_points: state.completed ? 41 : 40 } } }),
    'POST /education/tasks/task/check-in': route => { state.completed = true; state.balance = 41; return route.fulfill({ status: 201, json: { submission_id: 'submission', task_id: 'task', sequence: 1, submission_text: '', reward_status: 'ready', reward_summary: summary() } }); },
    'POST /education/rewards/sync': route => route.fulfill({ json: summary() }),
    'GET /education/rewards/settings': route => route.fulfill({ json: { ...settings, prices: state.prices } }),
    'PUT /education/rewards/settings': route => { state.prices = route.request().postDataJSON(); return route.fulfill({ json: { ...settings, prices: state.prices } }); },
    'GET /education/rewards/packs': route => route.fulfill({ json: { items: [...(state.completed && !state.opened ? [pack] : []), ...(state.purchase ? [state.purchase] : [])], total: summary().unopened_count, page: 1, page_size: 20 } }),
    'POST /education/rewards/packs/pack/open': route => { state.opened = true; return route.fulfill({ json: { ...pack, card_id: card.card_id, card, opened_at: '2026-10-11T06:00:00Z', owned_before: 0, reward_level: 'basic', effective_probabilities: probabilities } }); },
    'GET /education/rewards/collection': route => {
      const params = new URL(route.request().url()).searchParams; const items = [...Array.from({ length: seedCards }, (_, i) => ({ ...card, card_id: `seed-${i}`, name: `卡牌 ${i + 1}`, card_number: String(i + 1) })), ...(state.opened ? [card] : [])];
      const page = Number(params.get('page') ?? 1);
      return route.fulfill({ json: { items: items.slice((page - 1) * 20, page * 20), total: items.length, page, page_size: 20, series: [{ set_code: 'me55', series_name: '30周年庆典' }] } });
    },
    'GET /education/rewards/cards/*/image': route => route.fulfill({ contentType: 'image/png', body: png }),
    'GET /education/rewards/transactions': { items: [], total: 0, page: 1, page_size: 20 },
    'POST /education/rewards/purchases': route => {
      const input = route.request().postDataJSON(); state.purchases.push(input);
      if (!state.purchase) { state.balance -= input.expected_price; state.purchase = { ...pack, pack_id: 'purchase', source: 'purchase', price: input.expected_price, pack_type: input.pack_type }; }
      if (state.failFirst) { state.failFirst = false; return route.abort('failed'); }
      return route.fulfill({ json: state.purchase });
    },
  });
  return state;
}

for (const theme of ['light', 'nasa']) for (const [width, columns] of [[375, 2], [1280, 4], [1600, 5]]) {
  test(`${theme} ${width}px homework to reward and collection`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 }); await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    const state = await setup(page, 'student', 21);
    await page.goto('/education'); await page.getByRole('button', { name: '完成打卡', exact: true }).click(); await page.getByRole('button', { name: '确认打卡' }).click();
    await expect(page.getByRole('status').filter({ hasText: '今日补给包已到账' })).toBeVisible();
    await page.getByRole('link', { name: /学习奖励/ }).first().click(); await expect(page.getByRole('heading', { name: '学习补给站' })).toBeVisible();
    await page.getByRole('button', { name: '打开卡包' }).click();
    const dialog = page.getByRole('dialog'); await expect(dialog.getByRole('heading', { name: '新卡加入收藏' })).toBeVisible();
    await expect.poll(() => dialog.locator('img').evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`reward-reveal-${theme}-${width}.png`), animations: 'disabled' });
    await page.getByRole('button', { name: '收下卡牌' }).click(); await page.getByRole('button', { name: '我的卡牌', exact: true }).click();
    const grid = page.getByLabel('收藏卡牌'); await expect(grid.locator('article')).toHaveCount(20); expect(await grid.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length)).toBe(columns);
    expect(await page.locator('.rewards-page').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`reward-collection-${theme}-${width}.png`), animations: 'disabled' });
    await page.getByRole('button', { name: '下一页' }).click(); await expect(page.getByRole('button', { name: '查看皮卡丘 · 001' })).toBeVisible();
    await page.getByRole('button', { name: '积分兑换', exact: true }).click(); await page.getByRole('button', { name: '兑换日常包' }).click();
    await page.getByRole('button', { name: '确认兑换' }).click(); await expect(page.getByRole('dialog')).toHaveCount(0); expect(state.purchases).toHaveLength(1); expect(state.balance).toBe(36);
    await page.screenshot({ path: testInfo.outputPath(`reward-packs-${theme}-${width}.png`), animations: 'disabled' });
  });
}

test('reload recovers an uncertain purchase without a second charge', async ({ page }) => {
  const state = await setup(page); state.failFirst = true; state.completed = true;
  await page.goto('/education/rewards'); await page.getByRole('button', { name: '积分兑换' }).click(); await page.getByRole('button', { name: '兑换日常包' }).click(); await page.getByRole('button', { name: '确认兑换' }).click();
  await expect(page.getByRole('button', { name: '重试原兑换' })).toBeVisible();
  await page.reload(); await page.getByRole('button', { name: '重试原兑换' }).click(); await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(state.purchases).toHaveLength(2); expect(state.purchases[0]).toEqual(state.purchases[1]); expect(state.balance).toBe(35);
});

test('parent configures household prices and views child rewards', async ({ page }) => {
  const state = await setup(page, 'parent'); state.completed = true;
  await page.goto('/settings?tab=family'); await page.getByRole('link', { name: '奖励设置' }).click();
  await page.getByLabel('日常包价格').fill('7'); await page.getByRole('button', { name: '保存设置' }).click(); await expect(page.getByText('已保存家庭卡包价格。')).toBeVisible(); expect(state.prices.daily).toBe(7);
  await page.goto('/education/rewards'); await expect(page.getByText('日常包', { exact: true })).toBeVisible(); await expect(page.getByRole('button', { name: '打开卡包' })).toHaveCount(0);
  await page.getByRole('button', { name: '积分兑换' }).click(); await expect(page.getByRole('button', { name: /兑换日常包/ })).toHaveCount(0);
});
