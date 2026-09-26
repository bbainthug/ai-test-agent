# ai-test-agent

用 LLM Agent 对真实开源系统 **Halo**（halo-dev/halo，开源建站系统）做端到端测试的闭环工具：

```
功能描述 ──planner(LLM)──> 结构化用例 JSON（受限动作集）
        ──executor(Playwright)──> 步骤日志/截图/文本快照（失败三分类）
        ──judge(LLM, 只看文本快照)──> pass / fail / unsure（三态）
        ──report──> reports/<run_id>.json + .md（含 LLM 成本审计）
```

> **先做再写**：本 README 中出现的每一个指标数字都来自 `reports/*.json`（Milestone A）或
> `bench/results/*/`（Milestone B），可按
> [复现](#复现) 一节在干净环境重新跑出。没跑出来的不写；失败运行也保留报告。
> 当前靶子实测版本：Halo **2.20.21**（镜像 `registry.fit2cloud.com/halo/halo:2.20`）。

## 不做什么

- 不做通用测试框架、不做多应用适配、不做 UI 界面；
- 不用截图做 OCR 或多模态裁判（成本与可复现性差）——裁判只看文本快照。

## Milestone 进度

| Milestone | 内容 | 状态 |
|-----------|------|------|
| A | 闭环跑通：3 条手写用例（登录 / 发文章 / 改站点标题）+ planner 冒烟，tag `v0.1` | **完成，待复核** |
| B | 指标（20 功能基准、覆盖率/误报率/漏报率/一致性/成本、5 轮复跑、消融） | **完成**；参考用例由 agent 起草并对真实 Halo 校验，**待人工复核** |
| B2 | grounded planner：先自动探索真实页面再生成用例，同一基准前后对比 | **完成** |
| C | 对外产出（真实缺陷 issue/PR、GIF、docs/design.md） | 未开始（issue 草稿已写，见 [B2 结果](#b2grounded-planner)） |

## Milestone A 结果（数字出处：reports/ 下对应 run_id 的 JSON）

### 全链路结果（LLM 裁判开启，模型 glm-5.3-flash @ 火山方舟）

| run_id | 用例 | 步骤（P/F/S） | 裁判 | 裁判 tokens | 裁判耗时 |
|--------|------|---------------|------|-------------|----------|
| `20260921T070315Z-login-admin` | 手写·登录并进入控制台（P0） | 9/0/0 | **pass** | 5,131 | 15.5s |
| `20260921T070334Z-create-publish-post` | 手写·新建文章并发布（P0） | 14/0/0 | **pass** | 3,307 | 13.2s |
| `20260921T070352Z-change-site-title` | 手写·改站点标题（P1） | 11/0/0 | **pass** | 4,420 | 36.9s |
| `20260921T070215Z-view-user-list` | **planner 生成**·查看用户列表（P1） | 10/0/0 | **pass** | 4,049 | 46.1s |

- 4 条用例步骤级全部通过，裁判全部 pass，无 unsure；
- 最终这 4 次裁判调用合计 **16,907 tokens / 111.7s**；每次执行的裁判理由与快照行号证据见对应 `.md`。

### planner 冒烟（从一句话功能描述生成用例）——保留的三次迭代

planner 并非一次就写对，三次运行全部保留在 `reports/`（这正是三态裁判的价值）：

| run_id | 发生了什么 | 裁判 |
|--------|-----------|------|
| `20260921T065447Z-view-user-list-admin-role` | 生成的用例 `wait_for "个人中心"`，但该页面并无此文本（幻觉文案）→ 步骤超时，后续跳过 | **unsure** |
| `20260921T065715Z-view-user-list` | 把系统事实补进提示词后重生成；暴露 `assert_url` 竞态（登录跳转未完成就读 URL）→ 执行器缺陷被裁判判出 | **fail** |
| `20260921T070215Z-view-user-list` | 修复执行器 URL 断言竞态（改为轮询等待）+ 提示词加"稳定性红线"后 | **pass** |

### 本次开发中发现并修复的两个执行器问题（会被真实运行暴露，正是闭环的意义）

1. **URL 断言竞态**：`assert_url` 原来立即读 `page.url`，登录跳转未完成即失败 → 改为轮询等待至超时；
2. **升级提示横幅 flaky**：Halo 控制台"新版本可用"横幅由浏览器外联 `release-checker.halo.run` 决定是否出现，
   其浮层会盖住"发布"按钮 → 执行器按 `BLOCK_EXTERNAL_HOSTS` 屏蔽外联（可配置关闭，见 `.env.example`）。

## Milestone B 结果：20 功能 × 5 轮基准

数字出处：[`bench/results/20260925-full/summary.md`](bench/results/20260925-full/summary.md)
（逐次运行记录 `runs.jsonl`，可用 `bench.metrics` 重算）。模型 glm-5.3-flash，Halo 2.20.21，2026-09-25。

### 方法

- **20 个功能**（[`bench/features.json`](bench/features.json)）：每个功能一句话描述 + 一个**故障注入点**
  （Playwright 拦截该功能的关键接口并返回 500）+ 一条**参考用例**；
- **参考用例校验**（[`bench/reference_validation.json`](bench/reference_validation.json)）：20/20 条在健康系统上
  全部通过、注入故障后断言失败——证明每个故障在 UI 上**可以**被检出，漏报不是"故障本身不可见"造成的；
- **排除 3 个功能**：评论列表、附件列表、仪表盘统计——接口 500 时页面与"没有数据"的空状态完全一样，
  从 UI 无法区分（这本身是一个可以向 Halo 反馈的可观测性问题，列入 Milestone C 候选）；
- **每轮**：planner 从一句话描述生成用例 → 在健康系统上执行 → 三种裁判各给结论；第 1 轮另在注入故障后再执行一次；
- **覆盖**：执行过程中确实请求到了该功能的关键接口（网络探针命中）才算覆盖——用例"跑完了"不等于"测到了"；
- **三种裁判（消融）**：
  - `informed`：LLM 看用例、步骤结果与最终页面快照（默认配置）；
  - `blind`：LLM 只看功能预期与最终页面快照，不看步骤结果；
  - `assert_only`：不用 LLM，所有步骤通过即 pass；
- **口径**：误报率 = 健康系统、已覆盖运行中结论非 pass 的比例；漏报率 = 故障确实被触发的运行中结论仍为 pass 的比例；
  一致率 = 5 轮都产出用例的功能中，5 轮结论完全相同的比例；
- 每次执行用独立 `RUN_ID` 命名创建的数据，避免多轮之间互相污染；Halo 登录限流 3 次/分钟，
  基准按 21 秒间隔登录（不改被测系统配置）。

### 结果

- 100 次运行，planner 产出合法用例 **97%**（3 次生成失败）；
- 覆盖：15/20 个功能至少一轮被覆盖，**按运行计 53%**——近一半用例在走到目标接口之前就失败了；

| 裁判 | 误报率（健康·已覆盖，n=53） | 其中 fail / unsure | 漏报率（故障已触发，n=10） | 5 轮一致率（n=18） |
|---|---|---|---|---|
| LLM `informed` | 47.2% | 18 / 7 | **0%** | 44.4% |
| LLM `blind` | 77.4% | 9 / 32 | 10% | 38.9% |
| 纯断言 `assert_only` | **37.7%** | 20 / 0 | 30% | 55.6% |

成本：100 次运行共 **1,431,297 tokens**（平均 14.3k/次）；planner 108 次调用（平均 91.9 s/次），
裁判 237 次（平均 48.3 s/次）；总墙钟 **60 分钟**（规划与裁判并发、执行串行）。14 次 LLM 调用失败：6 次是上面 3 次 planner 生成失败（各 2 次尝试均失败），其余 8 次重试后恢复；裁判结论无一因调用失败缺失。

### 读数

1. **主要误差来源是 planner，不是裁判**。未覆盖的 44 次运行里，25 次是选择器定位失败、9 次超时、
   6 次断言了页面上不存在的文案；5 个功能 5 轮都没覆盖到（发布文章、页面列表、文章详情、归档页、角色列表），
   典型原因是编造了不存在的路由（如把角色管理写成会 404 的 `/console/roles`）。
   对照：同样 20 个功能的参考用例是 20/20 有效。
2. **LLM 裁判的价值在漏报**：故障已触发的 10 次里，纯断言漏了 3 次（标签列表、插件列表、用户列表——
   生成的断言只检查了页面框架文案，接口 500 时照样通过），`informed` 裁判 0 漏报，它从快照里读出了
   "列表为空 / 错误提示"。代价是误报比纯断言高约 10 个百分点。
3. **`informed` 判 fail 而断言全过的 3 次都是"用例预期写错"被抓出来**：例如 planner 点击 `name=保存`
   子串匹配到"保存并继续添加"，对话框没关，与它自己写的预期矛盾；插件页出现"网络错误"提示
   （执行器屏蔽了外联域名所致，见已知限制），裁判给 unsure 而不是 pass。
4. **盲裁判不可单独使用**：不给步骤结果时 32/53 次给 unsure，误报率 77%。
5. **一致性低**：18 个功能里只有 8 个 5 轮结论完全相同——每轮 planner 生成的用例不同，
   不稳定主要来自用例本身而非裁判。

### 结论与下一步

在这个设置下，"LLM 生成用例 + LLM 裁判"能以 0/10 的漏报检出注入的接口故障，但健康系统上近一半结论
不可直接采信，且主要是用例生成质量问题。最值得做的改进是让 planner 基于真实页面（路由表、可访问性树）
生成选择器，而不是凭描述猜——这是 Milestone C 之前的优先项。

> 参考用例与功能描述由 agent 起草并逐条在真实 Halo 上校验过（见 `reference_validation.json`），
> 但尚未经人工逐条复核；复核前，"参考用例 20/20 有效"应视为自动校验结论。

## B2：grounded planner

数字出处：[`bench/results/20260926-grounded/`](bench/results/20260926-grounded/)
（`runs.jsonl` 逐次记录、`comparison.md` 为 `bench.compare` 的原样输出）；基线不变，仍是
[`bench/results/20260925-full/`](bench/results/20260925-full/)。同一模型（glm-5.3-flash）、
同一 Halo 版本（2.20.21）、同样 20 功能 × 5 轮；`bench/features.json` / `bench/metrics.py` /
执行器 / 裁判均未改动（公平性红线）。

### 做了什么

Milestone B 的结论是：主要误差来源是 planner 凭一句话描述硬猜页面和选择器，不是执行器或裁判。
这次给 planner 加了"先看页面再写用例"的两步流程：

1. **`agent/explorer.py`（新）**：登录一次（`storage_state` 复用，不重复登录——Halo 限流
   3 次/分钟），自动探索控制台侧边栏 + 前台导航，缓存成 `site_map.json`；给定目标 URL 能再拍一次
   该页面的文本可访问性树快照；支持点击"树里存在的非提交类按钮"做一层展开（新建对话框一类）。
   全程只读，不装故障、不计入覆盖率。
   - 站点地图的自动发现踩了一个坑：Halo 2.20 控制台侧边栏是 `<li class="menu-item">` +
     Vue Router 客户端路由渲染的，**没有真实 `<a href>`**，`aria_snapshot()` 里这些条目也只是
     `listitem` 角色、不带 `/url:`——任务书原计划的两条路径（aria、DOM `href`）在真实控制台页面
     上都拿不到路由。加了第三条：点击侧边栏菜单项、读跳转后的 `page.url`，仍是自动发现（不读
     任何写死的路由表）、仍只读（路由跳转是 GET）。
2. **`agent/planner.py`**：`plan_case(..., mode="baseline"|"grounded")`，默认 `grounded`。
   两步生成——① 功能描述 + 站点地图 → LLM 选目标页面 URL（+ 是否需要展开某按钮）；
   ② 功能描述 + 目标页面快照 → LLM 写用例。写完后做**静态选择器校验**（纯函数，不跑浏览器）：
   用例里每个 `role=`/`label=`/`text=` 选择器必须能在目标页面快照里找到匹配（`role` 的 `name`
   精确匹配，"保存" 不会算命中"保存并继续添加"），不匹配就把具体问题回传 LLM 修一次，仍不过
   则照常交给执行器但在 `grounding.violations` 里如实记录。
   探索或选页失败（登录失败、页面打不开、LLM 一直选不出站点地图内的 URL）时降级 `baseline`，
   记录 `grounding.status="fallback"` 和原因，不静默。
   - baseline 的"系统事实"提示词里保留了页面具体事实（编辑器地址、站点设置控件等）；
     grounded 模式把这些**页面具体**事实去掉了（见 `GROUND_COMMON_FACTS`），只留通用规则
     （登录跳转、`{{RUN_ID}}`、凭据占位符），页面具体信息全部来自探索到的真实快照——这是任务书
     "已知取舍"里明确允许保留旧提示词、但要在这里说明的部分。
3. **`bench/run_bench.py`**：加 `--planner baseline|grounded`（默认 `grounded`），写入
   `meta.json`；主线程建**一个** `Explorer` 给全部规划线程共用（`site_map()` 内部加锁，
   保证一次运行只探索一次；见下面"发现的两个问题"）；每条记录加 `grounding` 字段
   （`status`/`page_url`/`expand_click`/`violations`/`explore_seconds`）。
4. **`bench/compare.py`（新）**：两次结果并排对比（覆盖、三种裁判的误报/漏报/一致率、成本），
   写 `comparison.md`。

### 接手时发现并修的两个阻塞问题

接手时上一位 agent 的实现已经完成大半但没提交，集成测试跑不过：

1. **同线程嵌套 `sync_playwright()`**：`Explorer.site_map()`/`page_snapshot()`/
   `expanded_snapshot()` 都在自己的 `with sync_playwright()` 里调 `_new_context()`，
   `_new_context()` 又调 `_login_and_save()`，后者自己再开一个 `with sync_playwright()`——
   同一线程内嵌套第二个 sync API 上下文必报错。改成登录必须在调用方自己的 `with` **之外**先做
   完，`_new_context()` 不再兜底登录。
2. **并发安全**：`run_bench` 的 6 个规划线程共用探索结果，但原实现是每线程一份 `Explorer`
   （`threading.local`），仍会在共享的缓存目录上竞争写 `site_map.json`。改成真的共用一个
   `Explorer` 实例，`site_map()` 加锁 + 双检，保证一次运行只探索一次；补了单元测试
   （fake 替换真实探索，8 线程并发只应触发 2 次探索调用），验证过去掉锁会失败（10 次而非 2 次）。

修完后 `HALO_UP=1 uv run pytest tests/test_explorer_halo_integration.py -q` 两条集成测试通过；
`uv run pytest -q` 全绿（73 个测试，71 通过 + 2 个 halo 集成测试默认跳过）；`ruff check .` 干净。

### 对比表

（[`bench/results/20260926-grounded/comparison.md`](bench/results/20260926-grounded/comparison.md)
的原样输出）

# 基准对比：20260925-full → 20260926-grounded (grounded)

- A（基线）: `bench/results/20260925-full`，20260925T114023Z，模型 glm-5.3-flash
- B: `bench/results/20260926-grounded`，20260926T022509Z，模型 glm-5.3-flash

## 总表

| 指标 | A（基线） | B | 变化 |
|---|---|---|---|
| 功能数 | 20 | 20 | 0 |
| 运行次数 | 100 | 100 | 0 |
| planner 产出合法用例 | 97.0% | 98.0% | — |
| 覆盖：至少一轮被覆盖的功能 | 15/20 | 19/20 | +4 |
| 覆盖：按运行计 | 53.0% | 90.0% | — |

| 裁判 | A 误报率（健康·已覆盖） | B 误报率 | 变化 | A 漏报率 | B 漏报率 | 变化 | A 一致率 | B 一致率 |
|---|---|---|---|---|---|---|---|---|
| LLM 裁判（看步骤结果） | 47.2%（53） | 17.8%（90） | -29.4pp | 0.0%（10） | 0.0%（18） | +0.0pp | 44.4% | 63.2% |
| LLM 盲裁判（只看页面） | 77.4%（53） | 62.2%（90） | -15.1pp | 10.0%（10） | 0.0%（18） | -10.0pp | 38.9% | 63.2% |
| 纯断言（无 LLM） | 37.7%（53） | 12.2%（90） | -25.5pp | 30.0%（10） | 5.6%（18） | -24.4pp | 55.6% | 57.9% |

## 成本

| 指标 | A（基线） | B | 变化 |
|---|---|---|---|
| tokens 总计 | 1,431,297 | 2,348,562 | +917,265 |
| tokens / 运行 | 14,313 | 23,486 | +9,173 |
| LLM 调用耗时累计 (s) | 21362.8 | 32305.1 | +10942.3 |
| 总墙钟 (s，按轮最大并发折算) | 3601.1 | 5886.3 | +2285.2 |
| 失败 LLM 调用 | 14 | 61 | +47 |
| 探索墙钟 (s，grounded 专属) | — | 19277.0 | — |

## 逐功能对比（覆盖率 = 覆盖轮数 / 合法用例轮数；informed 结论为健康系统各轮）

| 功能 | A 覆盖 | B 覆盖 | Δ | A informed | B informed |
|---|---|---|---|---|---|
| about-page | 5 | 5 | = | fail pass pass fail fail | pass pass pass pass unsure |
| archives-page | 0 | 5 | → | unsure unsure unsure unsure unsure | pass pass pass pass pass |
| category-list | 5 | 5 | = | pass unsure pass pass pass | unsure pass pass pass pass |
| create-category | 4 | 4 | = | pass fail fail fail fail | pass unsure pass fail pass |
| create-tag | 1 | 4 | → | fail fail fail fail fail | unsure pass pass pass pass |
| home-posts | 2 | 5 | → | unsure fail unsure unsure fail | pass pass pass pass pass |
| login | 5 | 5 | = | pass pass pass pass pass | pass pass pass pass pass |
| menu-items | 2 | 5 | → | unsure fail fail unsure fail | unsure unsure unsure unsure unsure |
| notification-list | 4 | 5 | → | fail fail pass fail pass | pass pass pass pass pass |
| page-list | 0 | 5 | → | fail fail fail fail fail | pass pass pass pass pass |
| plugin-list | 5 | 5 | = | fail pass unsure fail unsure | pass pass pass pass pass |
| post-detail | 0 | 5 | → | unsure - unsure unsure unsure | pass pass unsure pass pass |
| post-list | 4 | 5 | → | fail unsure unsure fail pass | pass pass pass pass pass |
| publish-post | 0 | 0 | = | unsure unsure unsure unsure unsure | unsure - - unsure unsure |
| role-list | 0 | 3 | → | fail fail fail fail fail | pass fail fail pass fail |
| search-posts | 1 | 5 | → | unsure - fail - unsure | fail fail fail fail fail |
| site-title | 5 | 5 | = | pass pass pass pass pass | pass pass pass pass pass |
| tag-list | 3 | 4 | → | pass fail fail pass fail | pass unsure fail pass pass |
| tags-page | 2 | 5 | → | unsure unsure unsure fail unsure | pass pass pass pass pass |
| user-list | 5 | 5 | = | pass pass pass pass pass | pass pass pass pass pass |

### 关于"探索墙钟 19277.0s"这一行：一个发现并已修的计时 bug

跑完整 5 轮之后核对成本数据才发现：`grounding.explore_seconds` 的计时起点在整个 grounded 流程
**最开始**（探索之前），终点在选页 + 写用例（+ 可能的修复重试）**全部**完成之后——名字叫"探索"，
实际把两次 LLM 往返也算了进去，所以 comparison.md 这一行（19277.0s，比总墙钟 5886.3s 还大很多）
明显不对。已经在 `agent/planner.py` 里改成只在 `explorer.site_map_text()` / `page_snapshot()` /
`expanded_snapshot()` 三个调用本身周围计时，不含中间的 LLM 调用。

这次的 100 条记录是用旧口径跑出来的，重跑一次 5 轮基准成本太高不值得；改用 `calls.jsonl` 里
`plan:grounded:*` 各阶段的 `latency_ms` 反推校正（`记录值 - 同一次调用里 select/write/repair 的
LLM 耗时`），拿到修正后的探索耗时：**100 次规划平均 4.66s／次**（多数在 2.3–8.5s，对应 1–2 次
页面导航；个别拿到"本轮第一次探索站点地图"任务的调用会到 18–22s，那是全程只发生一次的一次性
成本，其余全靠缓存）。这个量级符合设计预期的"已知取舍"（每功能多开 1–2 个页面）。往后的跑法
不用再反推，代码已经直接记录准确值。

### 逐功能：改善 / 基本不变 / 变差

**改善（15 个）**：`about-page`、`archives-page`、`category-list`、`create-category`、
`create-tag`、`home-posts`、`notification-list`、`page-list`、`plugin-list`、`post-detail`、
`post-list`、`role-list`、`tags-page`、`tag-list`、`search-posts`（覆盖与一致性都上升，但见
下面专门说明——不是单纯的"变好"）。其中 `page-list`、`post-detail`、`archives-page` 是阶段 B
里"5 轮全部未覆盖"的功能，这次 5/5 全覆盖；`role-list`（阶段 B 里典型的"编造 `/console/roles`"
案例）覆盖到 3/5。`category-list`/`create-category`/`tag-list` 三个覆盖轮数本身没变或只多 1，
放进"改善"是因为 informed 结论质量明显变好（更多 pass、更少连续 fail），程度比其余 12 个轻。

**基本不变（3 个）**：`login`、`site-title`、`user-list`——阶段 B 已经是 5/5 覆盖、informed
全 pass，这次同样，没有再改善的空间。

**变差（2 个，如实写）**：

- **`publish-post`**：覆盖仍是 0/5（阶段 B 也是 0/5，没有改善），但 planner
  可靠性**下降**了——阶段 B 每轮都能产出合法用例（5/5，只是没测对）；这次只有 3/5 轮产出用例，
  另外 2 轮（round 2、3）grounded 的写用例调用超时（180s）用尽重试后降级 baseline，baseline
  的规划**也**超时，两轮完全没有用例可执行。原因大概率是文章编辑器页面的可访问性树本身就很大
  （富文本编辑器 + 大量工具栏），grounded 比 baseline 多一次"写用例"LLM 调用还要把这份大快照
  塞进提示词，让本来就容易卡在 180s 超时线上的这个功能更容易两次都超时。round 1 唯一一次
  grounded 成功产出用例的运行，卡在执行阶段：编辑器页面上"发布"按钮和"文章设置"确认弹窗里的
  "发布"按钮**名字完全相同**，`role=button[name="发布"]` 精确匹配到两个元素，Playwright
  strict mode 报错——这正是本任务书"已知取舍"里说的"静态校验只查存在性不查唯一性"会漏的那类
  问题，两个 LLM 裁判（`informed`/`blind`）都正确识别出发布流程没走完。
- **`menu-items`**：覆盖从 2/5 升到 5/5（探针确实命中了目标接口），但 `informed` 裁判 5 轮
  全部给 `unsure`（阶段 B 是 unsure/fail 混合）——覆盖变好了，但裁判仍然没能给出确定结论，
  没有真正解决"这个功能到底测没测对"的问题，只是从"没测到"变成"测到了但看不准"。

**需要单独说明的一个"变差看起来像变差，其实是抓到真问题"的例子**：`search-posts` 覆盖从 1/5
升到 5/5，但 `informed` 结论从阶段 B 的"多为 unsure/缺失"变成这次的"5 轮全部一致 fail"，理由
逐轮几乎相同——搜索框输入关键词"Hello Halo"后，文章列表仍显示全部 10 篇文章（含明显不匹配的
标题），关键词过滤没有生效。5 轮独立生成的用例给出同样、具体、可复现的失败描述，这更像是
grounded planner 终于把用例写到了真实搜索接口上、从而稳定复现了一个真实的产品行为（搜索过滤
未生效，或者前端没等异步过滤结果就断言），而不是用例本身写错——按现在的口径这仍然算一次"误报"
（健康系统上非 pass），但它的性质和"编造了不存在的路由/文案"完全不同，值得区分开来看。

### 剩余误差来源分类（沿用阶段 B 的分类方式）

阶段 B："44 次未覆盖" = 选择器定位失败 25、超时 9、断言了不存在的文案 6（另有若干 planner 生成
失败与"全部步骤跑完但没打到接口"，未在原表逐项列出）。这次同样只统计**未覆盖**的运行（100 次里
10 次未覆盖，对应 90.0% 的覆盖率）：

| 类别 | 次数 | 说明 |
|---|---|---|
| 选择器定位失败（locator_failed） | 4 | 含 `publish-post` 的"发布"按钮同名歧义（见上）|
| 执行超时（timeout） | 2 | `tag-list` 一次、`publish-post` 一次 |
| planner 完全没产出用例（超时耗尽重试） | 2 | 全是 `publish-post`；grounded 特有的新增来源——多一轮 LLM 往返多一次超时机会 |
| 断言失败（assert_failed） | 1 | `role-list` 一轮 |
| 全部步骤跑完但没打到探针接口 | 1 | `role-list` 一轮：用例本身跑通了，但没有触发到目标接口 |

对比阶段 B，"选择器定位失败"仍是最大类但占比明显下降（44 次里 25 次 ≈ 57% → 10 次里 4 次 = 40%），
"断言了不存在的文案"这一类基本消失（grounded 模式下断言文案来自真实快照，静态校验也会拦一部分）；
新出现的"planner 完全没产出用例"是 grounded 模式本身带来的新成本，两轮 LLM 往返意味着两倍的
超时暴露面。

### grounded 选页校验的一个已知漏洞（顺带发现，未修，记录在这里）

`_select_page()` 校验"LLM 选的 URL 必须来自站点地图"的实现是
`chosen in urls or any(chosen.startswith(u) for u in urls)`。站点地图里前台首页的条目就是裸
`http://localhost:8090/`——任何同源 URL 天然满足 `startswith` 这个裸 origin，等于这条校验对
"必须来自站点地图"基本不设防。实测中 `role-list` 有一轮就选中了从未出现在站点地图里的
`http://localhost:8090/console/roles`（阶段 B 里那个会 404 的路由）——这次因为 Halo 的客户端
路由把它重定向到了 `/console/users`，而"写用例"那一步是基于**重定向后的真实快照**写的，
最终用例正确地 `goto` 到了 `/console/users`，蒙对了。这次没造成实际问题，但校验本身不牢固，
留在这里给下一步参考（本次任务范围内没有去修，因为写用例步骤已经用真实快照兜底了一层，
性价比排在探索/并发两个阻塞问题之后）。

### 顺带：Halo 的一个可观测性问题（issue 草稿，未提交）

阶段 B 排除的 3 个功能（评论列表、附件列表、仪表盘统计）在接口失败时给不出可断言的持久信号——
仪表盘统计值直接静默变 0/空，和真的空站点没有区别；评论/附件列表会闪一下"500: Internal Server
Error" toast，但几秒后消失，之后列表区既不是真的空状态（缺"当前没有评论"文案和"刷新"按钮）也
没有任何错误提示，只剩一个没有可访问名的图标。用 Playwright `page.route()` 注入 500 实测复现，
写成了草稿：[`docs/issues/halo-empty-state-on-api-error.md`](docs/issues/halo-empty-state-on-api-error.md)
（只是草稿，没有提交到 GitHub；先搜过 halo-dev/halo 现有 issue，没找到重复的）。

## 复现

依赖：Docker、Python ≥ 3.12（含 uv）、可访问 PyPI / Playwright 源 / 火山方舟的网络。

```bash
# 1) 安装依赖（Python >= 3.12）
uv sync
uv run playwright install chromium

# 2) 配置密钥（只进 .env，不进仓库）
cp .env.example .env
#    编辑 .env：
#      LLM_API_KEY   必填（OpenAI 兼容接口；默认配置为火山方舟 coding plan 端点）
#      LLM_MODEL     默认 glm-5.3-flash
#      LLM_TIMEOUT_S 默认 180（长 JSON 输出在部分网关较慢）
#      HALO_ADMIN_PASSWORD 留空则 scripts/up.sh 自动生成随机密码并写回 .env

# 3) 起 Halo 靶子（端口固定 8090，幂等可重复执行；数据卷 .runtime/halo2 保留）
./scripts/up.sh

# 4) 跑 3 条手写用例（执行 -> 裁判 -> 报告）
uv run python -m agent.run --case cases/01_login.json
uv run python -m agent.run --case cases/02_create_publish_post.json
uv run python -m agent.run --case cases/03_change_site_title.json

# 4b) planner 冒烟：一句话功能 -> LLM 生成用例 -> 执行
RUN_DIR="runs/$(date -u +%Y%m%dT%H%M%SZ)-planner-smoke" && mkdir -p "$RUN_DIR"
uv run python -m agent.planner \
  --feature "管理员在用户管理页查看用户列表，能看到 admin 账号及其角色" \
  --feature-id view-user-list --run-dir "$RUN_DIR" --out "$RUN_DIR/case.json"
uv run python -m agent.run --case "$RUN_DIR/case.json"

# 4c) 纯断言消融口径（不调 LLM，裁判结论由步骤结果机械推导；报告写入指定目录）
uv run python -m agent.run --case cases/01_login.json --skip-judge --reports-dir reports-ablation

# 4d) 阶段 B 基准（约 60 分钟；--only f1,f2 跑子集；中断后加 --resume 续跑）
# --planner 默认 grounded；--planner baseline 才是复现 20260925-full 那份基线数字
uv run python -m bench.validate_reference            # 参考用例健康/注入两态校验
uv run python -m bench.run_bench --rounds 5 --planner baseline --out-dir bench/results/<name>
uv run python -m bench.metrics bench/results/<name>  # 写 summary.json / summary.md

# 4e) B2：grounded planner 同一基准重跑 + 对比（约 90–100 分钟，比 baseline 慢——多了
#     两步规划里的探索 + 选页 LLM 调用；探索本身的墙钟很小，见"B2"一节里的口径说明）
uv run python -m bench.run_bench --rounds 5 --planner grounded --out-dir bench/results/<date>-grounded
uv run python -m bench.metrics bench/results/<date>-grounded
uv run python -m bench.compare bench/results/20260925-full bench/results/<date>-grounded

# 5) 收工清理
./scripts/down.sh           # 数据保留；--purge 连数据卷一起删
```

说明：
- 每次运行的报告为 `reports/<run_id>.json` + `.md`；`run_id` 含 UTC 时间戳，重跑会产生新报告，不会覆盖旧报告；
- LLM 每次调用的审计（prompt hash、token 数、耗时、错误）在 `runs/<run_id>/calls.jsonl`，
  报告 JSON 的 `llm` 字段是它的汇总；
- 失败运行同样产出报告；本仓库保留全部失败报告（见上表 planner 迭代）。

## 目录结构

```
agent/        # 全部核心代码（llm/planner/schema/executor/judge/report/run）
bench/        # 阶段 B：功能清单、参考用例校验、基准 runner、指标；results/ 为提交的基准结果
cases/        # 手写用例 JSON（受限动作集）
scripts/      # up.sh / down.sh / init_admin.py（起靶子、幂等初始化管理员）
reports/      # 每次运行的 JSON + Markdown 报告（进 git，README 数字出处）
runs/         # 运行期产物：截图、calls.jsonl（LLM 调用审计；不进 git）
docs/         # design.md（Milestone C）
```

## 硬性约定

- LLM 调用统一走 `agent/llm.py`（OpenAI 兼容，模型/温度/超时可配），每次调用的
  prompt hash、token 数、耗时记入 `runs/<run_id>/calls.jsonl`；
- 用例 `steps` 只能使用受限动作集 `goto/click/fill/select/wait_for/assert_text/assert_visible/assert_url`，
  由 `agent/schema.py` 在 JSON 层强制校验（多余参数、未知动作直接拒绝），非法用例不会进入执行器；
- 选择器优先级 `role= > label= > text= > placeholder= > CSS`，支持 `>>` 链式作用域
  （如 `role=dialog >> role=button[name="发布"]`，应对页面上出现两个同名按钮）；
- 凭据用 `{{ADMIN_USER}}` / `{{ADMIN_PASSWORD}}` 占位符写在用例里，执行时从 `.env` 渲染，
  快照/日志/报告落盘前统一脱敏（已验证报告 JSON 中不含密码明文）；
- 每步失败归入三类之一：`定位失败 / 超时 / 断言失败`（口径见 `agent/executor.py` 模块注释与报告 JSON 的 `failure_class` 字段）；
- 裁判三态 `pass/fail/unsure`，只看文本快照；裁判输出不可解析时降级为 `unsure`，绝不默认 pass；
  裁判证据必须引用快照行号（见报告 `judge.evidence[].snapshot_line`）。

## 已知限制

- 定位脆弱：用例选择器依赖中文界面文案（role/label/name），Halo 换语言或改版会批量失败；
- 裁判偏保守：证据不足即 `unsure`，会拉低"可直接采信率"（Milestone B 数据：健康系统已覆盖运行中 7/53 为 unsure）；
- 生成用例质量是最大短板：Milestone B 中按运行计只有 53% 的用例真正触达目标接口；
- 3 类功能（接口失败与空数据 UI 相同）无法从 UI 判定，已从基准中排除；
- 只测中文界面：选择器与断言均按简体中文 UI 编写；
- 执行器屏蔽被测应用外联域名（默认 `release-checker.halo.run` 等，可关闭）以提高确定性，
  意味着与外联相关的功能不在本工具的测试范围内；
- `runs/`（截图、调用审计）不进 git，报告 JSON 内含成本汇总与脱敏快照，复核不依赖本机历史文件。
