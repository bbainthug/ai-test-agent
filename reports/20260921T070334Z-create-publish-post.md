# Run 20260921T070334Z-create-publish-post

- 用例: `create-publish-post` 控制台新建文章并发布，前台首页可见（优先级 P0）
- 时间: 2026-09-21T07:03:34+00:00 -> 2026-09-21T07:03:38+00:00（UTC）
- 靶子: halo registry.fit2cloud.com/halo/halo:2.20 @ http://localhost:8090
- 步骤: 14 passed / 0 failed / 0 skipped
- 裁判: **pass** — 步骤12成功等待到「发布成功」提示证明控制台发布成功，步骤14断言通过且快照L32/L41显示前台首页出现该标题且文章处于已发布状态，无任何步骤失败或跳过。
- LLM 成本: 3307 tokens / 13227 ms（1 次调用, 失败 0）

## 步骤

| # | 动作 | 参数 | 状态 | 失败分类 | 耗时ms |
|---|------|------|------|----------|--------|
| 1 | goto | `{"url": "{{BASE_URL}}/login"}` | passed | - | 131 |
| 2 | fill | `{"selector": "role=textbox[name=\"用户名\"]", "value": "{{ADMIN_USER}}"}` | passed | - | 9 |
| 3 | fill | `{"selector": "role=textbox[name=\"密码\"]", "value": "{{ADMIN_PASSWORD}}"}` | passed | - | 16 |
| 4 | click | `{"selector": "role=button[name=\"登录\"]"}` | passed | - | 139 |
| 5 | wait_for | `{"text": "Administrator"}` | passed | - | 104 |
| 6 | goto | `{"url": "{{BASE_URL}}/console/posts/editor"}` | passed | - | 224 |
| 7 | fill | `{"selector": "role=textbox[name=\"请输入标题\"]", "value": "AI 测试 Agent 冒烟文章 001"}` | passed | - | 181 |
| 8 | fill | `{"selector": "[contenteditable=\"true\"]", "value": "这是 ai-test-agent 自动创建的冒烟测试文章。"}` | passed | - | 5 |
| 9 | click | `{"selector": "role=button[name=\"发布\"]"}` | passed | - | 110 |
| 10 | wait_for | `{"text": "文章设置"}` | passed | - | 3 |
| 11 | click | `{"selector": "role=dialog >> role=button[name=\"发布\"]"}` | passed | - | 270 |
| 12 | wait_for | `{"text": "发布成功"}` | passed | - | 301 |
| 13 | goto | `{"url": "{{BASE_URL}}/"}` | passed | - | 188 |
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
L51: - text: 发布于 2026-09-21
L52: - heading "AI 测试 Agent 冒烟文章 001" [level=1]:
L53:   - link "AI 测试 Agent 冒烟文章 001":
L54:     - /url: /archives/ai-ce-shi-agent-mou-yan-wen-zhang-001
L55: - paragraph: 这是 ai-test-agent 自动创建的冒烟测试文章。
L56: - link "Administrator":
L57:   - /url: /authors/admin
L58:   - img "Administrator"
L59: - link "Administrator":
L60:   - /url: /authors/admin
```

## 裁判证据

- L41: `- text: 发布于 2026-09-21`（expected_index=0）
- L32: `- heading "AI 测试 Agent 冒烟文章 001" [level=1]:`（expected_index=1）
