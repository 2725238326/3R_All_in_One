import { test, expect } from '@playwright/test';

test.describe('MonST3R 应用 E2E 测试', () => {
  test('应用首页加载', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/3R All-in-One/);
  });

  test('任务列表显示', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.job-list-item, .empty-state');
    const jobList = page.locator('.job-list-item');
    const count = await jobList.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('工作区切换', async ({ page }) => {
    await page.goto('/');
    
    // 切换到创建工作区
    await page.click('button[workspace="create"]');
    await expect(page.locator('.create-workspace')).toBeVisible();
    
    // 切换到队列工作区
    await page.click('button[workspace="queue"]');
    await expect(page.locator('.queue-workspace')).toBeVisible();
  });

  test('系统状态检查', async ({ page }) => {
    await page.goto('/');
    
    // 检查系统状态卡片
    await expect(page.locator('.system-status')).toBeVisible();
  });

  test('模型选择', async ({ page }) => {
    await page.goto('/');
    await page.click('button[workspace="create"]');
    
    // 检查模型选择器
    const modelSelect = page.locator('select[name="model"]');
    await expect(modelSelect).toBeVisible();
    
    // 选择一个模型
    await modelSelect.selectOption('dust3r');
    await expect(modelSelect).toHaveValue('dust3r');
  });

  test('API 健康检查', async ({ request }) => {
    const response = await request.get('/api/status');
    expect(response.ok()).toBeTruthy();
    
    const data = await response.json();
    expect(data).toHaveProperty('status');
  });

  test('模型目录 API', async ({ request }) => {
    const response = await request.get('/api/models');
    expect(response.ok()).toBeTruthy();
    
    const data = await response.json();
    expect(Array.isArray(data.models)).toBeTruthy();
  });

  test('任务列表 API', async ({ request }) => {
    const response = await request.get('/api/jobs');
    expect(response.ok()).toBeTruthy();
    
    const data = await response.json();
    expect(Array.isArray(data.jobs)).toBeTruthy();
  });
});
