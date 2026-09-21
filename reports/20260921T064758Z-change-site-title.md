# Run 20260921T064758Z-change-site-title

- 用例: `change-site-title` 控制台修改站点标题，前台生效（优先级 P1）
- 时间: 2026-09-21T06:47:58+00:00 -> 2026-09-21T06:48:02+00:00（UTC）
- 靶子: halo registry.fit2cloud.com/halo/halo:2.20 @ http://localhost:8090
- 步骤: 11 passed / 0 failed / 0 skipped
- 裁判: **pass** — 步骤9 wait_for「保存成功」通过证明控制台保存成功，步骤11 断言通过且快照多处显示新标题「Agent 测试站 001」，无失败或跳过步骤。
- LLM 成本: 3947 tokens / 36748 ms（1 次调用, 失败 0）

## 步骤

| # | 动作 | 参数 | 状态 | 失败分类 | 耗时ms |
|---|------|------|------|----------|--------|
| 1 | goto | `{"url": "{{BASE_URL}}/login"}` | passed | - | 196 |
| 2 | fill | `{"selector": "role=textbox[name=\"用户名\"]", "value": "{{ADMIN_USER}}"}` | passed | - | 9 |
| 3 | fill | `{"selector": "role=textbox[name=\"密码\"]", "value": "{{ADMIN_PASSWORD}}"}` | passed | - | 20 |
| 4 | click | `{"selector": "role=button[name=\"登录\"]"}` | passed | - | 354 |
| 5 | wait_for | `{"text": "Administrator"}` | passed | - | 178 |
| 6 | goto | `{"url": "{{BASE_URL}}/console/settings"}` | passed | - | 238 |
| 7 | fill | `{"selector": "role=textbox[name=\"站点标题\"]", "value": "Agent 测试站 001"}` | passed | - | 199 |
| 8 | click | `{"selector": "role=button[name=\"保存\"]"}` | passed | - | 30 |
| 9 | wait_for | `{"text": "保存成功"}` | passed | - | 6 |
| 10 | goto | `{"url": "{{BASE_URL}}/"}` | passed | - | 184 |
| 11 | assert_text | `{"text": "Agent 测试站 001"}` | passed | - | 2 |

## 最终快照（节选，前 60 行）

```
L1: - banner:
L2:   - link "Agent 测试站 001":
L3:     - /url: /
L4:   - list:
L5:     - listitem:
L6:       - link "首页":
L7:         - /url: /
L8:     - listitem:
L9:       - link "Hello Halo":
L10:         - /url: /archives/hello-halo
L11:     - listitem:
L12:       - link "Halo":
L13:         - /url: /tags/halo
L14:     - listitem:
L15:       - link "关于":
L16:         - /url: /about
L17:   - list:
L18:     - listitem
L19:     - listitem:
L20:       - link "搜索":
L21:         - /url: javascript:SearchWidget.open()
L22:     - listitem:
L23:       - img "Administrator"
L24: - text: Agent 测试站 001
L25: - list:
L26:   - listitem:
L27:     - link "全部":
L28:       - /url: /
L29:   - listitem:
L30:     - link "默认分类":
L31:       - /url: /categories/default
L32: - heading "AI 测试 Agent 冒烟文章 001" [level=1]:
L33:   - link "AI 测试 Agent 冒烟文章 001":
L34:     - /url: /archives/ai-ce-shi-agent-mou-yan-wen-zhang-001
L35: - paragraph: 这是 ai-test-agent 自动创建的冒烟测试文章。
L36: - link "Administrator":
L37:   - /url: /authors/admin
L38:   - img "Administrator"
L39: - link "Administrator":
L40:   - /url: /authors/admin
L41: - text: 发布于 2026-09-21
L42: - heading "AI 测试 Agent 冒烟文章 001" [level=1]:
L43:   - link "AI 测试 Agent 冒烟文章 001":
L44:     - /url: /archives/ai-ce-shi-agent-mou-yan-wen-zhang-001
L45: - paragraph: 这是 ai-test-agent 自动创建的冒烟测试文章。
L46: - link "Administrator":
L47:   - /url: /authors/admin
L48:   - img "Administrator"
L49: - link "Administrator":
L50:   - /url: /authors/admin
L51: - text: 发布于 2026-09-20
L52: - heading "AI 测试 Agent 冒烟文章 001" [level=1]:
L53:   - link "AI 测试 Agent 冒烟文章 001":
L54:     - /url: /archives/ai-ce-shi-agent-mou-yan-wen-zhang-001
L55: - paragraph: 冒烟正文。
L56: - link "Administrator":
L57:   - /url: /authors/admin
L58:   - img "Administrator"
L59: - link "Administrator":
L60:   - /url: /authors/admin
```

## 裁判证据

- L2: `- link "Agent 测试站 001":`（expected_index=0）
- L24: `- text: Agent 测试站 001`（expected_index=1）
- L116: `- link "Agent 测试站 001":`（expected_index=1）
