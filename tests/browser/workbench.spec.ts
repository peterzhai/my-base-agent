import {test,expect} from '@playwright/test';

test('管理工作台、RAG 引用与数据问答',async({page})=>{
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/');
  await page.getByLabel('管理员密码').fill('development-admin-password');
  await page.getByRole('button',{name:'进入工作台'}).click();
  await expect(page.getByRole('heading',{name:/让知识与数据/})).toBeVisible();
  await page.screenshot({path:'test-results/workbench.png',fullPage:true});
  await page.getByRole('button',{name:'问答调试',exact:true}).click();
  await page.getByRole('button',{name:'MES 如何报工？'}).click();
  await expect(page.locator('.fa-chat-assistant .fa-chat-content')).toContainText('工单报工');
  const citation=page.locator('.fa-chat-citations button').first();await expect(citation).toBeVisible();await citation.click();
  await expect(page.getByRole('button',{name:'下载原文'})).toBeVisible();
  await page.getByRole('button',{name:'Close',exact:true}).click();
  await page.getByRole('button',{name:'新会话',exact:true}).click();
  await page.getByLabel('输入问题').fill('今天产量是多少？');
  await page.getByRole('button',{name:'发送 ↑'}).click();
  await expect(page.locator('.fa-chat-table')).toContainText('200');
  await expect(page.locator('.fa-chat-table')).not.toContainText('999');
  await page.screenshot({path:'test-results/chat.png',fullPage:true});
  await page.getByRole('button',{name:'业务主题',exact:true}).click();
  await expect(page.getByRole('table')).toContainText('生产订单');
  await page.getByRole('button',{name:'编辑',exact:true}).first().click();
  await expect(page.getByLabel('部门权限字段键')).toHaveValue('department');
  expect(errors).toEqual([]);
});

test('宿主嵌入组件与账号切换隔离',async({page})=>{
  await page.goto('/demo');
  await page.getByRole('button',{name:'打开智能助手'}).click();
  await page.getByRole('button',{name:'今天产量是多少？'}).click();
  await expect(page.locator('.fa-chat-table')).toContainText('200');
  await page.getByLabel('切换示例账号').first().click();
  await page.getByText('二车间员工',{exact:true}).click();
  await expect(page.locator('.fa-chat-floating-wrap')).toHaveCount(0);
  await page.getByRole('button',{name:'打开智能助手'}).click();
  await expect(page.locator('.fa-chat-assistant')).toHaveCount(0);
  await page.getByRole('button',{name:'今天产量是多少？'}).click();
  await expect(page.locator('.fa-chat-table')).toContainText('999');
  await expect(page.locator('.fa-chat-table')).not.toContainText('200');
});

test('窄屏聊天窗口可操作',async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.goto('/demo');
  await page.getByRole('button',{name:'打开智能助手'}).click();
  const bounds=await page.locator('.fa-chat-floating-wrap').boundingBox();
  expect(bounds!.width).toBeLessThanOrEqual(390);
  await page.getByLabel('输入问题').fill('MES 如何报工？');
  await page.getByRole('button',{name:'发送 ↑'}).click();
  await expect(page.locator('.fa-chat-assistant')).toContainText('工单报工');
  await page.screenshot({path:'test-results/mobile-chat.png'});
});
