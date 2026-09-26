# 详细结果

> 本页是 [README](../README.md) 关键结果表的展开版本：Milestone A（闭环跑通）、
> Milestone B（20 功能 × 5 轮基准）、B2（grounded planner）三节的完整过程记录，
> 从 README 原样迁移（数字、结论未改动；仅把 B2 对比表里从 `comparison.md` 直接粘贴的
> 二级标题降级为四级，避免打断本页的标题层级）。文末新增一节是 Milestone C 阶段的复核结果。

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

数字出处：[`bench/results/20260925-full/summary.md`](../bench/results/20260925-full/summary.md)
（逐次运行记录 `runs.jsonl`，可用 `bench.metrics` 重算）。模型 glm-5.3-flash，Halo 2.20.21，2026-09-25。

### 方法

- **20 个功能**（[`bench/features.json`](../bench/features.json)）：每个功能一句话描述 + 一个**故障注入点**
  （Playwright 拦截该功能的关键接口并返回 500）+ 一条**参考用例**；
- **参考用例校验**（[`bench/reference_validation.json`](../bench/reference_validation.json)）：20/20 条在健康系统上
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

数字出处：[`bench/results/20260926-grounded/`](../bench/results/20260926-grounded/)
（`runs.jsonl` 逐次记录、`comparison.md` 为 `bench.compare` 的原样输出）；基线不变，仍是
[`bench/results/20260925-full/`](../bench/results/20260925-full/)。同一模型（glm-5.3-flash）、
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

（[`bench/results/20260926-grounded/comparison.md`](../bench/results/20260926-grounded/comparison.md)
的原样输出）

# 基准对比：20260925-full → 20260926-grounded (grounded)

- A（基线）: `bench/results/20260925-full`，20260925T114023Z，模型 glm-5.3-flash
- B: `bench/results/20260926-grounded`，20260926T022509Z，模型 glm-5.3-flash

#### 总表

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

#### 成本

| 指标 | A（基线） | B | 变化 |
|---|---|---|---|
| tokens 总计 | 1,431,297 | 2,348,562 | +917,265 |
| tokens / 运行 | 14,313 | 23,486 | +9,173 |
| LLM 调用耗时累计 (s) | 21362.8 | 32305.1 | +10942.3 |
| 总墙钟 (s，按轮最大并发折算) | 3601.1 | 5886.3 | +2285.2 |
| 失败 LLM 调用 | 14 | 61 | +47 |
| 探索墙钟 (s，grounded 专属) | — | 19277.0 | — |

#### 逐功能对比（覆盖率 = 覆盖轮数 / 合法用例轮数；informed 结论为健康系统各轮）

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
写成了草稿：[`docs/issues/halo-empty-state-on-api-error.md`](issues/halo-empty-state-on-api-error.md)
（只是草稿，没有提交到 GitHub；先搜过 halo-dev/halo 现有 issue，没找到重复的）。


## Milestone C 复核：`search-posts` 不是 Halo 缺陷，是执行器动作集的限制

上面 B2 一节「逐功能对比」表里 `search-posts` 一行、以及"变差看起来像变差"一段，把
"搜索框输入关键词后列表仍显示全部文章、过滤未生效"记录为一次疑似真实产品行为（当时的判断是
"更像是 grounded planner 终于把用例写到了真实搜索接口上、从而稳定复现了一个真实的产品行为"）。
这个数字和当时的描述都不改；但对外发布前（任务书 C 第 4 条要求"在真实 Halo 上手工复现，不是靠
基准推断"）用 Playwright 手工复核后，结论要更正：**这是我们执行器受限动作集缺一个"按 Enter"
动作，不是 Halo 的产品缺陷。**

复核方法（Halo 2.20.21 与最新稳定版 2.26.1 各测一次，结果一致）：在控制台文章列表页准备两篇
标题不同的文章（`Hello Halo` / 一篇标题完全不相关的草稿），对搜索框做四种操作并比较
"共 N 项数据"：

| 操作 | 结果 |
|---|---|
| `page.fill("Hello Halo")`，不回车，等 3s | 仍显示全部文章（未过滤） |
| `page.type("Hello Halo", delay=80)` 模拟真实按键，不回车，等 3s | 仍显示全部文章（未过滤） |
| `page.fill("Hello Halo")` + 按 `Enter` | 只显示《Hello Halo》一篇（**过滤生效**） |
| `page.fill("Hello Halo")` + 按 `Enter`，等 2–3s | 同上，稳定 |

检查搜索框的 DOM（`.formkit-inner` 容器里只有一个裸 `<input name="keyword">`，没有相邻的搜索
按钮/图标）确认：这个控件是"输入 + 回车提交"式搜索，不是防抖实时过滤；点击或填值都不会触发
过滤，只有 `keydown Enter`（表单提交）会。

再看 `bench/results/20260926-grounded/runs.jsonl` 里 5 轮 `search-posts` 用例的实际步骤（详见
[`bench/results/20260926-grounded/runs.jsonl`](../bench/results/20260926-grounded/runs.jsonl)），
5 轮全部只用了 `fill` 填搜索框，没有一轮按过 `Enter`——而受限动作集
（`goto/click/fill/select/wait_for/assert_text/assert_visible/assert_url`，见
[design.md「架构与模块职责」](design.md#2-架构与模块职责)）里**没有"按键"这个动作**，`click` 也无处可点
（没有搜索按钮）。也就是说，只要用例只能用这个动作集，`search-posts` 这条用例**结构上不可能
测出真实的过滤结果**，5 轮结论一致的"fail"是同一个工具局限性重复触发，不是 5 次独立证实的产品
行为。

`create-tag` 5 轮里也有同样嫌疑（新建标签对话框的输入框有的浏览器/表单也是回车提交），但未逐条
复核，留给下一步（见 [design.md「局限与下一步」](design.md#5-局限与下一步)）。

**不追加 Halo issue 草稿**——按任务书第 4 条的分支，这属于"确认不是"产品问题的情形。
[`docs/issues/halo-empty-state-on-api-error.md`](issues/halo-empty-state-on-api-error.md) 这一份
（评论/附件/仪表盘空状态与接口报错不可区分）走的是另一条分支：在 2.20.21 与 2.26.1 上都手工复现
成功，属于真实产品问题，见该文件更新后的版本说明与两个版本的差异记录。
