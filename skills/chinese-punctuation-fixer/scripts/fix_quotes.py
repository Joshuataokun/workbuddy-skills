#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中文双引号错配自动纠错（引号配对修复模块）。

可独立运行，也可被 fix_punctuation.py 作为流水线一环调用。
修复策略（经过约 1.2 万行真实小说验证）：

1. 保护真嵌套强调行（引号序列 L L R R，如 "外"内"外"），不动。
2. 普通行做「逐行严格交替重排」：第 1、3、5... 个引号定为左 "，
   第 2、4、6... 个定为右 "。纠正绝大多数开闭颠倒。
3. 奇数引号行（漏写）按语义补引号：缺左优先在冒号后补，缺右在行尾补。

独立运行：
    python fix_quotes.py 输入.txt [输出.txt]

被调用：
    from fix_quotes import fix_text
    new_text, stats = fix_text(text)
"""

import os
import re
import sys

LEFT = "\u201c"   # "
RIGHT = "\u201d"  # "

# 行首 debris 引号（双开引号型）：“解说[：，]“言语
# 行首的 “ 是解说误加引号（debris），：，后的 “ 才是言语开引号。
# 若交给交替重排，第二个 “ 会被错翻成 ”（产生 ：” 倒置开引号）。
# 判定：行首 “ 与第二个 “ 之间无其他引号（有则是正常对话/嵌套，不动）。
_DEBRIS_HEAD = re.compile(
    r"^(\s*)" + LEFT + r"([^" + LEFT + RIGHT + r"]*?[：，])" + LEFT)


def fix_alternate(line):
    """智能交替重排：纠正开闭颠倒，同时保护言语引出开引号。

    规则（逐引号从左到右，期望方向从「左」开始交替）：
    - 「“」紧跟 ：， 之后 = 言语引出开引号，钉住保留（之后的引号期望闭）
    - 期望闭引号时遇到 「“」：若行内其后还有闭引号 → 上一段言语漏写
      闭引号，此 “ 是新开引号（保留，继续期望闭）；否则是倒置闭引号
      （翻正为 ”）
    - 其余按期望方向保持/翻转

    相比纯位置交替：不再把 「道：“」 这类正常开引号错翻成 ”（多段漏
    闭言语并存的行，纯位置交替会按奇偶位误翻）。
    """
    chars = list(line)
    qpos = [i for i, c in enumerate(chars) if c in (LEFT, RIGHT)]
    expect_left = True
    for idx, pos in enumerate(qpos):
        ch = chars[pos]
        prev = chars[pos - 1] if pos > 0 else ""
        if ch == LEFT and prev in "：，":
            expect_left = False  # 钉住言语引出开引号
            continue
        if expect_left:
            if ch != LEFT:
                chars[pos] = LEFT
            expect_left = False
        else:
            if ch == LEFT:
                # 期望闭却遇开：其后还有闭引号则是漏闭的新开引号，保留
                if any(chars[p] == RIGHT for p in qpos[idx + 1:]):
                    continue
                chars[pos] = RIGHT
            expect_left = True
    return "".join(chars)


def is_true_nested(line):
    """合法嵌套强调行判定：引号序列以 " 开头、" 结尾，且同时含 "" 和 ""。"""
    s = line.strip()
    seq = "".join(c for c in s if c in (LEFT, RIGHT))
    return (
        seq.startswith(LEFT)
        and seq.endswith(RIGHT)
        and (LEFT + LEFT) in seq
        and (RIGHT + RIGHT) in seq
    )


def is_continuation_line(line):
    """闭引号开头的行是上一行被拆断的引语续行（由行首禁则合并处理）。

    这类行不能在行首补左引号（会生成 “” 空引号），也不能做交替重排
    （会把行首闭引号错改成开引号，且二次执行又会补闭引号，破坏幂等）。
    """
    return line.lstrip()[:1] == RIGHT


def fix_odd_line(line):
    """奇数引号行（漏写）：缺左引号优先在冒号后补，缺右引号在行尾补。"""
    s = line
    nl = s.count(LEFT)
    nr = s.count(RIGHT)
    if nl == nr:
        return s
    if nl < nr:
        # 闭引号开头的续行：不补引号，原样留给行首禁则合并/人工
        if is_continuation_line(s):
            return s
        idx = s.find("\uff1a")  # 全角冒号
        if idx >= 0 and idx + 1 < len(s) and s[idx + 1] not in (LEFT, RIGHT):
            return s[: idx + 1] + LEFT + s[idx + 1:]
        lead = len(s) - len(s.lstrip())
        return s[:lead] + LEFT + s[lead:]
    trail = len(s.rstrip())
    return s[:trail] + RIGHT + s[trail:]


def fix_text(data):
    """修复整段文本中的双引号错配。返回 (新文本, 统计dict)。"""
    lines = data.split("\n")
    fixed = []
    stats = {"quote_flipped": 0, "quote_added": 0, "quote_removed": 0,
             "quote_odd_nested": []}

    for lineno, line in enumerate(lines, 1):
        old = line
        nested_look = is_true_nested(line)
        if not nested_look:
            # 行首 debris 引号（双开引号型）：行首 “ 与第二个 “ 之间无
            # 其他引号 → 行首的是 debris，删除后按奇数行正常补齐。
            # 真嵌套行（L L R R）受保护不动
            m = _DEBRIS_HEAD.match(line)
            if m:
                line = m.group(1) + m.group(2) + LEFT + line[m.end():]

        cnt = line.count(LEFT) + line.count(RIGHT)
        if cnt == 0:
            fixed.append(line)
            continue

        nested_look = is_true_nested(line)
        if nested_look and cnt % 2 == 0:
            new = line  # 合法嵌套，保护
        elif cnt % 2 == 0:
            new = fix_alternate(line)
        else:
            # 奇数引号行必然有漏写/错位，不可能是合法嵌套（嵌套成对出现），
            # 即使长得像嵌套也不保护，否则会留下永久的不平衡
            if is_continuation_line(line):
                # 闭引号开头的续行：原样保留（交给行首禁则合并或人工），
                # 重排会把闭引号错改成开引号且破坏幂等
                new = line
            elif (line.count(LEFT) > line.count(RIGHT)
                  and line.rstrip().endswith(RIGHT)):
                # 行尾已是闭引号：缺的是别处的开引号（如对话开了头没闭），
                # 行尾再补只会生成 ”” ，并被交替重排打回 “” 空引号（振荡）。
                # 原样保留，由未闭合引号报告暴露给人工
                new = line
            else:
                new = fix_alternate(fix_odd_line(line))
            if nested_look:
                stats["quote_odd_nested"].append(lineno)

        if new != old:
            na = old.count(LEFT) + old.count(RIGHT)
            nb = new.count(LEFT) + new.count(RIGHT)
            if nb > na:
                stats["quote_added"] += nb - na
            elif nb < na:
                stats["quote_removed"] += na - nb
            if len(old) == len(new):
                for ca, cb in zip(old, new):
                    if ca != cb and ca in (LEFT, RIGHT) and cb in (LEFT, RIGHT):
                        stats["quote_flipped"] += 1

        fixed.append(new)

    return "\n".join(fixed), stats


def fix_file(input_path, output_path=None):
    with open(input_path, encoding="utf-8") as f:
        data = f.read()
    newdata, _ = fix_text(data)
    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = base + "_已修正引号" + ext
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(newdata)
    return newdata.count(LEFT), newdata.count(RIGHT)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    if not os.path.exists(input_path):
        print(f"错误：文件不存在 {input_path}")
        sys.exit(1)
    nl, nr = fix_file(input_path, output_path)
    base, ext = os.path.splitext(input_path)
    out = output_path or (base + "_已修正引号" + ext)
    print("=" * 40)
    print("修复完成")
    print("=" * 40)
    print(f"输出文件：{out}")
    print("左引号 \u201c：%d  右引号 \u201d：%d  差：%d" % (nl, nr, nl - nr))
    if nl != nr:
        print("警告：左右引号仍不平衡，可能有漏写引号需人工复核。")


if __name__ == "__main__":
    main()
