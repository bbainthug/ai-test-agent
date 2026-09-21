# Run 20260921T065447Z-view-user-list-admin-role

- 用例: `view-user-list-admin-role` 管理员登录后在用户管理页查看用户列表，可见 admin 账号及其角色（优先级 P0）
- 时间: 2026-09-21T06:54:47+00:00 -> 2026-09-21T06:54:57+00:00（UTC）
- 靶子: halo registry.fit2cloud.com/halo/halo:2.20 @ http://localhost:8090
- 步骤: 4 passed / 1 failed / 6 skipped
- 失败分类: {"timeout": 1}
- 裁判: **unsure** — 步骤5等待'个人中心'超时失败，步骤6-11全部跳过，/uc/profile 与 /console/users 的 URL 断言及用户列表断言均未执行，快照仅显示个人中心式页面而非用户列表页，各预期既无法证实也无法证伪。
- LLM 成本: 2554 tokens / 27952 ms（1 次调用, 失败 0）

## 步骤

| # | 动作 | 参数 | 状态 | 失败分类 | 耗时ms |
|---|------|------|------|----------|--------|
| 1 | goto | `{"url": "http://localhost:8090/login"}` | passed | - | 217 |
| 2 | fill | `{"selector": "label=用户名", "value": "{{ADMIN_USER}}"}` | passed | - | 8 |
| 3 | fill | `{"selector": "label=密码", "value": "{{ADMIN_PASSWORD}}"}` | passed | - | 17 |
| 4 | click | `{"selector": "role=button[name=\"登录\"]"}` | passed | - | 151 |
| 5 | wait_for | `{"text": "个人中心"}` | failed | timeout | 8010 |
| 6 | assert_url | `{"url": "/uc/profile"}` | skipped | - | 0 |
| 7 | goto | `{"url": "http://localhost:8090/console/users"}` | skipped | - | 0 |
| 8 | wait_for | `{"text": "admin"}` | skipped | - | 0 |
| 9 | assert_url | `{"url": "/console/users"}` | skipped | - | 0 |
| 10 | assert_text | `{"text": "admin"}` | skipped | - | 0 |
| 11 | assert_text | `{"text": "超级管理员"}` | skipped | - | 0 |

## 最终快照（节选，前 60 行）

```
L1: - complementary:
L2:   - link "访问首页":
L3:     - /url: /
L4:     - img
L5:   - list:
L6:     - listitem:
L7:       - img
L8:       - text: 我的
L9:     - listitem:
L10:       - img
L11:       - text: 消息
L12:     - listitem: 内容
L13:     - listitem:
L14:       - img
L15:       - text: 文章
L16:   - text: Administrator
L17:   - img
L18:   - text: 超级管理员
L19:   - link:
L20:     - /url: /console
L21:     - img
L22:   - img
L23: - main:
L24:   - text: A
L25:   - img
L26:   - heading "Administrator" [level=1]
L27:   - text: "@admin"
L28:   - button "编辑"
L29:   - text: 详情 通知配置 个人令牌 两步验证 登录设备
L30:   - term: 显示名称
L31:   - definition: Administrator
L32:   - term: 用户名
L33:   - definition: admin
L34:   - term: 电子邮箱
L35:   - definition:
L36:     - text: agent-test@example.com
L37:     - img
L38:     - text: 验证电子邮箱 电子邮箱地址还未验证，点击下方按钮进行验证
L39:     - button "验证"
L40:   - term: 角色
L41:   - definition:
L42:     - img
L43:     - text: 超级管理员
L44:   - term: 描述
L45:   - definition: 无
L46:   - term: 注册时间
L47:   - definition: 2026-09-19 16:42
L48:   - text: Powered by
L49:   - link "Halo":
L50:     - /url: https://www.halo.run
```

## 裁判证据

- L26: `heading "Administrator" [level=1]`（expected_index=0）
- L29: `详情 通知配置 个人令牌 两步验证 登录设备`（expected_index=1）
- L33: `definition: admin`（expected_index=2）
- L43: `text: 超级管理员`（expected_index=3）
