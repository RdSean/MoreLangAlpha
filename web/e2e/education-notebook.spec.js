import { test, expect, mockAPI, resetMockServer } from './fixtures.js';

const parent = { user_id: 'parent-1', name: '家长', role: 'parent', household_id: 'household-1', onboarding_completed: true, has_api_key: true };
const student = { ...parent, user_id: 'student-1', name: '小林', role: 'student', grade_code: 'g4' };
const dictionaries = {
  timezone: 'Asia/Tokyo',
  subjects: ['chinese', 'math', 'english', 'science'].map((code, index) => ({ code, name: ['语文', '数学', '英语', '科学'][index], sort_order: index, color: '', homework_types: [] })),
  grade_levels: [], practice_sources: [],
};
const homework = {
  task_id: 'task-1', task_rule_id: 'rule-1', household_id: 'household-1', assigned_student_id: 'student-1',
  occurrence_date: '2026-10-11', due_at: '2026-10-11T10:00:00Z', title: '阅读课文并记录三个发现',
  description: '读一读第三章，用自己的话记录最感兴趣的内容。', subject_code: 'chinese', status: 'open',
};

for (const role of ['parent', 'student']) for (const width of [375, 1440]) {
  test(`${role} ${width}px calendar notebook, check-in points and submission record`, async ({ page }, testInfo) => {
    await resetMockServer();
    await page.setViewportSize({ width, height: 950 });
    // UTC October 10 is already October 11 in the household timezone.
    await page.clock.setFixedTime(new Date('2026-10-10T23:30:00Z'));
    await page.addInitScript(() => {
      window.__homeworkSounds = 0;
      const original = AudioContext.prototype.createOscillator;
      AudioContext.prototype.createOscillator = function () {
        const node = original.call(this);
        const start = node.start.bind(node);
        node.start = (...args) => { window.__homeworkSounds += 1; return start(...args); };
        return node;
      };
    });
    let completed = false;
    let feedback = '';
    const task = () => ({ ...homework, status: completed ? 'completed' : 'open', is_completed: completed, is_overdue: false });
    await mockAPI(page, {
      'GET /auth/me': role === 'parent' ? parent : student,
      'GET /auth/members': [parent, student],
      'GET /education/dictionaries': dictionaries,
      'GET /education/learning': [],
      'GET /education/tasks/calendar': async route => {
        const url = new URL(route.request().url());
        await route.fulfill({ json: {
          start_date: url.searchParams.get('start_date'), end_date: url.searchParams.get('end_date'),
          stats: { today_count: 1, week_count: 0, overdue_count: 0, completed_count: completed ? 1 : 0, total_points: completed ? 13 : 12 },
          days: [
            { date: '2026-10-11', task_count: 1, completed_count: completed ? 1 : 0, overdue_count: 0, tasks: [task()] },
            { date: '2026-10-12', task_count: 1, completed_count: 0, overdue_count: 0, tasks: [{ ...task(), task_id: 'task-2', title: '观察植物', subject_code: 'science', status: 'open' }] },
          ],
        } });
      },
      'GET /education/tasks/task-1': async route => route.fulfill({ json: { ...task(), parent_materials: [], submissions: completed ? [{
        submission_id: 'submission-1', task_id: 'task-1', sequence: 1, submission_text: '今天读完第三章。', assets: [],
        reviews: feedback ? [{ review_id: 'review-1', decision: 'feedback', feedback_text: feedback }] : [],
      }] : [] } }),
      'POST /education/tasks/task-1/check-in': async route => {
        completed = true;
        await route.fulfill({ status: 201, json: { submission_id: 'submission-1', task_id: 'task-1', sequence: 1, submission_text: '今天读完第三章。' } });
      },
      'POST /education/tasks/task-1/reviews': async route => {
        feedback = route.request().postDataJSON().feedback_text;
        await route.fulfill({ status: 201, json: { review_id: 'review-1', feedback_text: feedback } });
      },
    });
    await page.goto('/education', { waitUntil: 'domcontentloaded' });
    await expect(page.getByLabel('累计积分', { exact: true })).toContainText('12');
    await expect(page.getByRole('button', { name: /2026-10-11/ })).toHaveAttribute('aria-pressed', 'true');
    for (const subject of ['语文', '数学', '英语']) await expect(page.getByRole('heading', { name: subject, exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '科学', exact: true })).toHaveCount(0);
    await expect(page.getByText('今日未布置')).toHaveCount(2);
    await page.getByRole('button', { name: /2026-10-12/ }).click();
    await expect(page.getByRole('heading', { name: '科学', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: homework.title })).toHaveCount(0);
    await page.getByRole('button', { name: '今天', exact: true }).click();
    await page.getByRole('button', { name: '完成打卡', exact: true }).click();
    await page.getByPlaceholder('可选的完成说明').fill('今天读完第三章。');
    await page.getByRole('button', { name: '确认打卡', exact: true }).click();
    await expect(page.getByLabel('累计积分', { exact: true })).toContainText('13');
    await expect.poll(() => page.evaluate(() => window.__homeworkSounds)).toBe(1);
    if (role === 'parent') {
      await page.getByRole('button', { name: '反馈', exact: true }).click();
      await expect(page.getByText('今天读完第三章。')).toBeVisible();
      await page.getByPlaceholder('写下修改建议或完成反馈').fill('记录很具体，继续保持。');
      await page.getByRole('button', { name: '保存反馈' }).click();
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await expect(page.getByLabel('累计积分', { exact: true })).toContainText('13');
      expect(await page.evaluate(() => window.__homeworkSounds)).toBe(1);
    }
    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(page.getByLabel('累计积分', { exact: true })).toContainText('13');
    await expect(page.getByRole('button', { name: '完成打卡', exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => window.__homeworkSounds)).toBe(0);
    const notebook = page.getByTestId('education-page');
    expect(await notebook.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await notebook.evaluate(element => { element.scrollTop = 0; });
    await page.screenshot({ path: testInfo.outputPath(`education-${role}-${width}.png`), animations: 'disabled' });
  });
}
