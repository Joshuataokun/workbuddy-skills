# -*- coding: utf-8 -*-
"""
中文小说/文本标点规范化规则库。

每个规则函数接收文本，返回 (新文本, 修改计数)，保证幂等（重复执行结果一致）。
规则顺序有讲究（先成对后单个、先特殊符号后半角转换），
完整流水线见 scripts/fix_punctuation.py。
"""

import re

# ------------------------------------------------------------------
# 字符分类
# ------------------------------------------------------------------

def is_cjk(ch):
    """是否为中文语境字符（汉字、中文标点、全角字符、弯引号）。"""
    if not ch:
        return False
    o = ord(ch)
    return (
        0x4E00 <= o <= 0x9FFF      # 基本汉字
        or 0x3400 <= o <= 0x4DBF   # 汉字扩展A
        or 0x3000 <= o <= 0x303F   # CJK符号与标点（。！？、等）
        or 0xFF01 <= o <= 0xFF5E   # 全角形式（Ａ１，等）
        or 0x2018 <= o <= 0x201D   # 弯引号 ''"" 
        or 0x2026 == o             # 省略号 …
        or 0x300A <= o <= 0x300B   # 《》
        or ch in "【】、—～·「」『』"
    )


def _is_ascii_alnum(ch):
    return bool(ch) and ch.isascii() and ch.isalnum()


# ------------------------------------------------------------------
# 特殊符号规范化（省略号 / 破折号 / 波浪线）
# ------------------------------------------------------------------

# 省略号类字符的连续串（一处省略号 = 一个 maximal run）
_ELLIPSIS_RUN = re.compile(r"[.。．·・⋯‥…]{2,}")


def _normalize_ellipsis_run(run):
    """归一化一个省略号串。

    - 纯 U+2026 串：不超过两个（…………）是合法上限，保留；三个以上折成两个
    - 其余混写（... 。。。 ··· ‥‥ 等）：统一为一个六连点 ……
    """
    if set(run) == {"\u2026"}:
        return run if len(run) <= 2 else "\u2026\u2026"
    return "\u2026\u2026"


def normalize_ellipsis(text):
    """各种省略号写法统一为六连点……：... 。。。 ．． ··· ‥‥ ⋯⋯ 等。

    单次遍历 maximal run 整体替换，天然幂等；一处只计一次。
    """
    n = 0

    def repl(m):
        nonlocal n
        run = m.group(0)
        norm = _normalize_ellipsis_run(run)
        if norm != run:
            n += 1
        return norm

    return _ELLIPSIS_RUN.sub(repl, text), n


# 分隔线行：整行只有 - = ~ _ * · ─ 等装饰字符（章节分隔线，不动）
_SEPARATOR_LINE = re.compile(r"^[\s\-=~_*·─—―]{3,}$")


def normalize_dashes(text):
    """破折号统一为两连——：-- ―― ── ———— 等。分隔线行跳过。

    不动点循环：混合写法（如 --— ）首轮可能产生新的可匹配模式。
    """
    dash_re = re.compile(r"-{2,}|—{2,}|―{2,}|─{2,}")
    lines = text.split("\n")
    total = 0
    for i, line in enumerate(lines):
        if _SEPARATOR_LINE.match(line.strip()):
            continue
        for _ in range(4):
            new, n = dash_re.subn("——", line)
            if new == line:
                break
            total += n
            line = new
        lines[i] = line
    return "\n".join(lines), total


# 波浪线类字符（逐字符归一，不折叠连续串）
_TILDE_CHARS = "~～∼〜\u301c"


def normalize_tildes(text):
    """波浪线统一为全角～：~ ˜ ∼ 〜 → ～。

    逐字符替换，不折叠连续串：小说中 `～～～` 常是风格化延长音
    （如 `吸溜～～～`），折叠会损失作者风格。
    单字符替换天然幂等；分隔线行跳过。
    """
    n = 0
    out_lines = []
    for line in text.split("\n"):
        if _SEPARATOR_LINE.match(line.strip()):
            out_lines.append(line)
            continue
        cnt = sum(1 for c in line if c in _TILDE_CHARS and c != "～")
        if cnt:
            n += cnt
            line = "".join("～" if c in _TILDE_CHARS else c for c in line)
        out_lines.append(line)
    return "\n".join(out_lines), n


# ------------------------------------------------------------------
# 重复标点合并
# ------------------------------------------------------------------

# 几乎必然是错误的重复（默认合并）
_SAFE_REPEAT = re.compile(r"([。，、；：])\1+|([,;:])\2+")
# 感叹号/问号叠用：小说中常作风格化强调，默认保留，--collapse-bang 时合并
_BANG_REPEAT = re.compile(r"([！？!?])\1+")


def collapse_repeats(text, collapse_bang=False):
    """合并重复标点：。。 ，， ：： 等；!! ?? 仅在开启时合并。"""
    text, n1 = _SAFE_REPEAT.subn(lambda m: m.group(1) or m.group(2), text)
    n2 = 0
    if collapse_bang:
        text, n2 = _BANG_REPEAT.subn(r"\1", text)
    return text, n1 + n2


# ------------------------------------------------------------------
# 全角字母数字 → 半角
# ------------------------------------------------------------------

def fullwidth_alnum_to_half(text):
    """ＡＢＣ１２３ → ABC123（只转字母数字，不动全角标点）。"""
    def repl(m):
        return chr(ord(m.group(0)) - 0xFEE0)
    return re.subn(r"[Ａ-Ｚａ-ｚ０-９]", repl, text)


# ------------------------------------------------------------------
# 英文直引号 → 中文弯引号
# ------------------------------------------------------------------

def convert_straight_quotes(text):
    """英文直引号转中文弯引号。

    双引号 " 按出现顺序交替转为 " "（先成对后单个原则）。
    单引号 ' 区分两种身份：
      - 位于两个ASCII字母/数字之间（don't / it's）→ 弯撇号 ’，不参与配对
      - 其余位置视为引用单引号，交替转为 ‘ ’
    返回 (新文本, 双引号转换数, 单引号转换数, 撇号转换数)。
    """
    # 双引号：交替
    out = []
    toggle = True  # True=开
    n_dq = 0
    for ch in text:
        if ch == '"':
            out.append("\u201c" if toggle else "\u201d")
            toggle = not toggle
            n_dq += 1
        else:
            out.append(ch)
    text = "".join(out)

    # 单引号：撇号检测
    out = []
    toggle = True
    n_sq = 0
    n_apos = 0
    for i, ch in enumerate(text):
        if ch == "'":
            prev = text[i - 1] if i > 0 else ""
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if _is_ascii_alnum(prev) and _is_ascii_alnum(nxt):
                out.append("\u2019")  # don't → don’t
                n_apos += 1
            else:
                out.append("\u2018" if toggle else "\u2019")
                toggle = not toggle
                n_sq += 1
        else:
            out.append(ch)
    return "".join(out), n_dq, n_sq, n_apos


# ------------------------------------------------------------------
# 半角标点 → 全角（中文语境感知）
# ------------------------------------------------------------------

# 需整体保护的片段：URL 与邮箱（其中的标点一律不动）
_URL_EMAIL = re.compile(
    r"(?:[a-zA-Z][a-zA-Z0-9+.-]*://|www\.)\S+"  # http:// https:// ftp:// www.xxx
    r"|[^\s@]+@[^\s@]+\.[^\s@]+"                # 邮箱
)

# HTML 实体 &lt; &gt; &amp; &quot; &nbsp; &#123; &#x1F; （分号等内部字符不动，
# 否则会把实体打断成 &lt； 而失去转义含义）
_HTML_ENTITY = re.compile(
    r"&(?:[a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#[xX][0-9a-fA-F]+);"
)

_ASCII_PUNCT = {
    ",": "，", ".": "。", "!": "！", "?": "？",
    ":": "：", ";": "；", "(": "（", ")": "）",
}

_CONTEXT_WINDOW = 10  # 前后各看10个字符判断语境


def convert_ascii_punct(text):
    """中文语境下的半角标点转全角。

    保护规则（这些位置不动）：
      - 小数点 3.14、千分位 1,000、时间 12:30（两侧均为数字）
      - URL 中的冒号 http:// （后跟 /）
      - 序号缩写 No.1（前为字母后为数字）
      - URL / 邮箱整体（白名单，内部标点一律不动）
      - HTML 实体 &lt; &gt; &#123;（白名单，分号等一律不动）
      - 前后窗口内没有任何中文字符的纯英文内容
    """
    # 计算 URL/邮箱/HTML实体 保护区间
    protected = set()
    for pattern in (_URL_EMAIL, _HTML_ENTITY):
        for m in pattern.finditer(text):
            protected.update(range(m.start(), m.end()))

    out = list(text)
    n = 0
    for i, ch in enumerate(text):
        if ch not in _ASCII_PUNCT:
            continue
        if i in protected:
            continue
        prev = text[i - 1] if i > 0 else ""
        nxt = text[i + 1] if i + 1 < len(text) else ""

        # 数字语境保护
        if ch in ".,:" and prev.isdigit() and nxt.isdigit():
            continue
        if ch == ":" and nxt == "/":
            continue
        if ch == "." and prev.isascii() and prev.isalpha() and nxt.isdigit():
            continue  # No.1 之类
        if ch == "." and (prev == "." or nxt == "."):
            continue  # 省略号残留双保险

        before = text[max(0, i - _CONTEXT_WINDOW):i]
        after = text[i + 1:i + 1 + _CONTEXT_WINDOW]
        if any(is_cjk(c) for c in before + after):
            out[i] = _ASCII_PUNCT[ch]
            n += 1
    return "".join(out), n


# ------------------------------------------------------------------
# 单引号层级提升（引号层级规范化）
# ------------------------------------------------------------------

DQ_L = "\u201c"   # "
DQ_R = "\u201d"   # "
SQ_L = "\u2018"   # '
SQ_R = "\u2019"   # '

# 国标 GB/T 15834-2011 4.8.3.4：「引号里面还要用引号时，外面一层用双引号，
# 里面一层用单引号」。即单引号只能作为双引号内的嵌套层出现；出现在双引号
# 嵌套深度之外的单引号（被当作对话引号或着重引号使用）属于层级错误，
# 提升为对应的双引号。双引号内的单引号是合法嵌套，原样保留。
#
# 前置条件：调用前文本的双引号必须已配对平衡（流水线中先执行引号配对
# 修复，保证每行自成平衡），深度状态机才可靠。


def promote_single_quotes(text):
    """把双引号外层出现的单引号提升为双引号；嵌套单引号保留。

    规则：
      - 双引号嵌套深度之外的 ' ' → “ ”（层级提升，计数）
      - 双引号之内的 ' ' → 合法嵌套，原样保留
      - 两个 ASCII 字母/数字之间的 '（don't / O'Neill）→ 撇号，保留

    返回 (新文本, 提升数, 保留嵌套数)。幂等：提升后外层不再有单引号，
    嵌套单引号再次执行仍判为嵌套，二次执行零改动。
    """
    out = []
    depth = 0
    n_promote = 0
    n_nested = 0
    n = len(text)
    for i, ch in enumerate(text):
        if ch == DQ_L:
            depth += 1
            out.append(ch)
        elif ch == DQ_R:
            if depth > 0:
                depth -= 1
            out.append(ch)
        elif ch in (SQ_L, SQ_R):
            prev = text[i - 1] if i > 0 else ""
            nxt = text[i + 1] if i + 1 < n else ""
            if (prev.isascii() and prev.isalnum()
                    and nxt.isascii() and nxt.isalnum()):
                out.append(ch)  # 撇号 don't，保留
            elif depth == 0:
                out.append(DQ_L if ch == SQ_L else DQ_R)
                n_promote += 1
            else:
                out.append(ch)  # 双引号内的合法嵌套，保留
                n_nested += 1
        else:
            out.append(ch)
    return "".join(out), n_promote, n_nested


# ------------------------------------------------------------------
# 空引号对修复（“” —— 双引号之间没有内容）
# ------------------------------------------------------------------

# 空对内部不允许出现的句读（短强调对判定用）
_EMPH_PUNCT = "。！？…；，、："
# 言语结束句读（补闭引号定位用）
_SPEECH_END = "。！？…"
# 言语情绪标记（行尾空对「移动」判定用：含标记视为漏引言语）
_SPEECH_MARK = "……！？"

# 冒号/逗号后的倒置对话对（E3）：：”X“” → ：“X”
_EQ_COLON = re.compile("([：，])" + DQ_R + "([^" + DQ_L + DQ_R + "]+)"
                       + DQ_L + DQ_R)
# 短强调倒置对（E4）：”X“” → “X”（X≤10字且无句读）
_EQ_EMPH = re.compile(DQ_R + "([^" + DQ_L + DQ_R + _EMPH_PUNCT + "]{1,10})"
                      + DQ_L + DQ_R)
# 冒号后的言语+空对（E7）：：X“” → ：“X”
_EQ_AFTER_COLON = re.compile("：([^" + DQ_L + DQ_R + "]+)" + DQ_L + DQ_R)
# 跨行倒置对话：行N = [可选debris“]无引号解说（含言语动词+：，）+ ” 结尾
_CR_LINE_N = re.compile(r"^(\s*)" + DQ_L + r"?([^" + DQ_L + DQ_R + r"]*"
                        r"[道说笑问喝骂喊哭叹辩答曰云][：，])" + DQ_R + r"\s*$")


def fix_crossline_inverted_quotes(text):
    """跨行倒置对话修复：行N末尾的倒置开引号 + 行N+1的倒置闭引号。

    模式（《覆雨翻云》行 17772-17773 实战）：
      行N  = [可选 debris“]无引号解说（含言语动词+：，）+ ”
      行N+1 = 无引号言语 + “
    作者本意：解说后引出对话，对话用双引号括起来。

    修复：删行N的 debris“（若有），行N末尾 ”→“（倒置开引号翻正），
          行N+1的首个 “→”（倒置闭引号翻正），两行合并。
    例：「“秦柔侧着臻首……柔声道：” / 你还想怎么样？“」
        →「秦柔侧着臻首……柔声道：“你还想怎么样？”」

    安全：行N要求「引号仅出现在动词+：，+”」之后，含其他引号的行不匹配；
    行N+1要求「“」前为无引号正文（否则是正常对话开头，不匹配）。
    合并成行内引号对，避免配对修复把行N末尾的孤立开引号补成 “” 空对。

    返回 (新文本, 修复处数)。
    """
    lines = text.split("\n")
    out = []
    n = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _CR_LINE_N.match(line)
        if m and i + 1 < len(lines):
            nxt = lines[i + 1]
            # 行N+1：缩进后以「非空白非引号」正文开头、随后出现 “
            #（“ 直接开头是正常对话，不匹配）
            m2 = re.match(r"^\s*([^" + DQ_L + DQ_R + r"\s][^"
                          + DQ_L + DQ_R + r"]*)" + DQ_L, nxt)
            if m2:
                # 合并：解说 + ：， + “ + 言语 + ” + 行N+1剩余部分
                rest = nxt[m2.end():]
                merged = (m.group(1) + m.group(2) + DQ_L
                          + m2.group(1) + DQ_R + rest)
                out.append(merged)
                n += 1
                i += 2
                continue
        out.append(line)
        i += 1
    return "\n".join(out), n


def _first_unclosed_quote(line):
    """返回 (第一个未闭合左引号的位置, 是否存在未闭合)。栈式配对。"""
    depth = 0
    first = -1
    for j, ch in enumerate(line):
        if ch == DQ_L:
            if depth == 0 and first < 0:
                first = j
            depth += 1
        elif ch == DQ_R and depth > 0:
            depth -= 1
    return first, depth > 0


def _is_true_nested(line):
    """合法嵌套强调行判定：引号序列以 “ 开头、” 结尾，且同时含 “” 和 “”。"""
    s = line.strip()
    seq = "".join(c for c in s if c in (DQ_L, DQ_R))
    return (seq.startswith(DQ_L) and seq.endswith(DQ_R)
            and (DQ_L + DQ_L) in seq and (DQ_R + DQ_R) in seq)


def fix_empty_quote_pairs(text):
    """修复「空引号对」“”（双引号之间没有内容）。

    来源（《覆雨翻云》实战，130 处）：① 作者倒置引号习惯（开引号写 ”、
    闭引号写 “）与配对补引号叠加，在行尾/段中生成 “”；② 作者原文自带的
    “”X“” 包裹残骸与 ”X“” 倒置强调对+多余闭引号。

    规则（逐行，按序应用，均幂等——所有模式都要求真实存在 “”）：
      E1 包裹空对     “”X“” → “X”          整行包裹的对话/强调
      E2 行首空对     ^“” → “               行首多余的开引号
      E3 倒置对话对   [：，]”X“” → [：，]“X”  冒号/逗号后倒置的对话对
      E4 短强调倒置对 ”X“” → “X”            X≤10字且无句读（排除正常
                                            闭引号+新引语，防误伤）
      E3/E4 附带补闭  翻转后若行内第一个开引号未闭合，在其后、下一个
                      引号之前的最后一个言语结束句读后补 ”（作者对话
                      开了头没结尾的常见缺陷；翻转倒置对后会暴露出来）
      E5 行尾移动     ”X“”$ → ”“X”          X 含情绪标记或≤12字：上一
                      个闭引号正常、X 是漏引言语，把开引号移到 X 前
      E6 行尾残骸     X“”$ → X              其余行尾空对直接删除（不猜语义）
      E7 冒号言语     ：X“” → ：“X”         冒号后漏引言语+空对
      E8 整行强调     A“”B“C”$ → A“B”C      A非空：强调对前半边丢失
      E9/E10 行首 debris “ 清理              解说误加引号（动词+：，/长解说）
      E11 倒置强调对+的 ”X“的 → “X”的        X≤10字无句读（「的」=定语信号）
      E12 旁白开引号残骸 “”X“Y” → ”X“Y”      紧邻对中的旁白开引号
      E12b 行首旁白残骸 ^“X“Y” → X“Y”        Y 短强调
      E13 漏引言语    ”X“ → ”“X”            X 感叹词开头+情绪标记；
                                            「“」后30字内无闭引号才动
      E14 行尾多余闭引号                     行尾 ”（前有句读）且右>左 → 删除

    返回 (新文本, 修复行数)。
    """
    n = 0
    out_lines = []
    for line in text.split("\n"):
        orig = line
        noq = "[^" + DQ_L + DQ_R + "]"

        # E1 包裹空对：“”内容“” → “内容”
        line = re.sub(DQ_L + DQ_R + "(" + noq + "+)" + DQ_L + DQ_R,
                      DQ_L + r"\1" + DQ_R, line)
        # E2 行首空对：行首 “” → “
        line = re.sub(r"^(\s*)" + DQ_L + DQ_R, r"\1" + DQ_L, line)

        # E3/E4 倒置对翻转 + 附带补闭（每行最多 3 轮）
        for _ in range(3):
            before = line
            m3 = _EQ_COLON.search(line)
            m4 = _EQ_EMPH.search(line)
            if m3 and (not m4 or m3.start() <= m4.start()):
                line = line[:m3.start()] + m3.group(1) + DQ_L \
                    + m3.group(2) + DQ_R + line[m3.end():]
            elif m4:
                line = line[:m4.start()] + DQ_L + m4.group(1) \
                    + DQ_R + line[m4.end():]
            else:
                break
            # 附带补闭：翻转暴露了未闭合的开引号（作者对话开了头没结尾），
            # 在其后、下一个引号之前的最后一个言语结束句读后补 ”
            u, unc = _first_unclosed_quote(line)
            if unc and u >= 0:
                nxt = len(line)
                for j in range(u + 1, len(line)):
                    if line[j] in (DQ_L, DQ_R):
                        nxt = j
                        break
                seg = line[u + 1:nxt]
                ends = [k for k, ch in enumerate(seg) if ch in _SPEECH_END]
                if ends:
                    at = u + 1 + ends[-1] + 1
                    line = line[:at] + DQ_R + line[at:]
            if line == before:
                break

        # E5 行尾空对移动：”X“”$ → ”“X”
        # 仅当 X 含言语情绪标记（……！？）——上一个闭引号正常、X 是
        # 漏引言语；旁白（无标记）交给 E6 删除，避免把解说括进引号
        m = re.search(DQ_R + "(" + noq + "+)" + DQ_L + DQ_R + r"\s*$", line)
        if m and m.group(1)[-1] not in "：，" and (
                any(c in m.group(1) for c in _SPEECH_MARK)):
            line = line[:m.start()] + DQ_R + DQ_L + m.group(1) + DQ_R
        # E6 行尾空对残骸：非引号字符 + “” + 行尾 → 删除空对
        line = re.sub("(" + noq + ")" + DQ_L + DQ_R + r"\s*$", r"\1", line)
        # E7 冒号后的漏引言语：：X“” → ：“X”
        line = _EQ_AFTER_COLON.sub("：" + DQ_L + r"\1" + DQ_R, line)
        # E8 整行强调对前半边丢失：A“”B“C”$ → A“B”C（A 非空）
        line = re.sub("^(" + noq + "+)" + DQ_L + DQ_R
                      + "(" + noq + "{1,8})" + DQ_L
                      + "(" + noq + "*)" + DQ_R + r"\s*$",
                      r"\1" + DQ_L + r"\2" + DQ_R + r"\3", line)

        # E9 行首 debris 引号：行首 “ + 无引号解说语（含言语动词+：，）
        #    + “对话” → 删行首引号。仅奇数次引号行（偶次是真嵌套，
        #    受 is_true_nested 保护，不能动）
        if (line.count(DQ_L) + line.count(DQ_R)) % 2 == 1:
            line = re.sub(r"^(\s*)" + DQ_L
                          + r"([^" + DQ_L + DQ_R + r"]*"
                          + r"[道说笑问喝骂喊哭叹辩答曰云][：，]?)" + DQ_L,
                          r"\1\2" + DQ_L, line)
        # E10 行首 debris 引号（整行型）：行首 “ + 长解说 + “言语” +
        #    行尾 → 删行首引号（解说≥10字，排除短嵌套残引）
        line = re.sub(r"^\s*" + DQ_L + "(" + noq + "{10,})" + DQ_L
                      + "(" + noq + "+)" + DQ_R + r"\s*$",
                      r"\1" + DQ_L + r"\2" + DQ_R, line)

        # E11 倒置强调对+的：”X“的 → “X”的（X≤10字无句读；「的」是
        #    定语信号——「啪、啪的声音」必然强调而非对话）
        line = re.sub(DQ_R + "([^" + DQ_L + DQ_R + "。！？…；，：]{1,10})"
                      + DQ_L + "(?=的)", DQ_L + r"\1" + DQ_R, line)

        # E12 旁白开引号残骸（”“紧邻型）：”“X“Y” → ”X“Y”
        #    删紧邻对中的开引号（旁白误加引号，如 「“房间不停的响着”啪、啪“」）
        line = re.sub(DQ_R + DQ_L + "(" + noq + "+)" + DQ_L
                      + "([^" + DQ_L + DQ_R + "。！？…；，：]{1,10})" + DQ_R,
                      DQ_R + r"\1" + DQ_L + r"\2" + DQ_R, line)
        # E12b 行首旁白开引号残骸：^\s*“X“Y” → X“Y”（Y 为短强调）。
        #    真嵌套行（L L R R）受保护不动
        if not _is_true_nested(line):
            line = re.sub(r"^(\s*)" + DQ_L + "(" + noq + "+)" + DQ_L
                          + "([^" + DQ_L + DQ_R + "。！？…；，：]{1,10})" + DQ_R,
                          r"\1\2" + DQ_L + r"\3" + DQ_R, line)

        # E13 漏引言语（感叹词开头）：”X“ → ”“X”
        #    上一个闭引号正常，X 以感叹词开头且含情绪标记=漏引言语，
        #    其后的 “ 是倒置闭引号。要求「“」后 30 字内无闭引号
        #    （否则 “ 是正常开引号，如 ”啊……“我们去吧” 不误伤）
        m = re.search(DQ_R + "([啊喔嗯呜唔哼哈哎]" + noq + "*[……！？]"
                      + noq + "*)" + DQ_L + r"(?!" + noq + "{0,30}" + DQ_R + ")",
                      line)
        if m:
            line = line[:m.start()] + DQ_R + DQ_L + m.group(1) + DQ_R \
                + line[m.end():]

        # E14 行尾多余闭引号：行尾 ”（前有句读）且行内右引号多于左引号
        #    → 删除（旁白残骸；只在删除后能改善平衡时动手）
        stripped = line.rstrip()
        if (stripped.endswith(DQ_R) and len(stripped) >= 2
                and stripped[-2] in _SPEECH_END
                and line.count(DQ_R) > line.count(DQ_L)):
            line = stripped[:-1] + line[len(stripped):]

        # E15 行首 debris + 倒置开引号（整行型）：
        #    “解说[：，]”言语$ → 解说[：，]“言语
        #    来源：「“谈应手微微一笑……淡然道：“既然如此……」这类行，
        #    行首 “ 是解说误加引号（debris），：，后的 “ 是言语的正常
        #    开引号；交替重排曾把它错翻成 ”（产生 ：”）。修复：删行首
        #    debris、” 翻正为 “。漏写的闭引号由配对步在行尾补齐。
        m = re.match(r"^(\s*)" + DQ_L + "([^" + DQ_L + DQ_R + r"]*?[：，])"
                     + DQ_R + "(" + noq + r"+)\s*$", line)
        if m:
            line = m.group(1) + m.group(2) + DQ_L + m.group(3)

        if line != orig:
            n += 1
        out_lines.append(line)
    return "\n".join(out_lines), n


# ------------------------------------------------------------------
# 断链引号修复（倒置强调对 / 行首叠引 / 漏开引号 / 行尾漏闭）
# ------------------------------------------------------------------
#
# 来源：《冰山女教师的反差沉沦》人工校对 35 例反推（用户亲校的正确答案）。
# 该文稿的病根是「闭引号一律写成开引号」+「对话开头的开引号被吃掉」，
# 两种病态相邻出现时，逐行交替重排会被前一个病态带偏而放弃整行，
# 于是留下大量”看起来像嵌套、其实断链”的行。本组规则用「预算法」处理：
#   预算 budget = 行内多余左引号数（L - R）
#   每次把一处 “ 翻正为 ” 消耗 2 个预算（L-1、R+1，差额缩小 2）
# 因此只有当行确实「左引号过多」时才动手，天然不会碰已平衡的行
# （合法嵌套强调行 L==R，永远不进预算分支）。

_EMPH_STOP = set("。！？，；：、")   # 倒置强调对内部不允许出现的标点
_EMPH_MAX = 10                     # 强调对内容最长字数
_INV_CLOSE_PREV = "。！？…"         # 倒置闭引号前允许的言语结束句读
_SPEECH_VERB = "说道问答喊叫嚷骂笑叹曰云"  # 言语动词（旁白引出对话的信号）


def _balance(line):
    return line.count(DQ_L) - line.count(DQ_R)


def _flip_at(line, pos):
    """把 line[pos] 的 “ 翻正为 ”。"""
    return line[:pos] + DQ_R + line[pos + 1:]


def _quote_depths(line):
    """返回「每个引号位置 → 它之前的深度」。用于避免把正常的对话开引号
    误判成倒置闭引号（正常开引号出现在深度 0，倒置闭引号必然在深度 ≥1）。"""
    d = 0
    out = {}
    for i, ch in enumerate(line):
        if ch == DQ_L:
            out[i] = d
            d += 1
        elif ch == DQ_R:
            d = max(0, d - 1)
    return out


def _emph_positions(line, depths):
    """倒置强调对 “X“ 中第二个 “ 的位置（X≤10字、无句读、深度≥1）。"""
    out = []
    pat = re.compile(DQ_L + "([^" + DQ_L + DQ_R + "]{1," + str(_EMPH_MAX) + "})"
                     + DQ_L)
    for m in pat.finditer(line):
        if _EMPH_STOP & set(m.group(1)):
            continue
        pos = m.end() - 1
        if depths.get(pos, 0) < 1:
            continue
        out.append(pos)
    return out


def _inverted_close_positions(line, depths):
    """紧跟在 。！？… 之后、且处于引号内的 “ 的位置（= 倒置闭引号）。

    深度 0 的不算——那是「旁白收尾 ＋ 另起一段对话」的正常开引号。
    """
    return [i for i, ch in enumerate(line)
            if ch == DQ_L and i > 0 and line[i - 1] in _INV_CLOSE_PREV
            and i < len(line) - 1 and depths.get(i, 0) >= 1]


def _missing_open_ok(line):
    """判断行首是否漏了对话开引号，返回 (是否可以补, 该翻正的 “ 位置)。

    条件（逐条都必要，少一条就可能把「旁白＋对话」误当「对话＋旁白」）：
      1. 行不以 “ 开头，行内第一个 “ 紧跟句读（。！？…，）
      2. 该 “ 之前的正文里没有句号「。」——句号是旁白收尾的信号，
         问号感叹号则常是对话本身的收尾（“九十分可以吗？老师？”）
      3. 该 “ 之前不含引号，且末尾 8 字内没有言语动词
         （…他说，“…” 这种是旁白引出对话，不能补开引号）
      4. 该 “ 之后紧跟「旁白＋下一段引语」且旁白不少于 4 字
         （排除“行尾残句”误判）
    """
    if not line or line[0] == DQ_L:
        return False, -1
    for i, ch in enumerate(line):
        if ch == DQ_L:
            if i == 0 or line[i - 1] not in "。！？…，":
                return False, -1
            head = line[:i]
            if "。" in head or set(DQ_L + DQ_R) & set(head):
                return False, -1
            if set(_SPEECH_VERB) & set(head[-8:]):
                return False, -1
            j = i + 1
            while j < len(line) and line[j] not in (DQ_L, DQ_R):
                j += 1
            if j >= len(line) or j - i - 1 < 4:
                return False, -1      # 引号后没有「旁白+下一段引语」，不是漏开引号
            return True, i
    return False, -1


def fix_dangling_quotes(text):
    """修复「引号断链」行：倒置强调对、行首叠引、行尾孤立引、漏开/漏闭。

    逐行按优先级反复应用，直到该行平衡或无规则可施（最多 8 轮）：
      D1 行首叠引     ““X → “X                行首多打一个开引号
      D6 行尾孤立引   X句读“ → X句读           行尾多打一个开引号（最常见
                                              的残骸，必须先删，否则会被
                                              当成开引号补出配对来）
      D2 倒置强调对   “X“ → “X”               X≤10字且无句读（含句读的成句
                                              言语交给配对步，避免与“翻正
                                              还是删除”的歧义打架）
      D3 倒置闭引号   。！“ → 。！”             紧跟言语结束句读、行内非末尾
      D5 补闭引号     行尾 。 → 。”（余额恰为 1） 对话开了头没结尾
      D4 补开引号+翻正 X，“Y… → “X，”Y…        行首漏开引号且该 “ 之后是
                                              旁白（≥4字）：补开 + 把中间
                                              那个倒置闭引号一并翻正

    D2/D3 共用「预算」：只有行内左引号确实多于右引号时才翻正，
    已平衡的行（合法嵌套强调 “外“内”外”）不进预算分支，天然免疫。

    D5 必须排在 D4 前：行尾就是缺一个闭引号时，直接补闭就行；
    若先补开引号会把「旁白＋新对话」误判成「对话＋旁白」。

    返回 (新文本, 修改行数)。
    """
    n = 0
    out = []
    for line in text.split("\n"):
        if DQ_L not in line or line.count(DQ_L) == line.count(DQ_R):
            out.append(line)
            continue
        orig = line
        for _ in range(8):
            bal = _balance(line)
            # D1 行首叠引
            if line.startswith(DQ_L + DQ_L):
                line = DQ_L + line.lstrip(DQ_L)
                continue
            # D6 行尾孤立开引号
            if bal >= 1 and line.endswith(DQ_L) and line[-2:-1] in tuple("。！？…，”"):
                line = line[:-1]
                continue
            if bal <= 0:
                break
            depths = _quote_depths(line)
            # D2/D3 合并：倒置强调对 与 句读后的倒置闭引号，取最靠左者。
            # 取最左很关键——「旁白＋新对话」与「对话＋旁白」在同一行相邻时
            # （…了。“她特意加重了“敬重”二字），只看形状两者都像倒置强调对，
            # 但真正该翻的是最左边那个句读后的引号。
            cand2 = _emph_positions(line, depths) if bal >= 2 else []
            cand3 = _inverted_close_positions(line, depths) if bal >= 2 else []
            cand = sorted(set(cand2) | set(cand3))
            if cand:
                line = _flip_at(line, cand[0])
                continue
            # D5 行尾补闭引号：仅当「最后一个引号是对话开场」（行首或紧跟句读），
            # 否则补出来的闭引号会落在错误的段尾
            if bal == 1 and line[-1] in "。！？…":
                last = line.rfind(DQ_L)
                if last == 0 or (last > 0 and line[last - 1] in "。！？…，：；"):
                    line = line + DQ_R
                    continue
            # D4 行首漏开引号（补开 + 翻正中间那个倒置闭引号）
            ok, pos = _missing_open_ok(line)
            if ok:
                line = DQ_L + _flip_at(line, pos)
                continue
            # D7 行首漏开引号（闭引号还在的情况）：行首是对话正文、
            # 行内第一个 ” 前面没有任何引号且该段以 ？！… 收尾
            # ——说明开引号在行首被吃掉了，补回去
            if bal == 1 and not line.startswith(DQ_L):
                q = line.find(DQ_R)
                if q > 0:
                    head = line[:q]
                    if (DQ_L not in head and "。" not in head
                            and head[-1] in "？！…"):
                        line = DQ_L + line
                        continue
            break
        if line != orig:
            n += 1
        out.append(line)
    return "\n".join(out), n


# ------------------------------------------------------------------
# P1 引号内外句末标点（2026-10 新增）
# ------------------------------------------------------------------

_QUOTE_PAIRS_OK = "：，。！？…；"
# 句末标点跑到闭合引号外面：”。 ！” ？”（后面不能再跟引号或句末标点）
_PERIOD_OUTSIDE = re.compile(
    DQ_R + r"([。！？]{1,2})(?![" + DQ_L + DQ_R + r"。！？])"
)
_QUOTE_ENDINGS = "。！？…"


def _quote_pairs(line):
    """返回 [(开引号位置, 闭引号位置)]，未配对的不返回。"""
    stack, pairs = [], []
    for i, ch in enumerate(line):
        if ch == DQ_L:
            stack.append(i)
        elif ch == DQ_R and stack:
            pairs.append((stack.pop(), i))
    return pairs


def _is_speech_lead(line, lpos):
    """开引号是否由言语直接引出：行首，或前面紧跟句读/冒号。

    只认「直接引出」是本规则的安全阀——`他说的“X”。` 这种引语作句子
    成分的写法不进入自动修复（其句号位置本身有争议，交人工）。
    """
    head = line[:lpos].rstrip()
    if not head:
        return True                     # 行首开引号 = 新对话
    return head[-1] in _QUOTE_PAIRS_OK


def fix_quote_period(text):
    """把跑到闭合引号外面的句末标点移回引号内（只做正向）。

    依据 GB/T 15834-2011：完整引用整句时，句末点号放在引号之内。

        他说：“我走了”。      → 他说：“我走了。”（句号移入）
        “我走了”？            → “我走了？”
        ：“我走了”。          → ：“我走了。”
        他说：“我走了！”。     → 他说：“我走了！”（删外面重复的句号）

    **为什么只做正向、不做反向**（这是本规则最重要的设计约束）：
    本文件的补闭约定（fix_empty_quote_pairs 的 E3/E4 附带补闭、
    fix_dangling_quotes 的 D5/D7）一律把 `”` 补在句读**之后**，
    产出 `。”`。若这里再做 `。”` → `”。` 的反向搬移，两股力量
    方向相反，在不动点循环里必然来回振荡（与注意事项 11「冒号后
    引号写反」同类型的坑）。因此反向情形（引语作句子成分却把句号
    写在引号内）只由 find_quote_period_suspects 报告，不改。

    **为什么可以放在不动点循环之后**：本规则只搬移标点位置，
    不增不减任何引号，因此不改变引号计数与逐行平衡，不会破坏
    循环已经收敛的平衡状态；同时它自身的产物（`。”`）不会再被
    任何后续规则改动，天然幂等。

    触发条件（同时成立才动）：
      1. 该 ” 由言语直接引出（行首 / 前接 ：，。！？…；）
      2. 引号内非空，跨度 ≤200 字
      3. 引号内末尾已有句末标点（。！？…）时，只删外面重复的那个，
         不搬移（避免 `“我……”。` → `“我……。”`）

    返回 (新文本, 修改处数)。
    """
    n = 0
    out_lines = []
    for line in text.split("\n"):
        # 从右往左处理，前面的位置就不会被后面的插删打乱
        for lpos, rpos in reversed(_quote_pairs(line)):
            m = _PERIOD_OUTSIDE.match(line, rpos)
            if not m:
                continue
            inner = line[lpos + 1:rpos]
            if not inner or len(inner) > 200:
                continue
            if not _is_speech_lead(line, lpos):
                continue
            tail = m.group(1)
            if inner[-1] in _QUOTE_ENDINGS:
                # 引号内已有句末标点 → 删掉外面重复的那个
                line = line[:m.start(1)] + line[m.end(1):]
            else:
                # 正向搬移：句末标点搬到 ” 之前
                line = (line[:rpos] + tail + line[rpos:m.start(1)]
                        + line[m.end(1):])
            n += 1
        out_lines.append(line)
    return "\n".join(out_lines), n


def find_quote_period_suspects(text):
    """只报告：引号内有句末标点、但引语疑作句子成分（反向可疑）。

    典型：他说的“我走了。”是气话。  ← 引语是句子成分，句号宜在引号外
    这类改法有争议（删除引号内标点等于删内容），一律不改，交人工。

    返回 [(行号, 原文片段)]。
    """
    suspects = []
    for ln, line in enumerate(text.split("\n"), 1):
        for lpos, rpos in _quote_pairs(line):
            if rpos + 1 >= len(line):
                continue
            nxt = line[rpos + 1]
            if nxt in _QUOTE_ENDINGS or nxt in "，；：、）":
                continue
            if not is_cjk(nxt):
                continue
            inner = line[lpos + 1:rpos]
            if inner and inner[-1] in _QUOTE_ENDINGS \
                    and not _is_speech_lead(line, lpos):
                suspects.append((ln, line.strip()[:40]))
                break
    return suspects


# ------------------------------------------------------------------
# P2 成对标点检查（书名号 / 各类括号，只报告不修改）
# ------------------------------------------------------------------

_SYMBOL_PAIRS = [
    ("《", "》", "书名号"),
    ("〈", "〉", "单书名号"),
    ("（", "）", "圆括号"),
    ("［", "］", "方括号"),
    ("〔", "〕", "六角括号"),
    ("「", "」", "直角引号"),
    ("『", "』", "直角双引号"),
    ("【", "】", "方头括号"),
]


def check_paired_symbols(text):
    """检查成对标点是否配对，**只报告不修改**。

    为什么不自动改：成对标点不成对时，正确做法可能是补、可能是删、
    也可能是把内容移出，规则无从判断；而 macro-correct 采用「不成对
    就整对删掉」的策略（见其 check_double），会直接毁掉正文。本实现
    只定位不动作。

    跨行配对（一行开、几行后闭）在小说里是合法排版（如书名号跨行、
    括号注跨段），所以按**全文**扫描，不逐行判断。

    返回 {名称: {"left": 左符号总数, "right": 右符号总数,
                 "extra_right": [多余右符号的行号],
                 "unclosed_left": [未闭合左符号的行号]}}
    全部正常时返回空 dict。
    """
    res = {}
    lines = text.split("\n")
    for lch, rch, name in _SYMBOL_PAIRS:
        stack, extra = [], []
        for ln, line in enumerate(lines, 1):
            for ch in line:
                if ch == lch:
                    stack.append(ln)
                elif ch == rch:
                    if stack:
                        stack.pop()
                    else:
                        extra.append(ln)
        left = text.count(lch)
        right = text.count(rch)
        if left != right or stack or extra:
            res[name] = {
                "left": left,
                "right": right,
                "extra_right": extra,
                "unclosed_left": list(stack),
            }
    return res


# ------------------------------------------------------------------
# 可选规则
# ------------------------------------------------------------------

def add_cjk_latin_spacing(text):
    """中英文之间补一个空格（默认关闭，--spacing 开启）。"""
    text, n1 = re.subn(r"([\u4e00-\u9fff])([A-Za-z0-9])", r"\1 \2", text)
    text, n2 = re.subn(r"([A-Za-z0-9])([\u4e00-\u9fff])", r"\1 \2", text)
    return text, n1 + n2


def trad_quotes_to_curly(text):
    """直角引号转弯引号（默认关闭，--trad-quotes 开启）：「」→“”，『』→‘’。"""
    text, n1 = re.subn(r"「([^」]*)」", lambda m: "\u201c" + m.group(1) + "\u201d", text)
    text, n2 = re.subn(r"『([^』]*)』", lambda m: "\u2018" + m.group(1) + "\u2019", text)
    return text, n1 + n2


# ------------------------------------------------------------------
# 空白清理
# ------------------------------------------------------------------

def cleanup_whitespace(text):
    """去行尾空格、压缩3个以上连续空行为2个。"""
    lines = text.split("\n")
    lines = [ln.rstrip() for ln in lines]
    text = "\n".join(lines)
    text, n = re.subn(r"\n{3,}", "\n\n", text)
    return text, n


# ------------------------------------------------------------------
# 行首标点禁则：续行合并 + 行首句号删除
# ------------------------------------------------------------------

# 章节标题行（合并时避开，别把标题和正文粘到一起）
_HEADING_LINE = re.compile(
    r"^第[0-9一二三四五六七八九十百千两]+[章节卷部回篇集]"
    r"|^(序|序章|序言|前言|引子|楔子|尾声|后记|番外)$"
)

# 行首出现即视为「上一行的续接」，合并到上一行末尾。
# 包含闭引号 ” ’：引语被换行拆断时，闭引号会落在下一行行首
# （如 `。”` / `”一声的…`），是续行不是新段落。
_MERGE_LEAD = "，！？；：、）】》」』”’"

# 行首破折号：后接正文才是续接（——他听不到的。）；整行只有破折号是
# 独立的中断/留白标记，不动
_DASH_LEAD = re.compile(r"^—{1,}(?!—*$)")


def _is_mergeable_lead(s):
    """行内容是否以「续接标点」开头（决定要不要合并到上一行）。"""
    if not s:
        return False
    if s[0] in _MERGE_LEAD:
        return True
    # 破折号开头且破折号后还有正文
    if _DASH_LEAD.match(s):
        return True
    return False


def fix_line_start_punct(text):
    """行首标点禁则自动修复。

    规则（经验决策，来自小说文本实践）：
      - 行首是 ，！？；：、）】》」』”’ 或「破折号+正文」：
        上一段与下一段明显是一句话（换行错位），合并为一行。
        上一行是空行 / 章节标题 / 分隔线时不合并。
        （闭引号 ” ’ 开头同理：引语被换行拆断，闭引号落在下一行行首）
      - 行首是 。（句号开头明显不对）：删除行首句号；
        删后整行空了就连行一起删掉。
      - 行首是 ……（省略号）：可能是作者刻意留白/分隔，保留不动。
      - 行首是 “（开引号）：是新对话的开头，不是禁则，不动。

    返回 (新文本, 合并行数, 删除句号数)。幂等。
    """
    lines = text.split("\n")
    out = []          # 输出缓冲（逐行堆叠，便于把续行并到上一行）
    n_merge = 0
    n_delete = 0
    for line in lines:
        s = line.strip()
        if not s:
            out.append(line)
            continue
        if _SEPARATOR_LINE.match(s):
            out.append(line)
            continue
        if _HEADING_LINE.match(s):
            out.append(line)
            continue

        # 行首句号：删除处理。
        # 例外：句号后紧跟闭引号/闭括号（如 。”）时，它是上一行被换行
        # 拆断的句尾，应合并回上一行而不是删除。
        if s[0] == "。":
            lead = len(s) - len(s.lstrip("。"))
            rest = s[lead:]
            if rest and rest[0] in "）”】》」』" and out:
                prev = out[-1].strip()
                if prev and not _HEADING_LINE.match(prev) and not _SEPARATOR_LINE.match(prev):
                    out[-1] = out[-1].rstrip() + s
                    n_merge += 1
                    continue
            n_delete += lead
            if not rest:
                continue  # 整行只剩句号，删掉整行
            line = line.replace(s, rest, 1)
            out.append(line)
            continue

        # 续接标点：与上一行合并
        if _is_mergeable_lead(s) and out:
            prev = out[-1].strip()
            if prev and not _HEADING_LINE.match(prev) and not _SEPARATOR_LINE.match(prev):
                out[-1] = out[-1].rstrip() + s
                n_merge += 1
                continue

        out.append(line)
    return "\n".join(out), n_merge, n_delete


# 报告用的「残留行首标点」：不含开引号 “（对话开头是正常排版），
# 不含已自动处理的项；剩下的主要是省略号开头等有意保留的情况
_LINEHEAD_PUNCT = "，。、；：？！）】》」…—”’"


def find_linehead_punct(text):
    """查找以标点开头的行（处理后仍残留的，如省略号开头，供报告）。"""
    issues = []
    for i, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if s and s[0] in _LINEHEAD_PUNCT:
            issues.append((i, s[:30]))
    return issues


def count_unbalanced_quotes(text):
    """栈配对统计无法配对的引号，返回 (未闭合左引号行号列表, 多余右引号行号列表)。"""
    lines = text.split("\n")
    stack = []          # (line_no, col)
    unmatched_right = []
    pos = 0
    lineno = 0
    for line in lines:
        lineno += 1
        for col, ch in enumerate(line):
            if ch == "\u201c":
                stack.append((lineno, col))
            elif ch == "\u201d":
                if stack:
                    stack.pop()
                else:
                    unmatched_right.append((lineno, col))
        pos += len(line) + 1
    return [ln for ln, _ in stack], [ln for ln, _ in unmatched_right]
