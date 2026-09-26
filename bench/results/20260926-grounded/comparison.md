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
| 总墙钟 (s，按轮最大并发折算) | 3601.1 | 5886.3 | +2285.2000000000003 |
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
