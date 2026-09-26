# Run 20260926T060324Z-site-title-update-and-frontend-display

- 用例: `site-title-update-and-frontend-display` 修改站点标题并保存后前台首页显示新标题（优先级 P1）
- 时间: 2026-09-26T06:03:24+00:00 -> 2026-09-26T06:03:37+00:00（UTC）
- 靶子: halo registry.fit2cloud.com/halo/halo:2.20 @ http://localhost:8090
- 步骤: 10 passed / 1 failed / 1 skipped
- 失败分类: {"timeout": 1}
- 裁判: **fail** — 前台首页快照中站点标题仍为旧值 '测试站点-3969d8e9'，等待新标题 '测试站点-5211fced' 超时失败且后续断言被跳过，预期2被明确证伪。
- LLM 成本: 0 tokens / 0 ms（0 次调用, 失败 0）

## 步骤

| # | 动作 | 参数 | 状态 | 失败分类 | 耗时ms |
|---|------|------|------|----------|--------|
| 1 | goto | `{"url": "http://localhost:8090/login"}` | passed | - | 269 |
| 2 | fill | `{"selector": "label=用户名", "value": "{{ADMIN_USER}}"}` | passed | - | 12 |
| 3 | fill | `{"selector": "label=密码", "value": "{{ADMIN_PASSWORD}}"}` | passed | - | 40 |
| 4 | click | `{"selector": "role=button[name=\"登录\"]"}` | passed | - | 431 |
| 5 | assert_url | `{"url": "/uc/profile"}` | passed | - | 200 |
| 6 | goto | `{"url": "http://localhost:8090/console/settings"}` | passed | - | 311 |
| 7 | wait_for | `{"selector": "role=textbox[name=\"站点标题 *\"]"}` | passed | - | 296 |
| 8 | fill | `{"selector": "role=textbox[name=\"站点标题 *\"]", "value": "测试站点-{{RUN_ID}}"}` | passed | - | 4 |
| 9 | click | `{"selector": "role=button[name=\"保存\"]"}` | passed | - | 31 |
| 10 | goto | `{"url": "http://localhost:8090/"}` | passed | - | 228 |
| 11 | wait_for | `{"text": "测试站点-{{RUN_ID}}"}` | failed | timeout | 8010 |
| 12 | assert_text | `{"text": "测试站点-{{RUN_ID}}"}` | skipped | - | 0 |

## 最终快照（节选，前 60 行）

```
L1: - banner:
L2:   - link "测试站点-3969d8e9":
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
L24: - text: 测试站点-3969d8e9
L25: - list:
L26:   - listitem:
L27:     - link "全部":
L28:       - /url: /
L29:   - listitem:
L30:     - link "默认分类":
L31:       - /url: /categories/default
L32:   - listitem:
L33:     - link "基准分类 728c5519":
L34:       - /url: /categories/bench-cat-728c5519
L35:   - listitem:
L36:     - link "基准分类 74f5e64e":
L37:       - /url: /categories/bench-cat-74f5e64e
L38:   - listitem:
L39:     - link "测试分类-995b1c74":
L40:       - /url: /categories/ce-shi-fen-lei-995b1c74
L41:   - listitem:
L42:     - link "测试分类-4d02e0b3":
L43:       - /url: /categories/ce-shi-fen-lei-4d02e0b3
L44:   - listitem:
L45:     - link "测试分类-aab01628":
L46:       - /url: /categories/ce-shi-fen-lei-aab01628
L47:   - listitem:
L48:     - link "测试分类-5fa1ae98":
L49:       - /url: /categories/test-category-5fa1ae98
L50:   - listitem:
L51:     - link "测试分类-7641d3c9":
L52:       - /url: /categories/test-category-7641d3c9
L53:   - listitem:
L54:     - link "测试分类-e39c51c4":
L55:       - /url: /categories/ce-shi-fen-lei-e39c51c4
L56:   - listitem:
L57:     - link "测试分类-25134dc0":
L58:       - /url: /categories/test-category-25134dc0
L59:   - listitem:
L60:     - link "测试分类-c8cdc1fd":
```

## 裁判证据

- L2: `- link "测试站点-3969d8e9":`（expected_index=2）
- L24: `- text: 测试站点-3969d8e9`（expected_index=2）
- L292: `- link "测试站点-3969d8e9":`（expected_index=2）
