#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deai_check.py —— 简体中文「AI 味」离线检测与打分。

架构与 Office 文件抽取逻辑移植自 sloptrim (Apache-2.0,
https://github.com/seyedehsanhadi/sloptrim)，规则库为简体中文重写。
只用标准库，不联网，不调模型。

用法:
    python deai_check.py 文件.md
    python deai_check.py 汇报.pptx          # 文字 + 版式双通道
    python deai_check.py - --json < a.txt
    python deai_check.py 稿.txt --min 30     # 自定义上报阈值

退出码: 0 通过（score <= min），1 超阈值，2 参数/读取错误。
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys

# ----------------------------------------------------------------- 阈值常量
MIN_WORDS = 120          # 低于此字数，结论降为「样本不足」
CONTENT_CAP = 48.0       # 内容族得分上限
RHYTHM_CAP = 18.0        # 节奏得分上限
VOCAB_CAP = 26.0         # 词表得分上限
VOCAB_FLOOR = 12.0       # 词表密度免罚线（每千字）
MAX_SAMPLES = 3
ZIP_MEMBER_CAP = 32 * 1024 * 1024

BANDS = ((20, "干净"), (40, "轻微"), (60, "明显"), (80, "偏重"), (100, "重度"))


def band(score: float) -> str:
    for limit, name in BANDS:
        if score <= limit:
            return name
    return "重度"


# =============================================================== 一、内容真实
RE_INFLATE = re.compile(
    r"标志着|里程碑|新的篇章|翻开.{0,6}新|具有(?:重要|深远|重大|战略)意义|"
    r"注入.{0,4}(?:新)?(?:动能|活力)|书写.{0,6}新|树立了.{0,4}标杆|"
    r"为.{0,10}提供(?:了)?(?:有力|坚实|强有力)(?:支撑|保障|支撑)|"
    r"奠定(?:了)?(?:坚实|重要)?基础|开创(?:了)?(?:新)?(?:局面|纪元)|"
    r"在.{0,8}(?:背景|形势|大潮)下|随着.{0,10}(?:的)?(?:发展|推进|深入)|"
    r"顺应.{0,8}趋势|把握.{0,6}(?:机遇|大势)"
)
RE_VAGUE_SRC = re.compile(
    r"业内人士|有关(?:方面|部门|专家)|研究表明|研究显示|数据显示(?![:：])|"
    r"专家(?:指出|表示|认为|建议)|普遍认为|众所周知|业内公认|"
    r"有(?:关|分析)人士|据(?:了解|悉)(?![^。]{0,10}[0-9])"
)
RE_GENERIC = re.compile(
    r"相关(?:领域|部门|工作|方面)|广泛(?:关注|影响|认可|好评)|"
    r"某种(?:意义|程度)上|各类(?:场景|主体)|在一定程度上|"
    r"存在(?:一定)?(?:联系|关联|关系)|发挥(?:了)?(?:积极|重要)作用"
)
RE_FALSE_BALANCE = re.compile(
    r"既要.{0,20}又要|一方面.{0,40}另一方面|虽然.{0,30}但是.{0,30}(?:值得|可期)|"
    r"尽管.{0,30}(?:挑战|困难).{0,30}(?:仍|依然|继续)"
)
RE_UPBEAT_END = re.compile(
    r"(?:未来|前景)(?:可期|广阔|光明|值得期待)|"
    r"迈上(?:新)?台阶|再上(?:新)?台阶|续写.{0,8}篇章|"
    r"必将.{0,20}(?:实现|取得|开创)|让我们(?:共同|一起)?(?:努力|期待)"
)
RE_JARGON = re.compile(
    r"赋能|抓手|闭环|底座|打通(?:了)?(?:最后|全链)|沉淀(?:了)?(?:方法|能力|经验)|"
    r"对齐(?:了)?(?:目标|认知)|形成(?:合力|闭环)|"
    r"提质增效|降本增效|高质量发展|新质生产力|"
    r"顶层设计|系统谋划|统筹推进|一体推进|"
    r"颗粒度|组合拳|护城河|天花板|分水岭|主战场|有了牙齿"
)

# =============================================================== 二、修辞骨架
RE_NOT_X_BUT_Y = re.compile(
    r"不是[^。！？；\n]{1,25}?而是|并非[^。！？；\n]{1,25}?而是|"
    r"不在于[^。！？；\n]{1,25}?而在于|"
    r"与其说[^。！？；\n]{1,20}?不如说"
)
RE_NOT_ONLY = re.compile(r"不仅[^。！？；\n]{1,30}?(?:更|还|也)[^。！？；\n]{1,30}")
RE_FALSE_RANGE = re.compile(
    r"从[^。！？；\n，]{2,12}到[^。！？；\n，]{2,12}(?:再到|，再到)|"
    r"从[^。！？；\n，]{2,12}(?:走向|迈向|跃向)"
)
RE_FAUX_DEPTH = re.compile(
    r"看似[^。！？；\n]{1,20}(?:实则|其实|本质)|表面(?:上)?[^。！？；\n]{1,20}背后|"
    r"真正的[^。！？；\n]{1,10}(?:是|在于)|(?:这|其)背后(?:是|的逻辑)"
)
RE_ORDINAL = re.compile(
    r"(?:^|[。！？；\n])\s*(?:首先|其次|再次|最后|第一|第二|第三)[，,、]"
)
RE_TRANSITION = re.compile(
    r"(?:^|[。！？；\n])\s*(?:然而|此外|因此|同时|另外|总之|综上|由此可见)[，,]"
)
RE_DASH = re.compile(r"[—–]{1,2}|——")
RE_TRIAD = re.compile(
    r"([^，。！？；、\n]{2,6})、([^，。！？；、\n]{2,6})[，、](?:和|与|及|以及)?"
    r"([^，。！？；、\n]{2,6})(?=[，。！？；\n])"
)

# =============================================================== 三、句法语序
RE_PREP_STACK = re.compile(
    r"^(?:在[^，。]{4,30}?[中上下里]|随着[^，。]{4,30}|基于[^，。]{4,30}|"
    r"围绕[^，。]{4,30}|按照[^，。]{4,30}|根据[^，。]{4,30})[，,]"
)
RE_PASSIVE_CN = re.compile(r"被[^。！？；\n]{1,15}?(?:所)?(?:进行|加以|予以|实施|推进|完成)")
RE_LONG_ATTR = re.compile(r"(?:[^，。！？；、\n]{1,12}的){3,}")
RE_NOUNIFY = re.compile(
    r"(?:进行|实现|推动|构建|开展|加强|推进|做好|抓好)(?:了)?"
    r"(?:[^。！？；\n]{0,6})?(?:工作|建设|管理|提升|优化|落实|部署)"
)
RE_XINGHUA = re.compile(r"(?:[^\s，。]{1,4}[性化])(?:[^\s，。]{1,4}[性化]){1,}")
RE_HEDGE_STACK = re.compile(
    r"(?:可能|或许|也许|大概|一定程度上|相对|基本上|总体看|大体上)"
    r"(?:[^。！？；\n]{0,8}?)(?:可能|或许|也许|大概|一定程度上|相对)"
)
RE_FILLER = re.compile(
    r"值得注意的是|需要指出的是|不可否认|毋庸置疑|显而易见|"
    r"众所周知|说白了|说白了就是|换句话说|也就是说|"
    r"为了更好地|为了进一步|在此基础上|在此过程中"
)

# =============================================================== 四、词汇
AI_VOCAB = (
    "赋能", "助力", "打造", "构建", "深化", "推动", "强化", "优化", "提升",
    "聚焦", "锚定", "对标", "贯通", "全方位", "多维度", "深层次", "系统性",
    "整体性", "协同性", "精准", "高效", "扎实", "有力", "有序", "稳步",
    "持续", "不断", "进一步", "切实", "着力", "突出", "彰显", "赋能于",
    "新高度", "新台阶", "新格局", "新篇章", "新动能", "新优势",
)
VOCAB_RE = re.compile("|".join(re.escape(w) for w in AI_VOCAB))

RE_SYNONYM_CYCLE = re.compile(
    r"(?:工作|任务|项目|工程)[^。]{0,15}(?:工作|任务|项目|工程)|"
    r"(?:问题|短板|不足|弱项)[^。]{0,15}(?:问题|短板|不足|弱项)"
)

# =============================================================== 五、格式残留
RE_BOLD = re.compile(r"\*\*[^*\n]{1,60}\*\*")
RE_INLINE_HEAD = re.compile(r"(?:^|\n)\s*[-*\d.、]*\s*\*\*[^*\n:：]{1,20}(?:[:：]\*\*|\*\*\s*[:：])")
RE_EMOJI = re.compile(
    "[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]"
)
RE_CHAT = re.compile(
    r"希望(?:以上|这|本)(?:内容|回答|说明)?(?:对你|能|可以)?(?:有所)?帮助|"
    r"如需(?:要)?(?:进一步|更多)|请(?:随时)?告知|"
    r"以下是(?:关于|一份|内容)|下面是(?:关于|一份)|"
    r"当然可以|当然！|好的[，,！!]|让我们(?:来|一起)"
)
RE_CUTOFF = re.compile(
    r"截至(?:我)?(?:的)?(?:知识|训练)(?:截止|更新)|"
    r"根据(?:我)?(?:所)?(?:掌握的|现有的|可获得的)信息|"
    r"由于(?:资料|信息)(?:有限|不足)"
)
RE_PLACEHOLDER = re.compile(
    r"\[(?:姓名|公司|日期|待填|待补|XX|xxx)\]|待补(?:充)?|"
    r"(?<![A-Za-z0-9])X{2,}(?![A-Za-z0-9])|TBD|TODO"
)
RE_STRAIGHT_QUOTE_IN_CN = re.compile(r'"[^"\n]{1,60}"')
RE_TITLE_SLOGAN = re.compile(
    r"以[^，。\n]{1,6}促[^，。\n]{1,6}|"
    r"[^，。\n]{1,8}为[^，。\n]{1,6}[，,][^，。\n]{1,8}为[^，。\n]{1,6}|"
    r"[^，。\n]{2,8}·[^，。\n]{2,8}|"
    r"^(?:[^，。\n]{4,10})[，,](?:[^，。\n]{4,10})$"
)

# =============================================================== 六、节奏指标
SENT_SPLIT = re.compile(r"[。！？；!?;\n]+")


def split_sentences(text: str) -> list:
    parts = [s.strip() for s in SENT_SPLIT.split(text)]
    return [s for s in parts if len(s) >= 2]


def count_words(text: str) -> int:
    """中文按字计，英文按词计。"""
    cn = len(re.findall(r"[\u4e00-\u9fff]", text))
    en = len(re.findall(r"[A-Za-z]+", text))
    return cn + en


def cv(values: list) -> float | None:
    if len(values) < 3:
        return None
    mean = statistics.fmean(values)
    if mean <= 0:
        return None
    return statistics.pstdev(values) / mean


def samples(text: str, pattern, k: int = MAX_SAMPLES) -> list:
    out = []
    for m in pattern.finditer(text):
        frag = m.group(0).strip().strip("。！？；，、\n 　")
        if frag and frag not in out:
            out.append(frag)
        if len(out) >= k:
            break
    return out


# =============================================================== 规则表
# (id, 族, 名称, 正则, 是否决定性)
RULES = [
    # --- A 内容真实性
    ("A1", "A", "无证据拔高", RE_INFLATE, True),
    ("A2", "A", "模糊归因", RE_VAGUE_SRC, True),
    ("A3", "A", "泛化无细节", RE_GENERIC, False),
    ("A4", "A", "假平衡与未来可期", RE_FALSE_BALANCE, True),
    ("A5", "A", "空转收尾", RE_UPBEAT_END, True),
    ("A6", "A", "空泛行话", RE_JARGON, True),
    # --- B 修辞骨架
    ("B1", "B", "不是X而是Y", RE_NOT_X_BUT_Y, True),
    ("B2", "B", "不仅X更Y", RE_NOT_ONLY, False),
    ("B3", "B", "从X到Y假范围", RE_FALSE_RANGE, False),
    ("B4", "B", "看似实则假揭示", RE_FAUX_DEPTH, True),
    ("B5", "B", "序数骨架", RE_ORDINAL, False),
    ("B6", "B", "连接词链", RE_TRANSITION, False),
    ("B7", "B", "破折号连缀", RE_DASH, False),
    ("B8", "B", "三连排比", RE_TRIAD, False),
    # --- C 句法语序
    ("C1", "C", "前置状语堆叠", RE_PREP_STACK, False),
    ("C2", "C", "翻译式被动", RE_PASSIVE_CN, False),
    ("C3", "C", "定语链过长", RE_LONG_ATTR, False),
    ("C4", "C", "抽象名词化", RE_NOUNIFY, False),
    ("C5", "C", "性化堆叠", RE_XINGHUA, False),
    ("C6", "C", "限定词串联", RE_HEDGE_STACK, False),
    ("C7", "C", "填充句", RE_FILLER, False),
    # --- D 词汇
    ("D1", "D", "AI 高频词", VOCAB_RE, False),
    ("D2", "D", "同义反复", RE_SYNONYM_CYCLE, False),
    # --- E 格式残留
    ("E1", "E", "粗体装饰", RE_BOLD, False),
    ("E2", "E", "行内标题列表", RE_INLINE_HEAD, False),
    ("E3", "E", "表情符号", RE_EMOJI, False),
    ("E4", "E", "聊天残留", RE_CHAT, True),
    ("E5", "E", "知识截止声明", RE_CUTOFF, True),
    ("E6", "E", "占位符未填", RE_PLACEHOLDER, True),
    ("E7", "E", "中文里用英文直引号", RE_STRAIGHT_QUOTE_IN_CN, False),
]

DECISIVE = {rid for rid, _, _, _, d in RULES if d}
STRONG = {"A1", "A4", "B1", "B4", "C1"}


def scan_text(text: str) -> dict:
    found = {}
    for rid, fam, name, pat, _ in RULES:
        hits = pat.findall(text) if hasattr(pat, "findall") else []
        count = len(hits)
        if not count:
            continue
        found[rid] = {
            "族": fam,
            "名称": name,
            "次数": count,
            "样例": samples(text, pat),
        }
    return found


def score_text(text: str, found: dict) -> dict:
    words = max(count_words(text), 1)
    eff = max(words, MIN_WORDS)

    diversity = 0.0
    load = 0.0
    seen_fam = set()
    for rid, info in found.items():
        cnt = min(info["次数"], 5)
        load += cnt
        fam = info["族"]
        if fam in seen_fam:
            continue
        seen_fam.add(fam)
        if rid in DECISIVE:
            diversity += 16.0
        elif rid in STRONG:
            diversity += 10.0
        else:
            diversity += 2.5
    content_term = min(CONTENT_CAP, diversity + min(10.0, load / eff * 1000))

    sents = split_sentences(text)
    lens = [len(s) for s in sents]
    scv = cv(lens)
    rhythm = 0.0
    if scv is not None and scv < 0.45:
        rhythm += (0.45 - scv) / 0.45 * 10.0
    paras = [p for p in text.split("\n") if p.strip()]
    pcv = cv([len(p) for p in paras])
    if pcv is not None and pcv < 0.40:
        rhythm += (0.40 - pcv) / 0.40 * 8.0
    rhythm_term = min(RHYTHM_CAP, rhythm)

    vocab_count = found.get("D1", {}).get("次数", 0)
    rate = vocab_count / eff * 1000
    vocab_term = min(VOCAB_CAP, max(0.0, rate - VOCAB_FLOOR) * 0.45)

    score = round(min(100.0, content_term + rhythm_term + vocab_term))

    decisive_hits = {r for r in found if r in DECISIVE}
    fams = {v["族"] for v in found.values()}
    if len(decisive_hits) >= 2:
        score = max(score, 65)
    elif len(decisive_hits) == 1 and words >= MIN_WORDS:
        score = max(score, 45)
    if words < MIN_WORDS:
        confidence = "低（样本不足）"
        if len(fams) >= 3:
            score = max(score, 45)
        elif len(fams) >= 2:
            score = max(score, 25)
    elif words >= 400:
        confidence = "正常"
        if len(fams) >= 6:
            score = max(score, 45)
        elif len(fams) >= 5:
            score = max(score, 25)
    else:
        confidence = "正常"

    return {
        "score": int(min(100, score)),
        "band": band(score),
        "confidence": confidence,
        "metrics": {
            "字数": words,
            "句数": len(sents),
            "句长变异": round(scv, 3) if scv is not None else None,
            "段长变异": round(pcv, 3) if pcv is not None else None,
            "AI词密度_每千字": round(rate, 1),
        },
    }


# =============================================================== PPT 版式通道
NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
NS_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def _slide_shapes(blob: bytes) -> list:
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(blob)
    except ET.ParseError:
        return []
    out = []
    for sp in root.iter():
        if sp.tag not in (NS_P + "sp", NS_P + "graphicFrame"):
            continue
        xfrm = None
        for el in sp.iter():
            if el.tag == NS_A + "xfrm":
                xfrm = el
                break
        if xfrm is None:
            continue
        off = xfrm.find(NS_A + "off")
        ext = xfrm.find(NS_A + "ext")
        text = "".join(t.text or "" for t in sp.iter(NS_A + "t")).strip()
        if not text:
            continue
        try:
            x = int(off.get("x", 0))
            y = int(off.get("y", 0))
            w = int(ext.get("cx", 0))
            h = int(ext.get("cy", 0))
        except (AttributeError, TypeError, ValueError):
            continue
        out.append({"x": x, "y": y, "w": w, "h": h, "text": text})
    return out


def _slide_size(z) -> tuple:
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(z.read("ppt/presentation.xml"))
    except (KeyError, ET.ParseError):
        return (9144000, 6858000)
    for el in root.iter():
        if el.tag == NS_P + "sldSz":
            try:
                return (int(el.get("cx")), int(el.get("cy")))
            except (TypeError, ValueError):
                break
    return (9144000, 6858000)


def check_pptx(path: str) -> dict:
    """版式通道：判阅读方向是否单一、单页信息量是否超载。"""
    import zipfile

    findings = []
    with zipfile.ZipFile(path) as z:
        slide_w, slide_h = _slide_size(z)
        names = [n for n in z.namelist()
                 if re.match(r"ppt/slides/slide\d+\.xml$", n)]
        names.sort(key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)))
        text_total = 0
        layouts = []
        for idx, name in enumerate(names, 1):
            if z.getinfo(name).file_size > ZIP_MEMBER_CAP:
                continue
            shapes = _slide_shapes(z.read(name))
            if not shapes:
                continue
            page_chars = sum(len(s["text"]) for s in shapes)
            text_total += page_chars
            layouts.append((len(shapes), page_chars))

            # --- 并排检测：y 相近、x 分散、宽度可容纳并排
            row_tol = slide_h * 0.08
            rows = {}
            for s in shapes:
                if s["w"] < slide_w * 0.12:
                    continue
                key = round(s["y"] / max(row_tol, 1))
                rows.setdefault(key, []).append(s)
            for key, group in rows.items():
                if len(group) < 3:
                    continue
                xs = sorted(g["x"] for g in group)
                if xs[-1] - xs[0] < slide_w * 0.35:
                    continue
                findings.append({
                    "页": idx,
                    "类型": "并排三栏以上",
                    "细节": f"{len(group)} 个文本框横排在同一高度",
                    "修复": "改纵向推进，或只保留并列中的一项，其余移到下一页",
                })

            # --- 同页存在两种方向
            has_side = any(len(g) >= 3 for g in rows.values())
            ys = sorted(s["y"] for s in shapes)
            has_stack = (ys[-1] - ys[0]) > slide_h * 0.4
            if has_side and has_stack:
                findings.append({
                    "页": idx,
                    "类型": "阅读方向混杂",
                    "细节": "同一页既有横向并排又有纵向推进",
                    "修复": "拆成两页：一页只承担一个方向",
                })

            # --- 信息量
            if page_chars > 150:
                findings.append({
                    "页": idx,
                    "类型": "单页文字超载",
                    "细节": f"{page_chars} 字（建议 ≤120，上限 150）",
                    "修复": "砍到一屏能念完；细节进备注或附录",
                })

            # --- 要点过多
            bullets = sum(1 for s in shapes if re.match(r"^[\-·•\d一二三四五六七八九十]", s["text"]))
            if bullets > 5:
                findings.append({
                    "页": idx,
                    "类型": "要点过多",
                    "细节": f"{bullets} 条并列要点",
                    "修复": "合并到 3 条以内，或拆页",
                })

            # --- 标题口号化
            title = max(shapes, key=lambda s: s["y"] * -1) if shapes else None
            top = min(shapes, key=lambda s: s["y"])
            for s in shapes:
                if s["y"] <= top["y"] + row_tol and len(s["text"]) <= 24:
                    if RE_TITLE_SLOGAN.match(s["text"].strip()):
                        findings.append({
                            "页": idx,
                            "类型": "标题口号化/对仗",
                            "细节": s["text"][:30],
                            "修复": "改成一句能念出口的判断句，主语+动作+结果",
                        })
                    break

        # --- 跨页同构
        if len(layouts) >= 5:
            shapes_seq = [n for n, _ in layouts]
            mode = max(set(shapes_seq), key=shapes_seq.count)
            if shapes_seq.count(mode) >= len(shapes_seq) * 0.75:
                findings.append({
                    "页": "全文",
                    "类型": "跨页版式同构",
                    "细节": f"{shapes_seq.count(mode)}/{len(shapes_seq)} 页元素数完全相同",
                    "修复": "按内容角色换版式：数据页、过程页、结论页不该一个模子",
                })

    score = min(100, len(findings) * 14)
    return {
        "页数": len(names),
        "抽字": text_total,
        "score": score,
        "band": band(score),
        "findings": findings,
    }


# =============================================================== Office 抽取
ZIP_DOC = {
    ".docx": ("word/document.xml",),
    ".docm": ("word/document.xml",),
    ".pptx": ("ppt/slides/slide",),
    ".pptm": ("ppt/slides/slide",),
    ".xlsx": ("xl/sharedStrings.xml", "xl/worksheets/sheet"),
    ".xlsm": ("xl/sharedStrings.xml", "xl/worksheets/sheet"),
    ".odt": ("content.xml",),
    ".odp": ("content.xml",),
    ".ods": ("content.xml",),
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def extract_office_text(path: str) -> str:
    """从 zip 型文档抽正文。移植自 sloptrim，去掉 EPUB/LaTeX 分支。"""
    import xml.etree.ElementTree as ET
    import zipfile

    ext = os.path.splitext(path)[1].lower()
    wanted = ZIP_DOC.get(ext)
    if not wanted:
        return ""
    spreadsheet = ext in {".xlsx", ".xlsm"}
    shared = []
    out = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if any(w in n for w in wanted)]
        names.sort(key=lambda n: (len(n), n))
        for name in names:
            try:
                if z.getinfo(name).file_size > ZIP_MEMBER_CAP:
                    continue
                blob = z.read(name)
            except (KeyError, zipfile.BadZipFile, EOFError):
                continue
            try:
                root = ET.fromstring(blob)
            except ET.ParseError:
                continue
            buf = []
            if spreadsheet:
                if name.endswith("sharedStrings.xml"):
                    shared = ["".join(el.text or "" for el in si.iter()
                                      if _local(el.tag) == "t")
                              for si in root if _local(si.tag) == "si"]
                    continue
                for cell in root.iter():
                    if _local(cell.tag) != "c":
                        continue
                    kind = cell.get("t")
                    value = next((el.text or "" for el in cell
                                  if _local(el.tag) == "v"), "")
                    if kind == "s":
                        try:
                            i = int(value)
                        except ValueError:
                            continue
                        if 0 <= i < len(shared):
                            value = shared[i]
                    elif kind == "inlineStr":
                        value = "".join(el.text or "" for el in cell.iter()
                                        if _local(el.tag) == "t")
                    elif kind != "str":
                        continue
                    if value:
                        buf.extend((value, "\n"))
            else:
                for el in root.iter():
                    tag = _local(el.tag)
                    if tag == "t" and el.text:
                        buf.append(el.text)
                    elif tag in {"p", "br", "tab", "tr"}:
                        if buf and buf[-1] != "\n":
                            buf.append("\n")
                        if el.text:
                            buf.append(el.text)
                    if el.tail and el.tail.strip():
                        buf.append(el.tail)
            chunk = "".join(buf)
            if chunk.strip():
                out.append(chunk)
    text = "\n\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    ext = os.path.splitext(path)[1].lower()
    if ext in ZIP_DOC:
        return extract_office_text(path)
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


# =============================================================== 输出
def report(path: str, result: dict, ppt: dict | None) -> str:
    lines = []
    lines.append(f"文件: {path}")
    lines.append(f"AI 味评分: {result['score']}/100 —— {result['band']}（{result['confidence']}）")
    m = result["metrics"]
    lines.append(
        f"字数 {m['字数']} · 句数 {m['句数']} · "
        f"句长变异 {m['句长变异']} · 段长变异 {m['段长变异']} · "
        f"AI词密度 {m['AI词密度_每千字']}/千字"
    )
    if result["patterns"]:
        lines.append("\n命中模式:")
        for rid, info in sorted(result["patterns"].items()):
            ex = "、".join(info["样例"])[:60]
            lines.append(f"  [{rid}] {info['名称']} ×{info['次数']}  例：{ex}")
    else:
        lines.append("\n未命中任何模式。")
    if ppt:
        lines.append(
            f"\n版式评分: {ppt['score']}/100 —— {ppt['band']}"
            f"（{ppt['页数']} 页，抽字 {ppt['抽字']}）"
        )
        if ppt["findings"]:
            for f in ppt["findings"]:
                where = f"第{f['页']}页" if isinstance(f["页"], int) else f["页"]
                lines.append(f"  [{where}] {f['类型']}: {f['细节']} → {f['修复']}")
        else:
            lines.append("  版式无命中。")
    return "\n".join(lines)


def main() -> int:
    args = [a for a in sys.argv[1:]]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 2 if not args else 0
    as_json = "--json" in args
    limit = 40
    if "--min" in args:
        try:
            limit = int(args[args.index("--min") + 1])
            args = args[:args.index("--min")] + args[args.index("--min") + 2:]
        except (IndexError, ValueError):
            print("--min 需要一个整数", file=sys.stderr)
            return 2
    path = args[0]

    try:
        text = read_input(path)
    except OSError as e:
        print(f"读取失败: {e}", file=sys.stderr)
        return 2
    if not text.strip():
        print("抽不到正文（可能是扫描件、加密文档或纯图表页）", file=sys.stderr)
        return 2

    found = scan_text(text)
    result = score_text(text, found)
    result["patterns"] = found

    ppt = None
    if path != "-" and os.path.splitext(path)[1].lower() in {".pptx", ".pptm"}:
        try:
            ppt = check_pptx(path)
        except Exception as e:  # noqa: BLE001 版式通道失败不该拖垮文字通道
            ppt = {"error": str(e)}

    if as_json:
        print(json.dumps({"文件": path, "文字": result, "版式": ppt},
                         ensure_ascii=False, indent=2))
    else:
        print(report(path, result, ppt if ppt and "error" not in ppt else None))
        if ppt and "error" in ppt:
            print(f"\n版式通道失败: {ppt['error']}")

    total = result["score"] + (ppt["score"] if ppt and "score" in ppt else 0) // 2
    return 0 if total <= limit else 1


if __name__ == "__main__":
    sys.exit(main())
