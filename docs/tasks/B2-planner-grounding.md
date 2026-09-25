# 任务 B2：让 planner 看见真实页面（grounded planner），并用同一基准做前后对比

> 交付给实现 agent 的任务书。先读 README 的「Milestone B 结果」一节和 `bench/`、`agent/planner.py`、
> `agent/executor.py`、`agent/snapshot.py`。

## 背景

阶段 B 基准（`bench/results/20260925-full/`，20 功能 × 5 轮，glm-5.3-flash）结论：

- 按运行计只有 **53%** 的生成用例真正触达目标接口（覆盖）；5 个功能 5 轮都没覆盖到；
- 未覆盖的 44 次里：选择器定位失败 25、超时 9、断言了不存在的文案 6；
- 典型错误：编造路由（角色管理写成会 404 的 `/console/roles`）、`name=保存` 子串匹配到"保存并继续添加"、
  等待页面上根本不存在的文本；
- 同样 20 个功能的人写参考用例是 20/20 有效——**问题出在 planner 凭一句描述猜页面**，不在执行器或裁判。

现在的 planner 只有一段手写的"系统事实"提示词，没看过任何真实页面。

## 目标

planner 生成用例前先**自动探索**被测应用、拿到真实的导航结构和目标页面的可访问性树，
只用树里真实存在的元素写选择器；然后用**完全相同的基准**重跑，给出前后对比。

成功标准（写进 README，不管达没达到都如实报）：覆盖率（按运行）与 `informed` 误报率相对基线有明显改善，
漏报率不变坏。

## 范围

### 1. 探索器 `agent/explorer.py`（新）

- **站点地图**（每轮一次，缓存到 `<run-dir>/site_map.json`）：登录一次，读取控制台侧边栏和前台导航的链接
  （文本 → URL）。Playwright 1.63 的 `aria_snapshot()` 对 link 会带 `/url:`，优先用它；拿不到再用 DOM 取 `href`。
  **必须是自动发现**，不许把 `features.json` 里的路由或任何按功能写的事实硬编码进去。
- **页面快照**：给定 URL，用已登录状态（`storage_state` 复用，**不要每个功能都重新登录**——Halo 登录限流
  3 次/分钟）打开页面，返回 `text_snapshot`（脱敏、截断）。
- **一层展开（可选但建议）**：允许 planner 请求"点击某个按钮后的快照"，用于新建对话框这类表单。
  只能点击树里存在的按钮，且**禁止点击提交类按钮**（名称含 保存/提交/发布/删除/确定/创建 等，写成可测试的黑名单）。
- 探索全程**只读**：不创建、不修改、不删除任何数据；探索用独立的 browser context，**不装故障、不计探针**
  （否则会污染覆盖率口径）。

### 2. grounded planner（改 `agent/planner.py`）

两步：

1. **选页面**：输入功能描述 + 站点地图 → LLM 输出要测的目标页面 URL（必须来自站点地图，或为站点地图中某 URL
   加路径参数时给出理由）以及是否需要一层展开；
2. **写用例**：输入功能描述 + 目标页面快照（+ 展开后的快照）→ 生成用例。

然后做**静态选择器校验**（纯函数，不跑浏览器）：用例里每个 `role=`/`label=`/`text=` 选择器必须能在对应页面的
快照里找到匹配（含 `name` 精确匹配，避免"保存"子串匹配到"保存并继续添加"）；不匹配时把具体问题回传 LLM
修一次，仍不过就照常交给执行器但在记录里标 `grounding_violations`。

- 保留旧 planner：`plan_case(..., mode="baseline"|"grounded")`，默认改为 `grounded`；
- 探索失败（页面打不开、登录失败）时降级为 baseline 并记录 `grounding: "fallback"`，不许静默；
- 现有"系统事实"提示词中的**通用**事实（登录跳 `/uc/profile`、`{{RUN_ID}}`、凭据占位符）保留；
  编辑器/站点设置等**页面具体事实**在 grounded 模式下应由快照替代——可以保留，但要在 README 说明。

### 3. 基准接入

- `bench.run_bench` 加 `--planner baseline|grounded`（默认 grounded），写入 `meta.json`；
- 每条记录加 `grounding` 字段（`ok | fallback`、选了哪个页面、违例数、探索耗时）；
- 成本统计把探索耗时单列（它不花 token，但花墙钟）；
- 新增 `bench/compare.py A_DIR B_DIR`：输出两次结果的并排表（覆盖、三种裁判的误报/漏报/一致率、成本），
  写 `comparison.md`。

### 4. 重跑与报告

- `uv run python -m bench.run_bench --rounds 5 --planner grounded --out-dir bench/results/<date>-grounded`；
- `bench.compare bench/results/20260925-full bench/results/<date>-grounded`；
- README 新增「B2：grounded planner」一节：做了什么、对比表、哪些功能改善/哪些没有/哪些变差、
  剩余误差来源的分类（沿用阶段 B 的分类方式）、成本变化。**变差的也要写**。

### 5. 顺带：Halo issue 草稿（不发布）

阶段 B 排除的 3 个功能（评论列表、附件列表、仪表盘统计）在接口 500 时与"没有数据"的空状态一模一样。
在 `docs/issues/halo-empty-state-on-api-error.md` 写一份 issue 草稿：复现步骤（用 Playwright route 注入 500
即可复现）、实际/期望行为、截图或快照片段、影响（用户与自动化测试都无法区分"没数据"和"加载失败"）。
先去 halo-dev/halo 搜一下有没有已存在的同类 issue，把链接写进草稿。**只写草稿，不要提交到 GitHub**。

## 公平性红线（违反则结果作废）

- 不改 `bench/features.json`（功能描述、故障点、参考用例）、`bench/metrics.py` 的口径、执行器与裁判；
- 同一模型（glm-5.3-flash）、同一 Halo 版本、同样 20 功能 × 5 轮；
- planner 不得读取 `features.json` 的 `fault` / `reference` 字段，不得读取历史 runs 里的用例；
- 不针对单个功能写特例提示词；
- 探索不计入覆盖，不带故障；
- 基线结果目录 `bench/results/20260925-full/` 保持原样。

## 测试

- 单元：站点地图从 aria 快照 fixture 中提取链接；选择器校验（精确 name 匹配、子串不算、`>>` 链式、
  CSS 选择器跳过校验）；提交类按钮黑名单；planner 两步的提示词里含快照与站点地图（FakeLLM）；
  探索失败降级为 baseline 且记录 fallback；
- 集成（需要 Halo，标 `@pytest.mark.halo`，默认跳过）：探索器在真实 Halo 上拿到的站点地图包含"文章""用户"等入口；
- 现有 56 个测试保持通过，ruff 干净。

## 交付

改动摘要、可复现命令、对比表（直接贴 `comparison.md`）、未解决问题；提交到本地 main（仓库无远程，不推送）。

## 已知取舍（不用来回问）

- 一层展开够用：多步向导类功能不在本次范围；
- 静态校验只查"能不能找到"，不查"找得对不对"——后者交给执行与裁判；
- 探索会增加墙钟（每功能多开 1–2 个页面），可接受，但要在成本里单列。
