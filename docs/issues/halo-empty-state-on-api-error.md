# [Draft] Console list/stat pages give no persistent, assertable signal when their API call fails

> **Status: draft, not filed.** Per task instructions this is written for internal review only
> and must not be posted to GitHub. If it is later filed, remove this banner.

## Summary

Three console pages — comments list, attachments list, dashboard statistics — give a UI-driven
test (or a user who isn't watching the exact moment the page loads) **no reliable way to tell
"no data yet" apart from "the backing API request failed"**:

- **Dashboard**: the stat cards' labels (文章/用户/评论/浏览量) render normally; the *values*
  fall back to `"0"` or a blank `<paragraph>` on a failed request. This is pixel-and-text
  identical to a genuinely fresh site with zero posts/users/comments — there is no error
  indicator anywhere, ever (confirmed: no toast either).
- **Comments / attachments**: on a failed request, a toast reading `"500: Internal Server
  Error"` does appear — but it fades within a few seconds and leaves no trace in the DOM/aria
  tree. After it fades, the list area does **not** show the real empty-state placeholder (icon +
  "当前没有评论"/"当前分组没有附件" text + retry button) — it shows a single unlabeled `<img>`
  with no accessible name and no text. Both the genuine-empty and the failed-request states
  *do* share one thing an assertion is likely to check: the pagination footer text `"共 0 项数据"`
  ("0 items total") is identical in both cases, and there's no retry affordance in either.

So the precise problem is narrower than "identical in every pixel" but broader than "just a
missing retry button": for comments/attachments, catching the difference requires an assertion
on the *exact* empty-state copy within roughly the toast's few-second lifetime; anything checking
the item count, a generic "list is empty" signal, or running its assertion a few seconds later
will see the same thing whether the API succeeded-with-zero-rows or failed outright. For
dashboard, there is no window at all — it's indistinguishable at any point in time.

This was discovered building an LLM-driven e2e test agent against Halo 2.20 (glm-5.3-flash
planner + judges): we inject a synthetic 500 on each feature's key API via Playwright's
`page.route()` and check whether the resulting page state gives a judge (LLM or assertion)
anything to react to. For these three, it effectively doesn't, so we excluded them from our
benchmark (see [`bench/features.json`](../../bench/features.json) → `excluded`) rather than
report a false "agent failed to detect the fault" result.

## Steps to reproduce

No backend changes needed — a Playwright network intercept reproduces it locally:

```python
page.route(
    "**/apis/api.console.halo.run/v1alpha1/comments*",
    lambda route: route.fulfill(status=500, content_type="application/json",
                                 body='{"message":"boom"}'),
)
page.goto("http://localhost:8090/console/comments")
page.wait_for_timeout(7000)  # let the transient toast finish fading
```

The three API paths (captured by watching `page.on("request", ...)` while loading each page,
logged in as admin):

| Page | URL | Intercepted API |
|---|---|---|
| Comments | `/console/comments` | `GET /apis/api.console.halo.run/v1alpha1/comments*` |
| Attachments | `/console/attachments` | `GET /apis/api.console.halo.run/v1alpha1/attachments*` |
| Dashboard | `/console/dashboard` | `GET /apis/api.console.halo.run/v1alpha1/stats*` |

Compare against the same page **without** the intercept, on the same (mostly-empty) admin
account, to see the two states side by side.

## Actual behavior (verified against a running local Halo 2.20)

**Dashboard** — labels stay, values silently become 0/blank, no toast at all:
```
 normal:                    500-injected:
  - text: 文章                - text: 文章
  - paragraph: "10"           - paragraph: "0"
  - text: 用户                - text: 用户
  - paragraph: "1"            - paragraph        (no text)
  - text: 评论                - text: 评论
  - paragraph: "0"            - paragraph        (no text)
  - text: 浏览量              - text: 浏览量
  - paragraph: "27"           - paragraph: "0"
```

**Comments** — a toast appears then fades (~a few seconds); what's left afterward is *not* the
real empty state, but it's just as uninformative as one:
```
 normal (genuinely empty list):        500-injected, ~7s after load (toast gone):
  - img "Empty"                         - img              (no accessible name)
  - text: 当前没有评论 你可以尝试...     (— no text node here at all —)
  - button "刷新"                       (— no button here at all —)
  - text: 共 0 项数据                    - text: 共 0 项数据      <- identical in both
```

**Attachments** — same pattern as comments (own empty-state copy "当前分组没有附件" +
"上传附件" button vs. a bare unlabeled `<img>` once the toast fades).

Common to all three: no `role="alert"`/persistent banner, no retry affordance that survives past
the first few seconds, nothing in the accessibility tree that says "this failed" once the initial
toast (comments/attachments only) is gone.

## Expected behavior

- A failed data request should render a **distinct, persistent** error state — different text
  ("加载失败，请重试" or similar), ideally a retry button, and ideally exposed with
  `role="alert"` (or similar) so it survives in the accessibility tree rather than only existing
  as a transient toast.
- This should hold for at least: comment list, attachment list, and the dashboard's statistic
  cards. Comments and attachments look like they may share one underlying list/empty-state
  component (same behavior pattern), so the fix might be a single shared component.

## Impact

- **Automated testing**: a UI-driven test asserting on item counts, "list is empty", or running
  its check any time after the first ~5 seconds cannot distinguish "no data yet" from "backend
  broke". This is exactly the failure mode we hit and had to work around by excluding these three
  checks from our benchmark rather than report a misleading pass/fail on them.
- **Real users/admins**: the same ambiguity applies — an admin looking at a dashboard reading all
  zeros, or a comments/attachments page with a bare icon and no items, cannot tell whether that's
  genuinely empty or something is broken, unless they happen to be watching the screen in the
  first couple of seconds after the page loads.

## Evidence

Full aria-snapshot captures (normal vs. 500-injected) and screenshots for all three pages were
captured locally during this investigation (`/tmp/halo_repro/{comments,attachments,dashboard}_{normal,500,500_long}.{txt,png}`
on the machine this was investigated on — not included in this repo; re-run the repro script
above against a local Halo instance to regenerate them).

## Existing issues

Searched `halo-dev/halo` (via `gh search issues`) before drafting this: queries tried — "empty
state error", "500 error state", "loading failed", "api error empty", "fetch failed silently",
"request failed empty list", "console empty", "error toast", "attachment list error", "comment
list", "dashboard statistics" (Chinese equivalents also tried: "无法区分 报错", "接口异常 空状态").
No existing issue found describing this empty-vs-error ambiguity for these pages. If one turns up
before filing, link it here instead of opening a duplicate.

## Environment

- Halo version: 2.20 (Docker image `registry.fit2cloud.com/halo/halo:2.20`)
- Reproduced via: Playwright (Chromium), `page.route()` request interception, admin session
- Source: [`bench/features.json`](../../bench/features.json) excluded-features list;
  [README.md](../../README.md) Milestone B results
