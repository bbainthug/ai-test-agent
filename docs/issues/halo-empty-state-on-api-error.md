# [Draft] Console list/stat pages give no persistent, assertable signal when their API call fails

> **Status: draft, not filed.** Written for internal review; not posted to GitHub.

Formatted to match `halo-dev/halo`'s `bug_report.en.yml` issue template (see
`.github/ISSUE_TEMPLATE/bug_report.en.yml` in that repo) so it's ready to paste in as-is once
someone decides to file it.

### Prerequisites

- [x] Searched [halo-dev/halo issues](https://github.com/halo-dev/halo/issues) for related reports
      (queries below) — none found.
- [x] This is an issue with the Halo project itself (reproduced with a stock install, no plugins,
      no theme changes beyond the default).
- [x] Not applicable — no plugins installed in the repro environment.
- [x] Not applicable — not a plugin/theme issue.

### System information

Two repro environments, both local Docker, default theme, no plugins:

```
- External url: http://localhost:8090 (local Docker repro, not a public instance)
- Version: 2.20.21 (image registry.fit2cloud.com/halo/halo:2.20) — original repro
- Version: 2.26.1 (image registry.fit2cloud.com/halo/halo:2.26.1) — re-verified 2026-09-26,
  latest stable at the time (2.27.0-beta.1 is a prerelease and was not tested)
- Activated theme: default
- Enabled plugins: none
```

### What is the project operation method?

Docker

## What happened?

Three console pages — comments list, attachments list, dashboard statistics — give a UI-driven
test (or a user who isn't watching the exact moment the page loads) **no reliable way to tell
"no data yet" apart from "the backing API request failed"**. This holds on both 2.20.21 and the
current latest stable, 2.26.1, though the exact presentation differs slightly between the two
(details and diffs below — the underlying ambiguity is the same).

- **Dashboard**: the stat cards' labels (文章/用户/评论/浏览量) render normally; the *values*
  fall back to `"0"` on a failed request, identical to a genuinely fresh/empty site. On 2.20.21
  there was no toast at all for the dashboard specifically; **on 2.26.1 a toast now does appear**
  for the dashboard case too (see version differences below) — but it's still transient, and once
  it's gone the four values sit at a silent, persistent `"0"` with no error indicator anywhere.
- **Comments / attachments**: on a failed request, a toast reading `"500: Internal Server
  Error"` appears, then fades — but it is not a fixed ~7s: measured on 2.26.1, it is still present
  at 7s and only gone by 15s (see version differences). After it fades, the list area's final
  state is indistinguishable from — or (on 2.26.1) literally identical text to — the genuine
  empty-state placeholder, so an assertion on item count, "list is empty", or the pagination
  footer text `"共 0 项数据"` ("0 items total") cannot tell the two apart.

So the precise problem is narrower than "identical in every pixel at every instant" but broader
than "just a missing retry button": catching the difference requires an assertion on the *exact*
empty-state copy within the toast's lifetime (which itself varies, see below); anything checking
item count, a generic "list is empty" signal, or running its assertion after the toast fades will
see the same thing whether the API succeeded-with-zero-rows or failed outright. For dashboard,
after the (now sometimes-present) toast fades, there is no window at all — it's indistinguishable
at any later point in time.

This was discovered building an LLM-driven e2e test agent against Halo: we inject a synthetic 500
on each feature's key API via Playwright's `page.route()` and check whether the resulting page
state gives a judge (LLM or assertion) anything to react to. For these three, it effectively
doesn't, so we excluded them from our benchmark (see
[`bench/features.json`](../../bench/features.json) → `excluded`) rather than report a false
"agent failed to detect the fault" result.

### Version differences (2.20.21 → 2.26.1), found while re-verifying for this write-up

- **Dashboard now shows a transient toast too.** On 2.20.21 the dashboard case had no toast at
  all (silent value fallback only). On 2.26.1, injecting the 500 also produces the
  `"500: Internal Server Error"` toast, which fades by ~15s — after which the values are still
  silently `"0"` with nothing else in the accessibility tree, same end state as before.
- **Toast lifetime is longer than originally measured.** The original repro used a fixed 7s wait
  on the assumption the toast had faded by then. Re-measured on 2.26.1 with checks at 2s/7s/15s:
  the toast is still present at both 2s and 7s, and gone by 15s. The reproduction steps below use
  a 15s wait to be safe on either version.
- **Comments/attachments empty-area text is now identical between genuine-empty and post-error,
  not just similarly uninformative.** On 2.20.21, after the toast faded the failed-request state
  showed a bare unlabeled `<img>` with no text and no button — visibly different markup from the
  real empty state (which has icon + text + button), just equally uninformative to an assertion
  that only checks item count. On 2.26.1, once the (now longer-lived) toast fades, the
  failed-request state renders the *exact same* empty-state text and retry button as the genuine
  empty state (`"当前没有评论 你可以尝试刷新或者修改筛选条件"` / `"当前分组没有附件..."`) — the
  two are now indistinguishable even by their copy, not only by pagination count. If anything,
  this makes the ambiguity slightly worse on the current version, not better.

## Reproduce Steps

No backend changes needed — a Playwright network intercept reproduces it locally on either
version:

```python
page.route(
    "**/apis/api.console.halo.run/v1alpha1/comments*",
    lambda route: route.fulfill(status=500, content_type="application/json",
                                 body='{"message":"boom"}'),
)
page.goto("http://localhost:8090/console/comments")
page.wait_for_timeout(15000)  # let the transient toast finish fading (measured up to ~15s on 2.26.1)
```

The three API paths (captured by watching `page.on("request", ...)` while loading each page,
logged in as admin), unchanged between versions:

| Page | URL | Intercepted API |
|---|---|---|
| Comments | `/console/comments` | `GET /apis/api.console.halo.run/v1alpha1/comments*` |
| Attachments | `/console/attachments` | `GET /apis/api.console.halo.run/v1alpha1/attachments*` |
| Dashboard | `/console/dashboard` | `GET /apis/api.console.halo.run/v1alpha1/stats*` |

Compare against the same page **without** the intercept, on the same (mostly-empty) admin
account, to see the two states side by side.

## Relevant log output

No server-side error is needed to reproduce (the 500 is injected client-side by the test); no
Halo server log output is relevant to this bug. Browser-side, the only observable signal is the
transient toast text `"500: Internal Server Error"` described above.

## Additional information

### Actual behavior, 2.20.21 (original repro)

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

**Comments** — a toast appears then fades; what's left afterward is *not* the real empty state,
but it's just as uninformative as one:
```
 normal (genuinely empty list):        500-injected, ~7s after load (toast gone on 2.20.21):
  - img "Empty"                         - img              (no accessible name)
  - text: 当前没有评论 你可以尝试...     (— no text node here at all —)
  - button "刷新"                       (— no button here at all —)
  - text: 共 0 项数据                    - text: 共 0 项数据      <- identical in both
```

**Attachments** — same pattern as comments (own empty-state copy "当前分组没有附件" +
"上传附件" button vs. a bare unlabeled `<img>` once the toast fades).

### Actual behavior, 2.26.1 (re-verified 2026-09-26)

**Dashboard** — same silent value fallback as 2.20.21, but now *with* a transient toast that
fades by ~15s:
```
 normal:                    500-injected (after toast fades):
  - text: 文章                - text: 文章
  - paragraph: "1"            - paragraph: "0"
  - text: 评论                - text: 评论
  - paragraph: "0"            - paragraph: "0"
  - text: 用户                - text: 用户
  - paragraph: "1"            - paragraph: "0"
  - text: 浏览量              - text: 浏览量
  - paragraph: "0"            - paragraph: "0"
```

**Comments / attachments** — toast confirmed present at 2s and 7s, gone by 15s; area text is now
byte-identical to the genuine empty state in both cases:
```
 normal (genuinely empty list):        500-injected, ~15s after load (toast gone):
  - img "Empty"                         - img "Empty"
  - text: 当前没有评论 你可以尝试刷新或者修改筛选条件   - text: 当前没有评论 你可以尝试刷新或者修改筛选条件   <- identical
  - button "刷新"                       - button "刷新"                                  <- identical
  - text: 共 0 项数据                    - text: 共 0 项数据                               <- identical
```

Common to all three, on both versions: no `role="alert"`/persistent banner, no retry affordance
that survives past the toast's lifetime, nothing in the accessibility tree that says "this
failed" once the toast is gone.

## Expected behavior

- A failed data request should render a **distinct, persistent** error state — different text
  ("加载失败，请重试" or similar), ideally a retry button, and ideally exposed with
  `role="alert"` (or similar) so it survives in the accessibility tree rather than only existing
  as a transient toast.
- This should hold for at least: comment list, attachment list, and the dashboard's statistic
  cards. Comments and attachments look like they may share one underlying list/empty-state
  component (same behavior pattern on both versions), so the fix might be a single shared
  component.

## Impact

- **Automated testing**: a UI-driven test asserting on item counts, "list is empty", or running
  its check any time after the toast fades cannot distinguish "no data yet" from "backend broke".
  This is exactly the failure mode we hit and had to work around by excluding these three checks
  from our benchmark rather than report a misleading pass/fail on them.
- **Real users/admins**: the same ambiguity applies — an admin looking at a dashboard reading all
  zeros, or a comments/attachments page with the normal empty-state copy, cannot tell whether
  that's genuinely empty or something is broken, unless they happen to be watching the screen in
  the toast's brief (and, per the above, version-dependent) window.

## Evidence

Full aria-snapshot captures (normal vs. 500-injected) for all three pages, both versions, were
captured during this investigation via Playwright's `locator("body").aria_snapshot()` against
locally running Halo instances (not screenshots — this repo's judge design only uses text
snapshots, see [`docs/design.md`](../design.md)). Re-run the repro script above against a local
Halo instance to regenerate them; the excerpts above are the relevant portions.

## Existing issues

Searched `halo-dev/halo` (via `gh search issues`) — queries tried: "empty state error", "500
error state", "loading failed", "api error empty", "fetch failed silently", "request failed empty
list", "console empty", "error toast", "attachment list error", "comment list", "dashboard
statistics" (Chinese equivalents also tried: "无法区分 报错", "接口异常 空状态", "评论列表
500", "统计 0", "dashboard statistics zero"). No existing issue found describing this
empty-vs-error ambiguity for these pages, on either the original search or the 2026-09-26 recheck.
If one turns up before filing, link it here instead of opening a duplicate.

## Environment

- Halo versions: 2.20.21 (original repro) and 2.26.1 (latest stable, re-verified 2026-09-26) —
  both Docker, `registry.fit2cloud.com/halo/halo:2.20` / `:2.26.1`
- Reproduced via: Playwright (Chromium), `page.route()` request interception, admin session
- Source: [`bench/features.json`](../../bench/features.json) excluded-features list;
  [`docs/results.md`](../results.md) Milestone B results
