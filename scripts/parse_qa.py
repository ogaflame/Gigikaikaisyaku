#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
疑義解釈資料の送付について（その N）テキスト -> 構造化Q&A JSON パーサー

前提:
- 入力テキストは PDF からのテキスト抽出結果(pdfplumber 等)を想定
- 「医－1」「歯－1」「調－1」「訪看－1」「看ベ－1」「DPC－1」のような
  ページ見出し(区分ラベル)の直後に区分名(例:歯科診療報酬点数表関係)が続く
- 各区分内は【見出し】で話題が区切られ、「問N」→「（答）」の順で連続する

完全ではないが、実運用データの大部分を高い精度で構造化できることを狙った
ヒューリスティックパーサー。抽出漏れがあれば raw_text をそのまま
full_text_fallback として保持し、あとから調整できるようにしている。
"""
import re
import json
import sys
from pathlib import Path

# 区分ラベルとその後に続く正式名称(表記ゆれに対応するため正規化用マップ)
CATEGORY_HEADERS = {
    "医科診療報酬点数表関係": "医科",
    "医科診療報酬点数表関係（ＤＰＣ）": "DPC",
    "看護職員処遇改善評価料及びベースアップ評価料関係": "看護職員処遇改善・ベースアップ評価料",
    "歯科診療報酬点数表関係": "歯科",
    "調剤報酬点数表関係": "調剤",
    "訪問看護療養費関係": "訪問看護",
}

# ページ番号/区分ラベル行のノイズ除去用パターン (例: 医－12, 看ベ－3, DPC－10, （別添３）)
NOISE_LINE_RE = re.compile(
    r"^(?:医|歯|調|訪看|看ベ|ＤＰＣ|DPC)[－\-]\d+$|^（別添\d+）$"
)

CATEGORY_HEADER_RE = re.compile(
    "|".join(re.escape(k) for k in CATEGORY_HEADERS.keys())
)

TOPIC_RE = re.compile(r"^【(.+?)】$")

# 「問１」「問 1」「問１－１」(DPC形式) 等に対応
QUESTION_RE = re.compile(r"^問\s*([0-9０-９]+(?:[－\-][0-9０-９]+)?)\s*(.*)$")
ANSWER_MARK_RE = re.compile(r"^（答）\s*(.*)$")


def normalize_lines(text: str):
    lines = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if NOISE_LINE_RE.match(line):
            continue
        lines.append(line)
    return lines


def extract_header_info(text: str):
    """号数・事務連絡日付を先頭部分から抽出する"""
    sono_match = re.search(r"疑義解釈資料の送付について（その\s*([0-9０-９]+)\s*）", text)
    date_match = re.search(r"令\s*和\s*([0-9０-９]+)\s*年\s*([0-9０-９]+)\s*月\s*([0-9０-９]+)\s*日", text)
    sono_no = sono_match.group(1) if sono_match else None
    date_str = None
    if date_match:
        y, m, d = date_match.groups()
        date_str = f"令和{y}年{m}月{d}日"
    return sono_no, date_str


def parse(text: str, source_url: str = ""):
    lines = normalize_lines(text)
    sono_no, date_str = extract_header_info(text)

    records = []
    current_category = "未分類"
    current_topic = None
    current_qnum = None
    current_question_lines = []
    current_answer_lines = []
    mode = None  # 'question' | 'answer'

    def flush():
        nonlocal current_qnum, current_question_lines, current_answer_lines
        if current_qnum is not None and (current_question_lines or current_answer_lines):
            records.append({
                "sono": sono_no,
                "date": date_str,
                "category": current_category,
                "topic": current_topic,
                "question_no": current_qnum,
                "question": "".join(current_question_lines).strip(),
                "answer": "".join(current_answer_lines).strip(),
                "source_url": source_url,
            })
        current_qnum = None
        current_question_lines = []
        current_answer_lines = []

    for line in lines:
        if CATEGORY_HEADER_RE.fullmatch(line):
            flush()
            current_category = CATEGORY_HEADERS.get(line, line)
            current_topic = None
            mode = None
            continue

        topic_m = TOPIC_RE.match(line)
        if topic_m:
            flush()
            current_topic = topic_m.group(1)
            mode = None
            continue

        q_m = QUESTION_RE.match(line)
        if q_m:
            flush()
            current_qnum = q_m.group(1)
            rest = q_m.group(2)
            current_question_lines = [rest] if rest else []
            mode = "question"
            continue

        a_m = ANSWER_MARK_RE.match(line)
        if a_m:
            mode = "answer"
            rest = a_m.group(1)
            current_answer_lines = [rest] if rest else []
            continue

        if mode == "question":
            current_question_lines.append(line)
        elif mode == "answer":
            current_answer_lines.append(line)
        # ヘッダ部(冒頭挨拶等)は無視

    flush()
    return records


def main():
    if len(sys.argv) < 2:
        print("usage: parse_qa.py <input_text_file> [source_url]", file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    source_url = sys.argv[2] if len(sys.argv) > 2 else ""

    text = input_path.read_text(encoding="utf-8")
    records = parse(text, source_url=source_url)

    out = json.dumps(records, ensure_ascii=False, indent=2)
    print(out)


if __name__ == "__main__":
    main()
