#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_search.py — read multiple queries, run them through multi_search in turn
===============================================================================

Reads one query per line (stdin or --file), runs each through the
multi_search aggregator, and emits a combined Markdown / JSON report.

Useful for: cross-product price checks, weekly news sweep, multi-domain
research, niche-specific fan-out queries.

Usage:
    python scripts/batch_search.py --file queries.txt --md
    cat queries.txt | python scripts/batch_search.py --json out.json
    python scripts/batch_search.py --inline "AI 教程" "跨境电商运营" "Python 学习"
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from multi_search import run, render_human, render_json, ALL_ENGINES, CN_ENGINES, GLOBAL_ENGINES, __version__
except Exception as e:  # noqa: BLE001
    print(f"error: cannot import multi_search: {e}", file=sys.stderr)
    sys.exit(2)


def parse_engines(spec: str) -> list[str]:
    s = spec.strip().lower()
    if s in {"all", "*"}:
        return list(ALL_ENGINES)
    if s in {"cn", "domestic"}:
        return list(CN_ENGINES)
    if s in {"global", "intl"}:
        return list(GLOBAL_ENGINES)
    return [x.strip() for x in s.split(",") if x.strip()]


def main() -> int:
    p = argparse.ArgumentParser(description="multi-search-plus batch runner")
    p.add_argument("--file", help="input file (one query per line; # comments)")
    p.add_argument("--inline", nargs="+", help="queries on the command line")
    p.add_argument("--engines", "-e", default="cn", help="cn | global | all | comma list")
    p.add_argument("--top", type=int, default=4, help="results per engine per query")
    p.add_argument("--delay", type=float, default=1.5, help="seconds between per-engine launches")
    p.add_argument("--md", action="store_true", help="emit combined Markdown report")
    p.add_argument("--json", help="write JSON report to file")
    args = p.parse_args()

    queries: list[str] = []
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            queries.extend(line.strip() for line in f if line.strip() and not line.startswith("#"))
    if args.inline:
        queries.extend(args.inline)
    if not queries:
        if not sys.stdin.isatty():
            queries.extend(line.strip() for line in sys.stdin if line.strip() and not line.startswith("#"))
    if not queries:
        p.error("no queries provided (use --file / --inline / stdin)")

    engines = parse_engines(args.engines)
    sections: list[dict] = []

    for q in queries:
        reports, merged, elapsed = run(q, engines=engines, top=args.top, per_request_delay=args.delay)
        sections.append({
            "query": q,
            "elapsed_s": round(elapsed, 2),
            "engines_total": len(reports),
            "engines_ok": sum(1 for r in reports if r.ok),
            "unique_results": len(merged),
            "results": [r.__dict__ for r in merged[:20]],
        })
        # gentle pacing between queries
        if q is not queries[-1]:
            import time
            time.sleep(2.0)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"version": __version__, "queries": sections}, f, ensure_ascii=False, indent=2)
        print(f"wrote {args.json} ({len(sections)} queries, {sum(s['unique_results'] for s in sections)} results)")
        return 0

    if args.md or not args.json:
        out: list[str] = []
        out.append(f"# Batch Search Report  (multi-search-plus v{__version__})")
        out.append(f"**Queries**: {len(sections)}  |  **Engines**: {len(engines)} ({engines[:3]}{'…' if len(engines) > 3 else ''})")
        out.append("")
        for s in sections:
            out.append(f"## Query: {s['query']}")
            out.append(f"_{s['engines_ok']}/{s['engines_total']} engines succeeded, {s['unique_results']} unique results, {s['elapsed_s']}s_")
            out.append("")
            for i, r in enumerate(s["results"], 1):
                snippet = r["snippet"][:220].replace("\n", " ")
                out.append(f"{i}. **[{r['title']}]({r['url']})**")
                if snippet:
                    out.append(f"   {snippet}")
                out.append(f"   _source: {r['source']}_")
                out.append("")
        print("\n".join(out))
        return 0


if __name__ == "__main__":
    sys.exit(main())
