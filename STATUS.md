# Assay（原 ai-test-agent）现状

> 项目当前状态的唯一可信来源。开始工作前先读；每次任务结束时更新。
> 结果与过程细节见 `README.md`、`docs/results.md`、`docs/design.md`；任务书在 `docs/tasks/`。

最后更新：2026-10-02（仓库改名 ai-test-agent → assay；本地目录名未改）

## 一句话

用 LLM Agent 对开源建站系统 Halo 做端到端测试：一句话功能描述 → planner 生成受限动作用例 →
Playwright 执行 → LLM 裁判（pass / fail / unsure）→ 报告。公开仓库：github.com/bbainthug/assay。

## 已完成

| 阶段 | 结果（数字出处见 README 结果表） |
|---|---|
| A 闭环 | 3 条手写用例 + 1 条 planner 生成用例全部 pass |
| B 基准 | 20 功能 × 5 轮：覆盖 53%，LLM 裁判误报 47.2% / 漏报 0%，纯断言漏报 30% |
| B2 grounded planner | 同一基准：覆盖 53% → **90%**，误报 47.2% → **17.8%**，漏报仍 0%；tokens/次 +64% |
| C 对外 | README 重构、`docs/design.md`、`docs/results.md`、演示 GIF、MIT、gitleaks 全历史干净、已公开 |
| LLM 客户端健壮性 | 429 限速退避重试（余额不足不重试）、空 choices 按失败记账；75 项测试通过 |

模型：glm-5.3-flash @ 火山方舟（基准用这个，换模型数字不可比）。靶子：Halo 2.20.21（Docker，`./scripts/up.sh`）。

## 进行中

（无）

## 下一步

- **重录演示 GIF**：当前 GIF 画面与字幕来自两次不同运行（`ab6ded18` vs `3969d8e9`）。火山额度 **2026-09-29 23:59:59（北京时间）** 才重置（29 日白天仍报 AccountQuotaExceeded），30 日起
  跑 `uv run python scripts/record_demo.py`，抽帧检查后提交推送。智谱免费 flash 和魔搭 GLM-5.2 都试过，录不成。
- **已知漏洞（未修）**：planner 静态校验不拦截非规定语法的选择器（如 `textbox "用户名"`）。
  修了属于 planner 逻辑变更，需重跑基准才能与现有数字对比——适合作为用户亲手完成的练习。
- **基准口径问题（未修）**：`bench/features.json` 里 `search-posts` 与 `post-list` 的故障点/探针正则完全相同
  （`/v1alpha1/posts(\?|$)`），打开文章列表页就算"覆盖"，搜索是否真的执行无法证明。B2 中 search-posts 覆盖 5/5
  因此可能偏乐观，整体按运行覆盖率 90% 最多高估约 5 个百分点。修法：探针要求带关键词参数；改了需重跑两组基准才可比。
  面试被问到覆盖率时应主动说明。（2026-09-29 由面试题库整理时读代码发现）
- 选页校验漏洞、同名按钮歧义（`>>` 链式选择器）——见 `docs/design.md` 局限一节。
- `bench/features.json` 的 20 条参考用例由 agent 起草、已对真实 Halo 自动校验，**待用户人工复核**。
- Halo issue 草稿 `docs/issues/halo-empty-state-on-api-error.md`（2.26.1 已复现、无重复）：是否提交由用户决定。

## 环境备忘

- `.env` 当前指向火山（基准模型）；`.env.volcano` / `.env.zhipu` / `.env.modelscope` 是各渠道配置备份，均被 git 忽略
- 写入 API key：`scripts/set_llm_key.sh`（不回显、不进历史）
- Halo 登录限流 3 次/分钟，基准按 21 秒间隔登录
