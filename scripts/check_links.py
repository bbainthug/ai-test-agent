"""检查 README.md / docs/*.md 里的相对链接（文件是否存在、锚点是否匹配某个标题）。

只查本仓库内的相对链接（不含 http(s):// 的外链）。锚点用近似 GitHub 的 slug 规则
（小写、去掉大多数标点、空格变连字符）计算——足够用来抓"标题改了但链接没改"这类问题，
不追求跟 GitHub 逐字节一致。

用法：
  uv run python scripts/check_links.py
退出码非 0 表示发现失效链接。
"""

from __future__ import annotations

import re
from pathlib import Path

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
# 近似 GitHub slugger：保留字母/数字/下划线/连字符/空格（含中日韩字符，\w 在 re.UNICODE 下已包含），
# 其余标点一律去掉；再把空格换成连字符。
_STRIP_RE = re.compile(r"[^\w\- ]", re.UNICODE)


def slugify(heading: str) -> str:
    text = heading.strip().lower()
    text = re.sub(r"`([^`]*)`", r"\1", text)  # 去反引号，保留内容
    text = _STRIP_RE.sub("", text)
    text = re.sub(r"\s+", "-", text)
    return text


def headings_of(path: Path) -> set[str]:
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    return {slugify(m.group(2)) for m in HEADING_RE.finditer(text)}


def check_file(md_path: Path, root: Path) -> list[str]:
    errors = []
    text = md_path.read_text(encoding="utf-8")
    for m in LINK_RE.finditer(text):
        target = m.group(1)
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        file_part, _, anchor = target.partition("#")
        if file_part:
            resolved = (md_path.parent / file_part).resolve()
            if not resolved.exists():
                errors.append(f"{md_path}: 目标文件不存在: {target}")
                continue
        else:
            resolved = md_path
        if anchor:
            slugs = headings_of(resolved)
            if anchor not in slugs:
                errors.append(
                    f"{md_path}: 锚点未匹配到标题: {target} "
                    f"(在 {resolved} 里找不到 slug={anchor!r})"
                )
    return errors


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    targets = [root / "README.md", *sorted((root / "docs").glob("**/*.md"))]
    all_errors: list[str] = []
    for md_path in targets:
        if md_path.exists():
            all_errors.extend(check_file(md_path, root))
    if all_errors:
        print(f"[check_links] 发现 {len(all_errors)} 个问题：")
        for e in all_errors:
            print(" -", e)
        return 1
    print(f"[check_links] 检查了 {len(targets)} 个文件，链接全部有效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
