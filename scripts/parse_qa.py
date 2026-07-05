#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
疑義解釈資料の送付について（その N）テキスト -> 構造化Q&A JSON パーサー

前提:
- 入力テキストは PDF からのテキスト抽出結果(pdfplumber 等)を想定
- extract_pdf_text() がページの境界に "__PAGE__N__" という目印行を
  挿入している(Nはそのページのページ番号、1始まり)
- 「医－1」「歯－1」「調－1」「訪看－1」「看ベ－1」「DPC－1」のような
  ページ見出し(区分ラベル)の直後に区分名(例:歯科診療報酬点数表関係)が続く
- 各区分内は【見出し】で話題が区切られ、「問N」→「（答）」の順で連続する

完全ではないが、実運用データの大部分を高い精度で構造化できることを狙った
ヒューリスティックパーサー。
"""
import re
import json
import sys
from pathlib import Path

CATEGORY_HEADERS = {
    "医科診療報酬点数表関係": "医科",
    "医科診療報酬点数表関係（ＤＰＣ）": "DPC",
    "看護職員処遇改善評価料及びベースアップ評価料関係": "看護職員処遇改善・ベースアップ評価料",
    "歯科診療報酬点数表関係": "歯科",
    "調剤報酬点数表関係": "調剤",
    "訪問看護療養費関係": "訪問看護",
}

NOISE_LINE_RE = re.compile(
    r"^(?:医|歯|調|訪看|看ベ|ＤＰＣ|DPC)[－\-]\d+$|^（別添\d+）$"
)

CATEGORY_HEADER_RE = re.compile(
    "|".join(re.escape(k) for k in CATEGORY_HEADERS.keys())
)

TOPIC_RE = re.compile(r"^【(.+?)】$")
QUESTION_RE = re.compile(r"^問\s*([0-9０-９]+(?:[－\-][0-9０-９]+)?)\s*(.*)$")
ANSWER_MARK_RE = re.compile(r"^（答）\s*(.*)$")

# extract_pdf_text() がページ境界に挿入する目印 (例: __PAGE__3__ = PDFの3ページ目の開始)
PAGE_MARK_RE = re.compile(r"^__PAGE__(\d+)__$")

ZEN_TO_HAN = str.maketrans("０１２３４５６７８９", "0123456789")


def main_number(qnum: str):
    """「１－１」→ 1、「１２」→ 12 のように、比較用の先頭番号(int)を取り出す"""
    head = qnum.translate(ZEN_TO_HAN).replace("－", "-").split("-")[0]
    try:
        return int(head)
    except ValueError:
        return None


def normalize_lines(text: str):
    """
    戻り値: (kind, value) のリスト
      kind == 'page' -> value はページ番号(int)
      kind == 'line' -> value はテキスト行(str)
    """
    items = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        page_m = PAGE_MARK_RE.match(line)
        if page_m:
            items.append(("page", int(page_m.group(1))))
            continue
        if NOISE_LINE_RE.match(line):
            continue
        items.append(("line", line))
    return items


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
    items = normalize_lines(text)
    sono_no, date_str = extract_header_info(text)

    records = []
    current_category = "未分類"
    current_topic = None
    current_qnum = None
    current_question_lines = []
    current_answer_lines = []
    mode = None  # 'question' | 'answer'
    last_main_num = None  # 現在の区分内で直前に確定した問番号(比較用int)
    current_page = 1
    question_start_page = 1

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
                "page": question_start_page,
            })
        current_qnum = None
        current_question_lines = []
        current_answer_lines = []

    for kind, value in items:
        if kind == "page":
            current_page = value
            continue

        line = value

        if CATEGORY_HEADER_RE.fullmatch(line):
            flush()
            current_category = CATEGORY_HEADERS.get(line, line)
            current_topic = None
            mode = None
            last_main_num = None
            continue

        topic_m = TOPIC_RE.match(line)
        if topic_m:
            flush()
            current_topic = topic_m.group(1)
            mode = None
            continue

        q_m = QUESTION_RE.match(line)
        if q_m:
            candidate_num = main_number(q_m.group(1))
            # 過去の号を参照する文中に「問４」等が偶然行頭に来て
            # 誤って新しい問として認識されるのを防ぐ:
            # 問番号は同一区分内で後退しない、というルールで弾く。
            is_backwards = (
                candidate_num is not None
                and last_main_num is not None
                and candidate_num < last_main_num
            )
            if not is_backwards:
                flush()
                current_qnum = q_m.group(1)
                rest = q_m.group(2)
                current_question_lines = [rest] if rest else []
                mode = "question"
                question_start_page = current_page
                if candidate_num is not None:
                    last_main_num = candidate_num
                continue
            # 後退している場合は新しい問として扱わず、下の通常テキスト処理に落とす

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
