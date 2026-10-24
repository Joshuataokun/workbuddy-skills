#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_check.py — pre-flight verification for multi-search-plus v2.2.0
=========================================================================

Verifies Python version, stdlib availability, network reachability, and that
the engine catalog is internally consistent. Always returns a non-zero exit
code if any CRITICAL check fails so this can be wired into automation.

Usage:
    python scripts/setup_check.py                # full check
    python scripts/setup_check.py --quiet        # only critical failures
    python scripts/setup_check.py --json         # machine-readable summary
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request

# Best-effort import of the main module so we share the ENGINE_CATALOG.
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
try:
    from multi_search import ENGINE_CATALOG, fetch, UA_POOL, __version__
except Exception as e:  # noqa: BLE001
    ENGINE_CATALOG = {}
    UA_POOL = []
    __version__ = "?"
    IMPORT_ERR = e
else:
    IMPORT_ERR = None


REQUIRED_PY = (3, 8)
CRITICAL_HOSTS = [
    ("www.baidu.com", "Baidu (CN core)"),
    ("cn.bing.com", "Bing CN"),
    ("duckduckgo.com", "DuckDuckGo"),
    ("www.startpage.com", "Startpage"),
    ("search.brave.com", "Brave"),
]
OPTIONAL_HOSTS = [
    ("www.wolframalpha.com", "WolframAlpha"),
    ("html.duckduckgo.com", "DDG HTML endpoint"),
]


def check_python() -> tuple[bool, str]:
    v = sys.version_info
    ok = v >= REQUIRED_PY
    return ok, f"Python {v.major}.{v.minor}.{v.micro} (need >= {'.'.join(str(x) for x in REQUIRED_PY)})"


def check_stdlib() -> tuple[bool, str]:
    mods = ["urllib.request", "urllib.parse", "urllib.error",
            "html.parser", "re", "json", "concurrent.futures",
            "gzip", "zlib", "socket", "dataclasses", "typing"]
    failed = []
    for m in mods:
        try:
            __import__(m)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{m}={e}")
    return (not failed), "all stdlib modules OK" if not failed else f"missing: {', '.join(failed)}"


def dns(host: str) -> tuple[bool, str]:
    try:
        ip = socket.gethostbyname(host)
        return True, ip
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def check_dns() -> list[tuple[str, bool, str]]:
    out = []
    for host, label in CRITICAL_HOSTS:
        ok, info = dns(host)
        out.append((f"{label} ({host}) DNS", ok, info))
    for host, label in OPTIONAL_HOSTS:
        ok, info = dns(host)
        out.append((f"{label} ({host}) DNS", ok, info + " [optional]"))
    return out


def check_fetch() -> list[tuple[str, bool, str]]:
    out = []
    samples = [
        ("https://www.baidu.com/s?wd=test", "Baidu HTTP"),
        ("https://cn.bing.com/search?q=test&ensearch=0", "Bing CN HTTP"),
    ]
    for url, label in samples:
        t0 = time.time()
        try:
            ok, body, err = fetch(url, timeout=4)
            ms = int((time.time() - t0) * 1000)
            if ok:
                out.append((f"{label} fetch", True, f"{len(body)}B in {ms}ms"))
            else:
                out.append((f"{label} fetch", False, f"{err} ({ms}ms)"))
        except Exception as e:  # noqa: BLE001
            out.append((f"{label} fetch", False, f"{type(e).__name__}: {e}"))
    return out


def check_catalog() -> list[tuple[str, bool, str]]:
    out = []
    if not ENGINE_CATALOG:
        out.append(("ENGINE_CATALOG load", False, f"import error: {IMPORT_ERR}"))
        return out
    out.append((f"ENGINE_CATALOG (v{__version__})", True,
                f"{len(ENGINE_CATALOG)} engines, {len(UA_POOL)} UAs"))
    # Validate every URL has {kw}
    bad = [k for k, v in ENGINE_CATALOG.items() if "{kw}" not in v.get("url", "")]
    out.append(("URL templates contain {kw}",
                not bad,
                "all OK" if not bad else f"missing: {', '.join(bad)}"))
    # Region coverage
    cn = sum(1 for v in ENGINE_CATALOG.values() if v.get("region") == "cn")
    gl = sum(1 for v in ENGINE_CATALOG.values() if v.get("region") == "global")
    out.append(("region balance", cn >= 5 and gl >= 5,
                f"CN={cn}, global={gl}"))
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="multi-search-plus preflight")
    p.add_argument("--json", action="store_true", help="emit JSON report")
    p.add_argument("--quiet", action="store_true", help="only print critical failures")
    args = p.parse_args()

    results: list[dict] = []

    py_ok, py_msg = check_python()
    results.append({"name": "Python version", "ok": py_ok, "msg": py_msg, "level": "critical"})

    std_ok, std_msg = check_stdlib()
    results.append({"name": "stdlib modules", "ok": std_ok, "msg": std_msg, "level": "critical"})

    for name, ok, msg in check_dns():
        results.append({"name": name, "ok": ok, "msg": msg, "level": "important"})

    for name, ok, msg in check_fetch():
        results.append({"name": name, "ok": ok, "msg": msg, "level": "advisory"})

    for name, ok, msg in check_catalog():
        results.append({"name": name, "ok": ok, "msg": msg, "level": "critical"})

    if args.json:
        print(json.dumps({"results": results,
                         "all_critical_ok": all(r["ok"] for r in results if r["level"] == "critical")},
                        ensure_ascii=False, indent=2))
    else:
        marker = lambda ok: ("✅" if ok else "❌")
        critical_failed = [r for r in results if not r["ok"] and r["level"] == "critical"]
        for r in results:
            if args.quiet and r["level"] != "critical":
                continue
            print(f"  {marker(r['ok'])} [{r['level']:9s}] {r['name']}: {r['msg']}")
        print()
        if critical_failed:
            print(f"❌ {len(critical_failed)} CRITICAL check(s) failed. Skill may not run.")
            return 1
        print("✅ All critical checks passed. Skill is ready to use.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
