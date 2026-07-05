#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
疑義解釈資料の送付について（その N）テキスト -> 構造化Q&A JSON パーサー
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

ZEN_TO_HAN = str.maketrans("０１２３４５６７８９", "0123456789")


def main_number(qnum: str):
    head = qnum.translate(ZEN_TO_HAN).replace("－", "-").split("-")[0]
    try:
        return int(head)
    except ValueError:
        return None


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


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """
    PDFからテキストを抽出する。各ページの直前に "__PAGE__N__" という
    目印行を挿入しておくことで、parse_qa.py 側でどの問がPDFの何ページ目に
    あったかを追跡できるようにする(検索サイトから原文の該当ページへ
    直接リンクするために使用)。
    """
    import pdfplumber
    import io

    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text_parts.append(f"__PAGE__{i}__")
            text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


def parse(text: str, source_url: str = ""):
    lines = normalize_lines(text)
    sono_no, date_str = extract_header_info(text)

    records = []
    current_category = "未分類"
    current_topic = None
    current_qnum = None
    current_question_lines = []
    current_answer_lines = []
    mode = None
    last_main_num = None

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
                if candidate_num is not None:
                    last_main_num = candidate_num
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
