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

## 不做什么

- 不做通用测试框架、不做多应用适配、不做 UI 界面；
- 不用截图做 OCR 或多模态裁判（成本与可复现性差）——裁判只看文本快照。

## Milestone 进度

| Milestone | 内容 | 状态 |
|-----------|------|------|
| A | 闭环跑通（3 条手写用例：登录 / 发文章 / 改站点标题），tag `v0.1` | 进行中 |
| B | 指标（20 功能人工基准、覆盖率/误报率/漏报率/一致性/成本、5 轮复跑、消融） | 未开始 |
| C | 对外产出（真实缺陷 issue/PR、GIF、docs/design.md） | 未开始 |

## 复现

依赖：Docker、Python ≥ 3.12（含 uv）、网络可达 PyPI / Playwright 源。

```bash
# 1) 安装依赖（Python >= 3.12）
uv sync
uv run playwright install chromium

# 2) 配置密钥（只进 .env，不进仓库）
cp .env.example .env
#    编辑 .env：填 LLM_API_KEY（OpenAI 兼容接口）
#    HALO_ADMIN_PASSWORD 留空则 scripts/up.sh 自动生成随机密码并写回 .env

# 3) 起 Halo 靶子（端口固定 8090，幂等可重复执行）
./scripts/up.sh

# 4) 跑通 3 条手写用例（执行 -> 裁判 -> 报告）
uv run python -m agent.run --case cases/01_login.json
uv run python -m agent.run --case cases/02_create_publish_post.json
uv run python -m agent.run --case cases/03_change_site_title.json

# 5) 收工清理
./scripts/down.sh           # 数据保留；--purge 连数据卷一起删
```

（Milestone A 跑通后，此处会补充：结果表、成本表，数字逐项对应 `reports/*.json`。）

## 目录结构

```
agent/        # 全部核心代码（llm/planner/schema/executor/judge/report/run）
cases/        # 手写用例 JSON（受限动作集）
scripts/      # up.sh / down.sh / init_admin.py（起靶子、初始化管理员）
reports/      # 每次运行的 JSON + Markdown 报告（进 git，数字出处）
runs/         # 运行期产物：截图、calls.jsonl（LLM 调用审计；不进 git）
docs/         # design.md（Milestone C）
```

## 硬性约定

- LLM 调用统一走 `agent/llm.py`（OpenAI 兼容，模型/温度/超时可配），每次调用的
  prompt hash、token 数、耗时记入 `runs/<run_id>/calls.jsonl`；
- 用例 `steps` 只能使用受限动作集 `goto/click/fill/select/wait_for/assert_text/assert_visible/assert_url`，
  由 `agent/schema.py` 在 JSON 层强制校验，非法用例不会进入执行器；
- 凭据用 `{{ADMIN_USER}}` / `{{ADMIN_PASSWORD}}` 占位符写在用例里，执行时从 `.env`
  渲染，报告落盘前统一脱敏；
- 每步失败归入三类之一：`定位失败 / 超时 / 断言失败`（口径见 `agent/executor.py` 模块注释）；
- 裁判三态 `pass/fail/unsure`，只看文本快照；裁判输出不可解析时降级为 `unsure`，绝不默认 pass。
