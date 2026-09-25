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
| C | 对外产出（真实缺陷 issue/PR、GIF、docs/design.md） | 未开始 |

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
uv run python -m bench.validate_reference            # 参考用例健康/注入两态校验
uv run python -m bench.run_bench --rounds 5 --out-dir bench/results/<name>
uv run python -m bench.metrics bench/results/<name>  # 写 summary.json / summary.md

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
