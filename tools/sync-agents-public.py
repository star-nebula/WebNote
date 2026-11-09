#!/usr/bin/env python
"""从私有 AGENTS.md 生成脱敏的 AGENTS.public.md。

约定：私有内容只写在 `<!-- private:start -->` 与 `<!-- private:end -->` 之间。
生成器删掉这些块，再对结果做一次泄漏扫描（盘符路径、用户名、私有目录名），
命中就拒绝写出。唯一真源永远是 AGENTS.md，不要手改 AGENTS.public.md。

用法：
    python tools/sync-agents-public.py            # 重新生成 AGENTS.public.md
    python tools/sync-agents-public.py --check    # 只比对，漂移返回 1
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIVATE = os.path.join(ROOT, "AGENTS.md")
PUBLIC = os.path.join(ROOT, "AGENTS.public.md")

START = "<!-- private:start -->"
END = "<!-- private:end -->"

HEADER = """<!-- 由 tools/sync-agents-public.py 从仓库根的 AGENTS.md 生成，勿手改。 -->
<!-- 私有内容（本机路径、账号、记忆库位置、汇报口径）已剔除。 -->

"""

# 脱敏后仍不该出现的东西：盘符路径、用户目录、私有库名
LEAK_PATTERNS = (
    r"[A-Za-z]:\\\\",
    r"[A-Za-z]:\\",
    r"C:\\\\Users",
    r"\\\\knowledge",
    r"Hermes",
)


def strip_private(text):
    out, depth = [], 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == START:
            depth += 1
            continue
        if stripped == END:
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            out.append(line)
    body = "\n".join(out)
    body = re.sub(r"\n{3,}", "\n\n", body)          # 折叠被删块留下的空行
    body = re.sub(r"\n+(## )", r"\n\n\1", body)      # 小节之间统一空行
    return body.strip() + "\n"


def scan(body):
    hits = []
    for pat in LEAK_PATTERNS:
        for m in re.finditer(pat, body):
            line_no = body.count("\n", 0, m.start()) + 1
            hits.append("line %d: %r" % (line_no, body.splitlines()[line_no - 1][:100]))
            break
    return hits


def main():
    check_only = "--check" in sys.argv[1:]
    if not os.path.isfile(PRIVATE):
        sys.stderr.write("missing %s\n" % PRIVATE)
        return 2
    body = HEADER + strip_private(io.open(PRIVATE, encoding="utf-8").read())
    hits = scan(body)
    if hits:
        sys.stderr.write("脱敏失败，公开版仍含敏感片段：\n")
        for h in hits:
            sys.stderr.write("  " + h + "\n")
        sys.stderr.write("把这些内容移进 %s 块后重跑。\n" % START)
        return 1

    current = io.open(PUBLIC, encoding="utf-8").read() if os.path.isfile(PUBLIC) else None
    if check_only:
        if current == body:
            print("OK    AGENTS.public.md 与私有版一致")
            return 0
        print("DRIFT AGENTS.public.md 与私有版不一致 —— 跑一次生成器")
        return 1
    if current == body:
        print("OK    AGENTS.public.md 已是最新")
        return 0
    io.open(PUBLIC, "w", encoding="utf-8", newline="\n").write(body)
    print("WROTE %s (%d 行, %d 字节)" % (
        os.path.relpath(PUBLIC, ROOT), body.count("\n"), len(body.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
