# 阶段 B 基准结果（20260925T114023Z，模型 glm-5.3-flash）

- 功能 20 个 × 5 轮 = 100 次运行；planner 产出合法用例 97.0%
- 覆盖：15/20 个功能至少一轮被覆盖；按运行计 53.0%

| 裁判 | 误报率（健康·已覆盖） | fail / unsure | 漏报率（注入故障） | 一致率（N 轮结论相同） |
|---|---|---|---|---|
| LLM 裁判（看步骤结果） | 47.2%（53 次） | 18 / 7 | 0.0%（10 次） | 44.4%（8/18） |
| LLM 盲裁判（只看页面） | 77.4%（53 次） | 9 / 32 | 10.0%（10 次） | 38.9%（7/18） |
| 纯断言（无 LLM） | 37.7%（53 次） | 20 / 0 | 30.0%（10 次） | 55.6%（10/18） |

成本：共 1,431,297 tokens，平均每次运行 14,313；LLM 调用耗时累计 21362.8 s（并发，非墙钟），总墙钟 3601.1 s；失败调用 14 次。

| 功能 | 合法用例 | 覆盖 | informed 各轮 | 故障注入（informed / blind / 断言） |
|---|---|---|---|---|
| about-page | 5/5 | 5/5 | fail pass pass fail fail | fail / fail / fail |
| archives-page | 5/5 | 0/5 | unsure unsure unsure unsure unsure | unsure / fail / fail（未触发） |
| category-list | 5/5 | 5/5 | pass unsure pass pass pass | fail / fail / fail |
| create-category | 5/5 | 4/5 | pass fail fail fail fail | fail / fail / fail |
| create-tag | 5/5 | 1/5 | fail fail fail fail fail | fail / fail / fail（未触发） |
| home-posts | 5/5 | 2/5 | unsure fail unsure unsure fail | unsure / unsure / fail（未触发） |
| login | 5/5 | 5/5 | pass pass pass pass pass | fail / fail / fail |
| menu-items | 5/5 | 2/5 | unsure fail fail unsure fail | unsure / fail / fail（未触发） |
| notification-list | 5/5 | 4/5 | fail fail pass fail pass | fail / fail / fail |
| page-list | 5/5 | 0/5 | fail fail fail fail fail | fail / fail / fail（未触发） |
| plugin-list | 5/5 | 5/5 | fail pass unsure fail unsure | fail / fail / pass |
| post-detail | 4/5 | 0/5 | unsure - unsure unsure unsure | unsure / unsure / fail（未触发） |
| post-list | 5/5 | 4/5 | fail unsure unsure fail pass | fail / fail / fail |
| publish-post | 5/5 | 0/5 | unsure unsure unsure unsure unsure | unsure / unsure / fail（未触发） |
| role-list | 5/5 | 0/5 | fail fail fail fail fail | fail / fail / pass（未触发） |
| search-posts | 3/5 | 1/5 | unsure - fail - unsure | unsure / fail / fail（未触发） |
| site-title | 5/5 | 5/5 | pass pass pass pass pass | unsure / pass / fail |
| tag-list | 5/5 | 3/5 | pass fail fail pass fail | fail / fail / pass |
| tags-page | 5/5 | 2/5 | unsure unsure unsure fail unsure | unsure / fail / fail（未触发） |
| user-list | 5/5 | 5/5 | pass pass pass pass pass | fail / fail / pass |
