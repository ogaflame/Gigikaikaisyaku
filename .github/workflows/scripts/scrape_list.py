#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
厚労省「令和８年度診療報酬改定について」ページから
「疑義解釈資料の送付について（そのN）」等のPDFリンク一覧を取得する。

出力: data/links.json
  [
    {"sono": "1", "title": "...", "date": "...", "url": "https://...pdf"},
    ...
  ]

GitHub Actions からの定期実行を想定。実行の都度この一覧を作り直し、
前回コミット時点の links.json と比較することで新規/更新PDFを検出する
(差分検出は run_pipeline.py 側で行う)。
"""
import re
import json
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PAGE_URL = "https://www.mhlw.go.jp/stf/newpage_67729.html"

# 「疑義解釈資料の送付について（そのN）」及びその訂正等を対象とする
TARGET_RE = re.compile(r"疑義解釈資料の送付について（その\s*([0-9０-９]+)\s*）")
DATE_RE = re.compile(r"令\s*和\s*([0-9０-９]+)\s*年\s*([0-9０-９]+)\s*月\s*([0-9０-９]+)\s*日")


def fetch_links(page_url: str = PAGE_URL):
    resp = requests.get(page_url, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    results = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        m = TARGET_RE.search(text)
        if not m:
            continue
        # 「一部訂正」等の別ページ通知は対象外(単体のその N 本体のみ)にしたい場合はここで除外可能
        sono_no = m.group(1)
        date_m = DATE_RE.search(text)
        date_str = None
        if date_m:
            y, mo, d = date_m.groups()
            date_str = f"令和{y}年{mo}月{d}日"

        href = a["href"]
        if href.startswith("/"):
            href = "https://www.mhlw.go.jp" + href

        results.append({
            "sono": sono_no,
            "title": text,
            "date": date_str,
            "url": href,
        })

    # 重複除去(同一URL)
    seen = set()
    deduped = []
    for r in results:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        deduped.append(r)

    return deduped


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/links.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    links = fetch_links()
    out_path.write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(links)} 件のリンクを {out_path} に書き出しました。")


if __name__ == "__main__":
    main()
