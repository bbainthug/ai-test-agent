# Run 20260921T064737Z-create-publish-post

- 用例: `create-publish-post` 控制台新建文章并发布，前台首页可见（优先级 P0）
- 时间: 2026-09-21T06:47:37+00:00 -> 2026-09-21T06:47:43+00:00（UTC）
- 靶子: halo registry.fit2cloud.com/halo/halo:2.20 @ http://localhost:8090
- 步骤: 14 passed / 0 failed / 0 skipped
- 裁判: **pass** — 步骤12成功等待到「发布成功」提示，且最终首页快照中出现该文章标题及发布日期，两条预期均有明确证据，无失败或跳过步骤。
- LLM 成本: 3099 tokens / 14299 ms（1 次调用, 失败 0）

## 步骤

| # | 动作 | 参数 | 状态 | 失败分类 | 耗时ms |
|---|------|------|------|----------|--------|
| 1 | goto | `{"url": "{{BASE_URL}}/login"}` | passed | - | 252 |
| 2 | fill | `{"selector": "role=textbox[name=\"用户名\"]", "value": "{{ADMIN_USER}}"}` | passed | - | 13 |
| 3 | fill | `{"selector": "role=textbox[name=\"密码\"]", "value": "{{ADMIN_PASSWORD}}"}` | passed | - | 24 |
| 4 | click | `{"selector": "role=button[name=\"登录\"]"}` | passed | - | 148 |
| 5 | wait_for | `{"text": "Administrator"}` | passed | - | 415 |
| 6 | goto | `{"url": "{{BASE_URL}}/console/posts/editor"}` | passed | - | 326 |
| 7 | fill | `{"selector": "role=textbox[name=\"请输入标题\"]", "value": "AI 测试 Agent 冒烟文章 001"}` | passed | - | 277 |
| 8 | fill | `{"selector": "[contenteditable=\"true\"]", "value": "这是 ai-test-agent 自动创建的冒烟测试文章。"}` | passed | - | 6 |
| 9 | click | `{"selector": "role=button[name=\"发布\"]"}` | passed | - | 121 |
| 10 | wait_for | `{"text": "文章设置"}` | passed | - | 5 |
| 11 | click | `{"selector": "role=dialog >> role=button[name=\"发布\"]"}` | passed | - | 943 |
| 12 | wait_for | `{"text": "发布成功"}` | passed | - | 181 |
| 13 | goto | `{"url": "{{BASE_URL}}/"}` | passed | - | 514 |
| 14 | assert_text | `{"text": "AI 测试 Agent 冒烟文章 001"}` | passed | - | 3 |

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

- L41: `- text: 发布于 2026-09-21`（expected_index=0）
- L32: `- heading "AI 测试 Agent 冒烟文章 001" [level=1]:`（expected_index=0）
- L33: `- link "AI 测试 Agent 冒烟文章 001":`（expected_index=1）
