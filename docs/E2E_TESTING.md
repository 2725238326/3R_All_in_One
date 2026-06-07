# E2E 测试指南

## 安装依赖

```bash
# 安装 Playwright
npm install -D @playwright/test @types/node

# 安装浏览器
npx playwright install
```

## 运行测试

### 运行所有测试

```bash
npx playwright test
```

### 运行特定测试文件

```bash
npx playwright test e2e/app.spec.ts
```

### 运行特定测试

```bash
npx playwright test -g "应用首页加载"
```

### 调试模式

```bash
npx playwright test --debug
```

### 显示浏览器

```bash
npx playwright test --headed
```

## 测试覆盖

当前测试覆盖以下功能：

- 应用首页加载
- 任务列表显示
- 工作区切换
- 系统状态检查
- 模型选择
- API 健康检查
- 模型目录 API
- 任务列表 API

## 添加新测试

在 `e2e/` 目录下创建新的测试文件：

```typescript
import { test, expect } from '@playwright/test';

test.describe('新功能测试', () => {
  test('测试用例名称', async ({ page }) => {
    await page.goto('/');
    // 测试逻辑
  });
});
```

## 查看测试报告

```bash
npx playwright show-report
```

## CI/CD 集成

在 CI 环境中运行测试：

```yaml
- name: Install dependencies
  run: npm ci

- name: Install Playwright
  run: npx playwright install --with-deps

- name: Run E2E tests
  run: npx playwright test

- name: Upload test results
  if: always()
  uses: actions/upload-artifact@v3
  with:
    name: playwright-report
    path: playwright-report/
```
