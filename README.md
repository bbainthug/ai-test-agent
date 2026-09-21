# ai-test-agent

用 LLM Agent 对真实开源系统 **Halo**（halo-dev/halo，开源建站系统）做端到端测试的闭环工具：

```
功能描述 ──planner(LLM)──> 结构化用例 JSON（受限动作集）
        ──executor(Playwright)──> 步骤日志/截图/文本快照（失败三分类）
        ──judge(LLM, 只看文本快照)──> pass / fail / unsure（三态）
        ──report──> reports/<run_id>.json + .md（含 LLM 成本审计）
```

> **先做再写**：本 README 中出现的每一个指标数字都来自 `reports/*.json`，可按
> [复现](#复现) 一节在干净环境重新跑出。没跑出来的不写；失败运行也保留报告。
> 当前靶子实测版本：Halo **2.20.21**（镜像 `registry.fit2cloud.com/halo/halo:2.20`）。

## 不做什么

- 不做通用测试框架、不做多应用适配、不做 UI 界面；
- 不用截图做 OCR 或多模态裁判（成本与可复现性差）——裁判只看文本快照。

## Milestone 进度

| Milestone | 内容 | 状态 |
|-----------|------|------|
| A | 闭环跑通：3 条手写用例（登录 / 发文章 / 改站点标题）+ planner 冒烟，tag `v0.1` | **完成，待复核** |
| B | 指标（20 功能人工基准、覆盖率/误报率/漏报率/一致性/成本、5 轮复跑、消融） | 未开始 |
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
- 裁判偏保守：证据不足即 `unsure`，会拉低"可直接采信率"（这是设计取向，Milestone B 用消融数据量化）；
- 只测中文界面：选择器与断言均按简体中文 UI 编写；
- 执行器屏蔽被测应用外联域名（默认 `release-checker.halo.run` 等，可关闭）以提高确定性，
  意味着与外联相关的功能不在本工具的测试范围内；
- `runs/`（截图、调用审计）不进 git，报告 JSON 内含成本汇总与脱敏快照，复核不依赖本机历史文件。
