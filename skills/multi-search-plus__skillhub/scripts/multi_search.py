#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
multi_search.py — Multi-Engine Aggregator Search  (multi-search-plus v2.2.0)
================================================================================

A real, runnable parallel web search across 17 engines (8 CN + 9 Global).
Pure Python 3.8+ standard library — no third-party packages required.

This script is the practical backbone of the multi-search-plus skill.
It honors rate limits, gracefully degrades single-engine failures, and never
silently drops results.

QUICK START
-----------
    python scripts/multi_search.py "site:github.com react 教程"
    python scripts/multi_search.py "AI news" --time week --json out.json
    python scripts/multi_search.py "选品" --engines baidu,bing_cn,sogou_wechat
    python scripts/multi_search.py --list-engines
    python scripts/multi_search.py --self-check

NOTES
-----
* Single-engine failure does NOT abort the whole run. Other engines continue.
* Concurrency is capped at 3 simultaneous engines; 1.5s minimum delay between
  requests to the same engine.
* Results are deduplicated by normalized URL.
* Output formats: human (default), markdown (--md), JSON (--json), or
  pipe-friendly (--tsv).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import Iterable

__version__ = "2.2.0"

# -----------------------------------------------------------------------------
# Engine Catalog
# -----------------------------------------------------------------------------

# Each engine entry maps to a URL pattern with {kw} placeholder for query.
# 'extra' is appended after keyword (e.g., time filter suffix for Google).
# 'parser' selects Result extraction strategy from PARSERS below.
# 'note' is shown in --list-engines and failure reasons.
ENGINE_CATALOG: dict[str, dict] = {
    # --- Domestic (8) ---
    "baidu":          {"url": "https://www.baidu.com/s?wd={kw}",       "region": "cn", "parser": "baidu",
                       "note": "中文索引最全，Baidu有反爬验证，频繁失败属正常"},
    "bing_cn":        {"url": "https://cn.bing.com/search?q={kw}&ensearch=0", "region": "cn", "parser": "bing",
                       "note": "必应中国版，中文结果首选"},
    "bing_int":       {"url": "https://cn.bing.com/search?q={kw}&ensearch=1", "region": "cn", "parser": "bing",
                       "note": "必应国际版，英文结果，但走中国服务器"},
    "so360":          {"url": "https://www.so.com/s?q={kw}",            "region": "cn", "parser": "generic_h3_p",
                       "note": "360搜索，安全防护内置"},
    "sogou":          {"url": "https://www.sogou.com/web?query={kw}",   "region": "cn", "parser": "generic_h3_p",
                       "note": "搜狗网页，知乎内容优化好"},
    "sogou_wechat":   {"url": "https://wx.sogou.com/weixin?type=2&query={kw}", "region": "cn", "parser": "sogou_wechat",
                       "note": "微信公众号搜索唯一渠道"},
    "toutiao":        {"url": "https://so.toutiao.com/search?keyword={kw}", "region": "cn", "parser": "generic_h3_p",
                       "note": "头条搜索，整合字节系内容"},
    "shenma":         {"url": "https://m.sm.cn/s?q={kw}",              "region": "cn", "parser": "generic_h3_p",
                       "note": "神马移动搜索，UC浏览器默认"},
    # --- International (9) ---
    "google":         {"url": "https://www.google.com/search?q={kw}{extra}", "region": "global", "parser": "google",
                       "note": "Google 主站，必要时用 google_hk 替代"},
    "google_hk":      {"url": "https://www.google.com.hk/search?q={kw}{extra}", "region": "global", "parser": "google",
                       "note": "Google HK，国内可达时优先用此"},
    "duckduckgo":     {"url": "https://html.duckduckgo.com/html/?q={kw}", "region": "global", "parser": "ddg",
                       "note": "DDG HTML版，隐私搜索，无需JS"},
    "yahoo":          {"url": "https://search.yahoo.com/search?p={kw}", "region": "global", "parser": "generic_h3_p",
                       "note": "Yahoo搜索，国际"},
    "startpage":      {"url": "https://www.startpage.com/sp/search?query={kw}", "region": "global", "parser": "generic_h3_p",
                       "note": "Startpage，Google结果+隐私保护"},
    "brave":          {"url": "https://search.brave.com/search?q={kw}", "region": "global", "parser": "brave",
                       "note": "Brave Search，独立索引"},
    "ecosia":         {"url": "https://www.ecosia.org/search?q={kw}",   "region": "global", "parser": "generic_h3_p",
                       "note": "Ecosia 环保搜索，盈利植树"},
    "qwant":          {"url": "https://www.qwant.com/?q={kw}",          "region": "global", "parser": "generic_h3_p",
                       "note": "Qwant 欧盟GDPR合规隐私搜索"},
    "wolframalpha":   {"url": "https://www.wolframalpha.com/input?i={kw}", "region": "global", "parser": "wolfram",
                       "note": "WolframAlpha 知识计算/数据查询（非网页搜索）"},
}

CN_ENGINES     = [k for k, v in ENGINE_CATALOG.items() if v["region"] == "cn"]
GLOBAL_ENGINES = [k for k, v in ENGINE_CATALOG.items() if v["region"] == "global"]
ALL_ENGINES    = list(ENGINE_CATALOG.keys())

# Time-filter suffixes appended to queries (Google style tbs).
TIME_FILTERS = {
    "hour":   "tbs=qdr:h",
    "day":    "tbs=qdr:d",
    "week":   "tbs=qdr:w",
    "month":  "tbs=qdr:m",
    "year":   "tbs=qdr:y",
}

# User-Agent rotation. Some engines (notably Baidu/Brave) gate on UA.
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

# -----------------------------------------------------------------------------
# Data Types
# -----------------------------------------------------------------------------

@dataclass
class Result:
    title: str
    url: str
    snippet: str
    source: str
    rank: int = 0

@dataclass
class EngineReport:
    engine: str
    ok: bool
    count: int = 0
    elapsed_ms: int = 0
    error: str = ""
    results: list[Result] = field(default_factory=list)

# -----------------------------------------------------------------------------
# Fetch
# -----------------------------------------------------------------------------

def fetch(url: str, *, timeout: float = 8.0, retries: int = 1) -> tuple[bool, str, str]:
    """HTTP GET with UA rotation + retries.
    Returns (ok, body_or_empty, error_message).
    """
    last_err = ""
    for attempt in range(retries + 1):
        ua = UA_POOL[attempt % len(UA_POOL)]
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                # Try to ungzip / inflate via stdlib if header indicates.
                enc = (r.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    import zlib
                    raw = zlib.decompress(raw)
                charset = r.headers.get_content_charset() or "utf-8"
                try:
                    body = raw.decode(charset, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    body = raw.decode("utf-8", errors="replace")
                if r.status >= 400:
                    last_err = f"HTTP {r.status}"
                    continue
                return True, body, ""
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {(e.read() or b'')[:120].decode('utf-8', 'replace').strip()}"
        except urllib.error.URLError as e:
            last_err = f"URLError: {e.reason}"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        time.sleep(0.6 + attempt * 0.4)  # backoff
    return False, "", last_err

# -----------------------------------------------------------------------------
# HTML Parsers — engine-specific Result extractors
# -----------------------------------------------------------------------------

# Always strip scripts/styles before pattern-matching.
_PRE_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)
_PRE_STYLE  = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)
_TAG        = re.compile(r"<[^>]+>")
_WS         = re.compile(r"\s+")
_HREF_RE    = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)


def _clean(html: str) -> str:
    html = _PRE_SCRIPT.sub(" ", html)
    html = _PRE_STYLE.sub(" ", html)
    return html


def _normalize_url(href: str, base: str = "") -> str:
    href = href.strip()
    if not href or href.startswith(("javascript:", "#", "mailto:")):
        return ""
    if href.startswith("//"):
        href = "https:" + href
    elif href.startswith("/"):
        # relative
        if base:
            href = urllib.parse.urljoin(base, href)
        else:
            return ""
    return href.split("#", 1)[0]


def _strip(text: str) -> str:
    return _WS.sub(" ", _TAG.sub("", text or "")).strip()


def _extract_link_title(block: str) -> tuple[str, str]:
    """Robustly find the FIRST anchor's href & title within a block.
    Restricts to the FIRST <a>...</a> pair so nested/unclosed tags don't bleed in.
    """
    m = re.search(r'<a\b([^>]*)>(.*?)</a>', block, flags=re.S | re.I)
    if not m:
        return "", ""
    attrs = m.group(1)
    inner = m.group(2)
    href_m = re.search(r'href\s*=\s*"([^"]+)"|href\s*=\s*\'([^\']+)\'', attrs)
    href = (href_m.group(1) or href_m.group(2)) if href_m else ""
    title = _strip(inner)
    return href.strip(), title


def parse_google(html: str, source: str, base: str) -> list[Result]:
    """Google: <div ...><a href="/url?q=..."><h3>title</h3></a>...<div ...>snippet</div>"""
    out: list[Result] = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.S | re.I):
        raw_href = m.group(1)
        inner = m.group(2)
        # Google redirect: /url?q=REAL
        if "/url?" in raw_href and "q=" in raw_href:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query).get("q", [""])[0]
            href = q
        else:
            href = raw_href
        url = _normalize_url(href, "https://www.google.com")
        if not url or "google.com" in urllib.parse.urlparse(url).netloc:
            continue
        title = _strip(inner)
        if not title or len(title) < 4 or title.lower() in {"images", "videos", "news", "maps", "shopping"}:
            continue
        # naive snippet: take next 600 chars after the </a>
        tail = html[m.end(): m.end() + 1200]
        snippet_text = _strip(tail[:600])
        # Strip query repetition from snippets
        if snippet_text.lower().startswith(title.lower()[:30]):
            snippet_text = snippet_text[len(title):].strip(" :-|")
        if not snippet_text:
            continue
        out.append(Result(title=title[:160], url=url, snippet=snippet_text[:280], source=source))
        if len(out) >= 12:
            break
    return out


def parse_bing(html: str, source: str, base: str) -> list[Result]:
    """Bing: <li class="b_algo"> ... <h2><a href="...">title</a></h2> <p>snippet</p> """
    out: list[Result] = []
    for m in re.finditer(r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>', html, flags=re.S | re.I):
        block = m.group(1)
        href, title = _extract_link_title(block)
        if not href or not title:
            continue
        url = _normalize_url(href, "https://cn.bing.com")
        p = re.search(r'<p[^>]*>(.*?)</p>', block, flags=re.S | re.I)
        snippet = _strip(p.group(1)) if p else ""
        if url and len(title) > 4:
            out.append(Result(title=title[:160], url=url, snippet=snippet[:280], source=source))
    return out[:12]


def parse_baidu(html: str, source: str, base: str) -> list[Result]:
    """Baidu: <h3 class="..."><a href="...">title</a></h3> + 摘要容器 c-abstract / content-abstract.
    Robust against nested anchors that don't close."""
    out: list[Result] = []
    for m in re.finditer(r'<h3[^>]*>(.*?)</h3>', html, flags=re.S | re.I):
        block = m.group(1)
        href, title = _extract_link_title(block)
        url = _normalize_url(href, "https://www.baidu.com")
        if not url or not title or len(title) < 4:
            continue
        # pull snippet from following ~700 chars — pick first useful paragraph
        tail = html[m.end(): m.end() + 2000]
        para = re.search(r'<(?:p|span|div)[^>]*class="[^"]*(?:c-abstract|content-right|content-abstract|c-font-normal)[^"]*"[^>]*>(.*?)(?:</(?:p|span|div)>)',
                         tail, flags=re.S | re.I)
        if para:
            snippet = _strip(para.group(1))
        else:
            snippet = _strip(tail[:600])
        if snippet and snippet.lower().startswith(title.lower()[:30]):
            snippet = snippet[len(title):].strip(" :-|")
        if not snippet:
            continue
        out.append(Result(title=title[:160], url=url, snippet=snippet[:280], source=source))
    return out[:12]


def parse_sogou_wechat(html: str, source: str, base: str) -> list[Result]:
    """Sogou WeChat: <li class="txt-box"> ... <a>title</a> <p class="txt-info">snippet</p> """
    out: list[Result] = []
    for m in re.finditer(r'<(?:li|div)[^>]*class="[^"]*txt-box[^"]*"[^>]*>(.*?)(?:</li>|</div>\s*</li>)',
                         html, flags=re.S | re.I):
        block = m.group(1)
        href, title = _extract_link_title(block)
        url = _normalize_url(href, "https://wx.sogou.com")
        p = re.search(r'<p[^>]*class="[^"]*txt-info[^"]*"[^>]*>(.*?)</p>', block, flags=re.S | re.I)
        snippet = _strip(p.group(1)) if p else ""
        if url and title and len(title) > 4:
            out.append(Result(title=title[:160], url=url, snippet=snippet[:280], source=source))
    return out[:12]


def parse_ddg(html: str, source: str, base: str) -> list[Result]:
    """DuckDuckGo HTML: <a class="result__a" href="...">title</a> + <a class="result__snippet">..."""
    out: list[Result] = []
    for m in re.finditer(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                         html, flags=re.S | re.I):
        url = _normalize_url(m.group(1), "https://html.duckduckgo.com")
        title = _strip(m.group(2))
        # snippet: next result__snippet anchor within 800 chars
        tail = html[m.end(): m.end() + 1500]
        snip = re.search(r'<(?:a|td)[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|td)>',
                         tail, flags=re.S | re.I)
        snippet = _strip(snip.group(1)) if snip else ""
        if url and title and len(title) > 3:
            out.append(Result(title=title[:160], url=url, snippet=snippet[:280], source=source))
        if len(out) >= 12:
            break
    return out


def parse_brave(html: str, source: str, base: str) -> list[Result]:
    """Brave: <div class="snippet ..."> <div class="title"><a>title</a></div> <div class="snippet-description">snippet</div>"""
    out: list[Result] = []
    for m in re.finditer(r'<div[^>]*class="[^"]*snippet[^"]*"[^>]*>(.*?)(?=<div[^>]*class="[^"]*snippet|\Z)',
                         html, flags=re.S | re.I):
        block = m.group(1)
        a = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.S | re.I)
        if not a:
            continue
        url = _normalize_url(a.group(1), "https://search.brave.com")
        title = _strip(a.group(2))
        if title.lower() in {"videos", "images", "news"} or len(title) < 4:
            continue
        snip = re.search(r'<div[^>]*class="[^"]*snippet-description[^"]*"[^>]*>(.*?)</div>',
                         block, flags=re.S | re.I)
        snippet = _strip(snip.group(1)) if snip else ""
        if url and title:
            out.append(Result(title=title[:160], url=url, snippet=snippet[:280], source=source))
        if len(out) >= 12:
            break
    return out


def parse_generic_h3_p(html: str, source: str, base: str) -> list[Result]:
    """Generic fallback: scan <h3> or strong-styled anchors + following <p>."""
    out: list[Result] = []
    seen_urls: set[str] = set()
    for m in re.finditer(r'<h[1-6][^>]*>(.*?)</h[1-6]>', html, flags=re.S | re.I):
        inner = m.group(1)
        href, title = _extract_link_title(inner)
        if not href or not title:
            continue
        url = _normalize_url(href, base)
        if not url or url in seen_urls:
            continue
        if len(title) < 4:
            continue
        if title.lower() in {"home", "about", "contact", "login", "sign in", "register"}:
            continue
        tail = html[m.end(): m.end() + 1200]
        p = re.search(r'<p[^>]*>(.*?)</p>', tail, flags=re.S | re.I)
        snippet = _strip(p.group(1)) if p else _strip(tail[:400])
        if not snippet:
            continue
        seen_urls.add(url)
        out.append(Result(title=title[:160], url=url, snippet=snippet[:280], source=source))
        if len(out) >= 12:
            break
    return out


def parse_wolfram(html: str, source: str, base: str) -> list[Result]:
    """WolframAlpha: typically renders to a JS-driven page; we capture the query echo + section titles only."""
    out: list[Result] = []
    # Look for the input field value
    iv = re.search(r'<input[^>]+id="[^"]*i[_-]?[^"]*"[^>]+value="([^"]+)"', html)
    if iv:
        query = _strip(iv.group(1))
        if query:
            out.append(Result(
                title=f"WolframAlpha query: {query[:60]}",
                url=f"https://www.wolframalpha.com/input?i={urllib.parse.quote(query)}",
                snippet="WolframAlpha results render via JavaScript. For full content, use web_fetch on the result URL or visit in a browser.",
                source=source,
            ))
    # Capture section blob titles (Pod headers)
    for m in re.finditer(r'<h2[^>]*class="[^"]*pod[_-]?title[^"]*"[^>]*>(.*?)</h2>', html, flags=re.S | re.I):
        title = _strip(m.group(1))
        if title:
            out.append(Result(
                title=f"WA section: {title[:80]}",
                url=f"https://www.wolframalpha.com/input?i={urllib.parse.quote(_strip(re.search(r'name=\"i\"|value=\"([^\"]+)\"', html[:5000]).group(1) if re.search(r'name=\"i\"|value=\"([^\"]+)\"', html[:5000]) else ''))}",
                snippet="(rendered client-side; consult URL for full answer)",
                source=source,
            ))
        if len(out) >= 8:
            break
    return out[:8]


PARSERS = {
    "baidu": parse_baidu,
    "bing":  parse_bing,
    "google": parse_google,
    "ddg":   parse_ddg,
    "brave": parse_brave,
    "sogou_wechat": parse_sogou_wechat,
    "wolfram": parse_wolfram,
    "generic_h3_p": parse_generic_h3_p,
}

# -----------------------------------------------------------------------------
# Search Logic
# -----------------------------------------------------------------------------

def search_engine(engine: str, query: str, *, time_filter: str = "", top: int = 8, timeout: float = 8.0) -> EngineReport:
    if engine not in ENGINE_CATALOG:
        return EngineReport(engine=engine, ok=False, error="unknown engine")
    cfg = ENGINE_CATALOG[engine]
    extra = ""
    if engine in {"google", "google_hk"} and time_filter and time_filter in TIME_FILTERS:
        extra = "&" + TIME_FILTERS[time_filter]
    encoded_kw = urllib.parse.quote(query, safe="")
    url = cfg["url"].format(kw=encoded_kw) + extra
    t0 = time.time()
    ok, html_body, err = fetch(url, timeout=timeout, retries=1)
    elapsed = int((time.time() - t0) * 1000)
    if not ok:
        return EngineReport(engine=engine, ok=False, error=err, elapsed_ms=elapsed)
    html_body = _clean(html_body)
    parser_fn = PARSERS.get(cfg["parser"]) or parse_generic_h3_p
    try:
        results = parser_fn(html_body, engine, urllib.parse.urlparse(url).netloc)
    except Exception as e:  # noqa: BLE001
        return EngineReport(engine=engine, ok=False, error=f"parser error: {e}", elapsed_ms=elapsed)
    for i, r in enumerate(results[:top], 1):
        r.rank = i
    return EngineReport(engine=engine, ok=True, count=len(results[:top]), results=results[:top], elapsed_ms=elapsed)


def dedup(results: list[Result]) -> list[Result]:
    """URL-based dedup, normalize trailing slash & tracking params."""
    def norm(u: str) -> str:
        try:
            p = urllib.parse.urlparse(u)
            host = p.netloc.lower().replace("www.", "")
            # strip aggressive tracking
            q = "&".join(sorted(k for k in (p.query or "").split("&")
                                if not k.startswith(("utm_", "fbclid=", "gclid=", "ref=", "ref_src="))))
            return f"{p.scheme}://{host}{p.path}".rstrip("/") + (f"?{q}" if q else "")
        except Exception:
            return u
    seen: dict[str, Result] = {}
    for r in results:
        key = norm(r.url)
        if not key or key in seen:
            continue
        seen[key] = r
    return list(seen.values())


def aggregate(reports: list[EngineReport]) -> list[Result]:
    flat: list[Result] = []
    for rep in reports:
        flat.extend(rep.results)
    return dedup(flat)


# -----------------------------------------------------------------------------
# Output
# -----------------------------------------------------------------------------

def render_human(reports: list[EngineReport], merged: list[Result], query: str, elapsed_total: float) -> str:
    lines: list[str] = []
    lines.append(f"# Multi-Engine Search Results")
    lines.append(f"**Query**: {query}")
    lines.append(f"**Engines**: {len(reports)} (succeeded={sum(1 for r in reports if r.ok)})")
    lines.append(f"**Elapsed**: {elapsed_total:.2f}s")
    lines.append(f"**Total unique results**: {len(merged)}")
    lines.append("")
    if not merged:
        lines.append("(No results extracted. Engines may be blocking automated requests. Try `web_fetch` for a single-engine probe.)")
        return "\n".join(lines)
    lines.append("## Deduplicated Top Results")
    for i, r in enumerate(merged[:30], 1):
        lines.append(f"{i}. **[{r.title}]({r.url})**")
        if r.snippet:
            lines.append(f"   {r.snippet[:240]}")
        lines.append(f"   _source: {r.source}_")
        lines.append("")
    lines.append("## Per-Engine Status")
    for rep in sorted(reports, key=lambda x: (not x.ok, x.engine)):
        marker = "✅" if rep.ok else "❌"
        if rep.ok:
            lines.append(f"- {marker} **{rep.engine}** — {rep.count} results, {rep.elapsed_ms}ms")
        else:
            err = (rep.error or "unknown")[:80]
            lines.append(f"- {marker} **{rep.engine}** — {err}")
    return "\n".join(lines)


def render_markdown(reports: list[EngineReport], merged: list[Result], query: str, elapsed_total: float) -> str:
    return render_human(reports, merged, query, elapsed_total)  # same format works


def render_json(reports: list[EngineReport], merged: list[Result], query: str, elapsed_total: float) -> str:
    payload = {
        "version": __version__,
        "query": query,
        "elapsed_total_s": round(elapsed_total, 2),
        "engines_total": len(reports),
        "engines_ok": sum(1 for r in reports if r.ok),
        "unique_results": len(merged),
        "results": [asdict(r) for r in merged],
        "engine_reports": [
            {k: v for k, v in asdict(rep).items() if k != "results"} | {"results": [asdict(r) for r in rep.results]}
            for rep in reports
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_tsv(merged: list[Result]) -> str:
    out = ["source\ttitle\turl\tsnippet"]
    for r in merged:
        out.append(f"{r.source}\t{r.title}\t{r.url}\t{r.snippet[:240]}")
    return "\n".join(out)


# -----------------------------------------------------------------------------
# Orchestration
# -----------------------------------------------------------------------------

def run(query: str, *, engines: list[str], time_filter: str = "", top: int = 8,
        max_workers: int = 3, per_request_delay: float = 1.5, timeout: float = 8.0,
        fmt: str = "human") -> tuple[list[EngineReport], list[Result], float]:
    if not engines:
        engines = ALL_ENGINES
    # Per-engine throttle: keep ≥ per_request_delay between launches.
    # We rely on ThreadPoolExecutor's BoundedSemaphore style via submit pacing.
    pool = ThreadPoolExecutor(max_workers=max_workers)
    futures = {}
    schedule: dict[str, float] = {}
    t0 = time.time()

    def schedule_launch(eng: str):
        last = schedule.get(eng, 0)
        wait = max(0.0, per_request_delay - (time.time() - last))
        if wait:
            time.sleep(wait)
        schedule[eng] = time.time()
        return pool.submit(search_engine, eng, query,
                           time_filter=time_filter, top=top, timeout=timeout)

    try:
        for eng in engines:
            futures[schedule_launch(eng)] = eng
        reports: list[EngineReport] = []
        for fut in as_completed(futures):
            try:
                rep = fut.result()
            except Exception as e:  # noqa: BLE001
                rep = EngineReport(engine=futures[fut], ok=False, error=f"worker error: {e}")
            reports.append(rep)
    finally:
        pool.shutdown(wait=True)
    elapsed = time.time() - t0
    merged = aggregate(reports)
    return reports, merged, elapsed


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def _parse_engines_arg(arg: str) -> list[str]:
    if arg.lower() in {"cn", "domestic", "china"}:
        return list(CN_ENGINES)
    if arg.lower() in {"global", "intl", "international"}:
        return list(GLOBAL_ENGINES)
    if arg.lower() in {"all", "*"}:
        return list(ALL_ENGINES)
    parts = [p.strip() for p in arg.split(",") if p.strip()]
    bad = [p for p in parts if p not in ENGINE_CATALOG]
    if bad:
        sys.stderr.write(f"warning: unknown engine(s) ignored: {', '.join(bad)}\n"
                         f"        available: {', '.join(ALL_ENGINES)}\n")
    return [p for p in parts if p in ENGINE_CATALOG]


def cli():
    p = argparse.ArgumentParser(
        prog="multi_search",
        description="Multi-Engine Aggregator Search (multi-search-plus v" + __version__ + ")",
    )
    p.add_argument("query", nargs="?", help="Search query (operators: site:, filetype:, inurl:, intitle:, \"exact\", -exclude)")
    p.add_argument("--engines", "-e", default="all",
                   help="Comma-separated engines, or 'cn', 'global', 'all' (default)")
    p.add_argument("--time", choices=list(TIME_FILTERS) + [""], default="",
                   help="Google-style time filter (Google/Google HK only)")
    p.add_argument("--top", type=int, default=8, help="Results per engine (default 8)")
    p.add_argument("--max-workers", type=int, default=3, help="Concurrent engine calls (default 3)")
    p.add_argument("--delay", type=float, default=1.5, help="Seconds between per-engine launches (default 1.5)")
    p.add_argument("--timeout", type=float, default=8.0, help="Per-request timeout seconds (default 8)")
    p.add_argument("--md", action="store_true", help="Markdown output (default human)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--tsv", action="store_true", help="TSV output (one row per result)")
    p.add_argument("--list-engines", action="store_true", help="List all available engines and exit")
    p.add_argument("--self-check", action="store_true", help="Run pre-flight checks and exit")
    p.add_argument("--quiet", action="store_true", help="Suppress per-engine stderr warnings")
    args = p.parse_args()

    if args.list_engines:
        print(f"multi-search-plus v{__version__}\nEngine catalog:")
        print(f"\n  Domestic ({len(CN_ENGINES)}):")
        for e in CN_ENGINES:
            print(f"    - {e:<16} {ENGINE_CATALOG[e]['note']}")
        print(f"\n  Global ({len(GLOBAL_ENGINES)}):")
        for e in GLOBAL_ENGINES:
            print(f"    - {e:<16} {ENGINE_CATALOG[e]['note']}")
        return 0

    if args.self_check:
        return _self_check()

    if not args.query:
        p.error("query is required (or use --list-engines / --self-check)")

    engines = _parse_engines_arg(args.engines)
    if not engines:
        sys.stderr.write("error: no valid engines selected\n")
        return 2

    reports, merged, elapsed = run(
        args.query,
        engines=engines,
        time_filter=args.time or "",
        top=max(1, args.top),
        max_workers=max(1, args.max_workers),
        per_request_delay=max(0.0, args.delay),
        timeout=max(1.0, args.timeout),
        fmt="json" if args.json else ("tsv" if args.tsv else ("md" if args.md else "human")),
    )

    if args.json:
        print(render_json(reports, merged, args.query, elapsed))
    elif args.tsv:
        print(render_tsv(merged))
    else:
        print(render_human(reports, merged, args.query, elapsed))

    # non-zero exit if every engine failed
    return 0 if any(r.ok for r in reports) or merged else 1


def _self_check() -> int:
    """Pre-flight: Python version, stdlib availability, basic DNS / connectivity."""
    import socket
    print(f"multi-search-plus v{__version__} self-check")
    print(f"  Python: {sys.version.split()[0]} (need ≥3.8)")
    checks = []
    try:
        socket.gethostbyname("www.baidu.com")
        checks.append(("DNS resolve baidu", "OK"))
    except Exception as e:
        checks.append(("DNS resolve baidu", f"FAIL {e}"))
    try:
        import gzip, zlib, concurrent.futures  # noqa: F401
        checks.append(("stdlib modules", "OK"))
    except Exception as e:
        checks.append(("stdlib modules", f"FAIL {e}"))
    try:
        ok, _, err = fetch("https://www.baidu.com/s?wd=test", timeout=4)
        checks.append(("Baidu connectivity", "OK" if ok else f"FAIL {err}"))
    except Exception as e:
        checks.append(("Baidu connectivity", f"FAIL {e}"))
    for name, status in checks:
        marker = "✅" if status.startswith("OK") else "❌"
        print(f"  {marker} {name}: {status}")
    print()
    print(f"  Engines catalog: {len(ENGINE_CATALOG)} total, {len(CN_ENGINES)} CN, {len(GLOBAL_ENGINES)} global")
    print(f"  User-Agent pool: {len(UA_POOL)} entries")
    return 0 if all(c[1].startswith("OK") for c in checks) else 1


if __name__ == "__main__":
    sys.exit(cli())
