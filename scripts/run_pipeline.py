#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自動更新パイプライン本体。GitHub Actions から定期実行される想定。

流れ:
1. scrape_list.fetch_links() で最新のPDFリンク一覧を取得
2. 直前にコミットされている data/links.json と比較し、新規/変更されたURLを抽出
3. 新規/変更分のPDFをダウンロードし、pdfplumber でテキスト抽出
4. parse_qa.parse() で構造化
5. 号(sono)ごとに data/manifest/sonoN.json として保存
6. すべてのmanifestを合算して site/qa.json を再生成
7. data/links.json を最新の内容で更新

このスクリプトはネットワークアクセスを必要とする(GitHub Actions実行環境で行う)。
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from scrape_list import fetch_links  # noqa: E402
from parse_qa import parse  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LINKS_PATH = ROOT / "data" / "links.json"
MANIFEST_DIR = ROOT / "data" / "manifest"
RAW_TEXT_DIR = ROOT / "data" / "raw_text"
SITE_QA_PATH = ROOT / "site" / "qa.json"

MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
RAW_TEXT_DIR.mkdir(parents=True, exist_ok=True)


def load_previous_links():
    if LINKS_PATH.exists():
        return json.loads(LINKS_PATH.read_text(encoding="utf-8"))
    return []


def extract_pdf_text(pdf_bytes: bytes) -> str:
    import pdfplumber
    import io

    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


def safe_filename(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def main():
    previous = load_previous_links()
    previous_by_url = {p["url"]: p for p in previous}

    current = fetch_links()

    new_or_changed = [
        item for item in current
        if item["url"] not in previous_by_url
    ]

    print(f"検出: 全 {len(current)} 件中 {len(new_or_changed)} 件が新規/未処理です。")

    for item in new_or_changed:
        url = item["url"]
        fname = safe_filename(url)
        raw_txt_path = RAW_TEXT_DIR / (fname.replace(".pdf", ".txt"))

        print(f"取得中: {url}")
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()

        text = extract_pdf_text(resp.content)
        raw_txt_path.write_text(text, encoding="utf-8")

        records = parse(text, source_url=url)
        manifest_path = MANIFEST_DIR / f"sono{item['sono']}.json"

        # 同じ号のPDFが複数(訂正等)ある場合は上書きではなくマージすることも検討可能。
        # ここでは単純化のため、同号の既存分がなければ新規保存、あれば追記する。
        existing = []
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        merged = existing + records
        manifest_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  -> {len(records)} 件のQ&Aを {manifest_path} に保存しました。")

    # 全体のqa.jsonを再構築
    all_records = []
    for manifest_file in sorted(MANIFEST_DIR.glob("sono*.json")):
        all_records.extend(json.loads(manifest_file.read_text(encoding="utf-8")))

    SITE_QA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SITE_QA_PATH.write_text(
        json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"合計 {len(all_records)} 件のQ&Aを {SITE_QA_PATH} に書き出しました。")

    # links.json を更新
    LINKS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
