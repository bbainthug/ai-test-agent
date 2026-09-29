# 工作约定

- **开始工作前先读 `STATUS.md`**（项目现状的唯一可信来源）；**任务结束时更新它**：改"最后更新"日期，
  把完成的条目移到"已完成"，新发现的问题写进"下一步"。
- 需要"当时为什么这么做"时：先看 `docs/tasks/` 任务书与 `git log`，再用 Hindsight 检索历史对话。
- README 与 `docs/` 里的每个数字必须来自 `reports/` 或 `bench/results/`；不改基准口径、功能清单、执行器与裁判
  就不能宣称"可比"。
- 密钥只进 `.env`（`.env.*` 一律不提交）；提交前跑 `uv run pytest`、`uv run ruff check .`、`gitleaks protect --staged`。
- 推送到公开仓库、在 GitHub 提 issue 前先征得用户同意。
