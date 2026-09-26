# 阶段 B 基准结果（20260926T022509Z，模型 glm-5.3-flash）

- 功能 20 个 × 5 轮 = 100 次运行；planner 产出合法用例 98.0%
- 覆盖：19/20 个功能至少一轮被覆盖；按运行计 90.0%

| 裁判 | 误报率（健康·已覆盖） | fail / unsure | 漏报率（注入故障） | 一致率（N 轮结论相同） |
|---|---|---|---|---|
| LLM 裁判（看步骤结果） | 17.8%（90 次） | 6 / 10 | 0.0%（18 次） | 63.2%（12/19） |
| LLM 盲裁判（只看页面） | 62.2%（90 次） | 8 / 48 | 0.0%（18 次） | 63.2%（12/19） |
| 纯断言（无 LLM） | 12.2%（90 次） | 11 / 0 | 5.6%（18 次） | 57.9%（11/19） |

成本：共 2,348,562 tokens，平均每次运行 23,486；LLM 调用耗时累计 32305.1 s（并发，非墙钟），总墙钟 5886.3 s；失败调用 61 次。

| 功能 | 合法用例 | 覆盖 | informed 各轮 | 故障注入（informed / blind / 断言） |
|---|---|---|---|---|
| about-page | 5/5 | 5/5 | pass pass pass pass unsure | fail / fail / fail |
| archives-page | 5/5 | 5/5 | pass pass pass pass pass | fail / fail / fail |
| category-list | 5/5 | 5/5 | unsure pass pass pass pass | unsure / fail / fail |
| create-category | 5/5 | 4/5 | pass unsure pass fail pass | fail / fail / fail |
| create-tag | 5/5 | 4/5 | unsure pass pass pass pass | unsure / fail / fail（未触发） |
| home-posts | 5/5 | 5/5 | pass pass pass pass pass | fail / fail / fail |
| login | 5/5 | 5/5 | pass pass pass pass pass | fail / fail / fail |
| menu-items | 5/5 | 5/5 | unsure unsure unsure unsure unsure | fail / fail / fail |
| notification-list | 5/5 | 5/5 | pass pass pass pass pass | fail / fail / fail |
| page-list | 5/5 | 5/5 | pass pass pass pass pass | fail / fail / fail |
| plugin-list | 5/5 | 5/5 | pass pass pass pass pass | fail / fail / fail |
| post-detail | 5/5 | 5/5 | pass pass unsure pass pass | fail / fail / fail |
| post-list | 5/5 | 5/5 | pass pass pass pass pass | fail / fail / fail |
| publish-post | 3/5 | 0/5 | unsure - - unsure unsure | unsure / fail / fail（未触发） |
| role-list | 5/5 | 3/5 | pass fail fail pass fail | fail / fail / pass |
| search-posts | 5/5 | 5/5 | fail fail fail fail fail | fail / fail / fail |
| site-title | 5/5 | 5/5 | pass pass pass pass pass | unsure / unsure / fail |
| tag-list | 5/5 | 4/5 | pass unsure fail pass pass | fail / fail / fail |
| tags-page | 5/5 | 5/5 | pass pass pass pass pass | fail / fail / fail |
| user-list | 5/5 | 5/5 | pass pass pass pass pass | fail / fail / fail |
