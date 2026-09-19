"""页面文本快照：裁判的唯一视觉输入（文本化可访问性树，不用截图/OCR）。"""

from __future__ import annotations

from playwright.sync_api import Page


def text_snapshot(page: Page, max_chars: int = 12000) -> str:
    """返回当前页面的文本快照（紧凑可访问性树）。

    优先 locator("body").aria_snapshot()（Playwright >= 1.49），
    不可用时退回 page.accessibility.snapshot() 的缩进序列化。
    超长截断并标注 [TRUNCATED]。
    """
    tree = ""
    try:
        tree = page.locator("body").aria_snapshot()
    except Exception:  # noqa: BLE001 —— 旧版本 Playwright 没有该 API，走兜底
        tree = ""

    if not tree or not tree.strip():
        tree = _accessibility_fallback(page)

    if len(tree) > max_chars:
        tree = tree[:max_chars] + "\n… [TRUNCATED]"
    return tree


def _accessibility_fallback(page: Page) -> str:
    try:
        snap = page.accessibility.snapshot(interesting_only=True)
    except Exception:  # noqa: BLE001
        return "(无法获取页面快照)"
    if not snap:
        return "(空页面快照)"

    lines: list[str] = []

    def walk(node: dict, depth: int) -> None:
        role = node.get("role", "?")
        name = (node.get("name") or "").strip()
        value = node.get("value")
        piece = f"{'  ' * depth}- {role}" + (f' "{name}"' if name else "")
        if value is not None and str(value).strip():
            piece += f" = {str(value).strip()[:80]}"
        lines.append(piece)
        for child in node.get("children", []) or []:
            walk(child, depth + 1)

    walk(snap, 0)
    return "\n".join(lines)


def numbered(text: str, max_lines: int | None = None) -> str:
    """给快照加行号（L1, L2, ...），裁判引用证据时用行号定位。"""
    out = []
    for i, line in enumerate(text.splitlines(), start=1):
        if max_lines and i > max_lines:
            out.append(f"… [快照仅展示前 {max_lines} 行]")
            break
        out.append(f"L{i}: {line}")
    return "\n".join(out)


def redact(text: str, secrets: set[str]) -> str:
    """把敏感字符串替换为 ***（报告/日志落盘前调用）。"""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text
