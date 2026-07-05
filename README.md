# 疑義解釈資料 横断検索サイト（プロトタイプ）

厚生労働省「令和８年度診療報酬改定について」ページに掲載される
「疑義解釈資料の送付について（その１〜）」を、問・答単位で自動収集し、
検索できる静的サイトを生成する一式です。

## 構成

```
.
├── scripts/
│   ├── scrape_list.py   # MHLWページから疑義解釈資料PDFのリンク一覧を取得
│   ├── parse_qa.py      # PDFテキスト → 問/答単位のJSONへ変換するパーサー
│   └── run_pipeline.py  # 上記を組み合わせた自動更新パイプライン本体
├── data/
│   ├── links.json       # 直近に検出済みのPDFリンク一覧(差分検出の基準)
│   ├── raw_text/        # PDFから抽出した生テキスト(デバッグ・再パース用)
│   └── manifest/        # 号(その1, その2, ...)ごとの構造化Q&A JSON
├── site/
│   ├── index.html       # 検索UI(クライアントサイドJS、ビルド不要)
│   └── qa.json          # 全号を統合した検索対象データ
├── requirements.txt
└── .github/workflows/update.yml   # 自動更新 & GitHub Pages デプロイ
```

## 現在の状態について

このリポジトリの `data/manifest/` および `site/qa.json` は、
**その１・その２の一部を使った動作確認用サンプルデータ**です
（このプロトタイプを作成した環境からは MHLW サイトへの直接アクセスができなかったため）。

実際に全号（その１〜９、以後の号も含む）を反映するには、下記の「初回セットアップ」を行い、
GitHub Actions 上でパイプラインを一度実行してください（Actions にはネットワークアクセスがあります）。

## 初回セットアップ

1. このフォルダの中身をそのまま新しい GitHub リポジトリにコミット・push する
2. リポジトリの **Settings → Pages** で、Source を「GitHub Actions」に設定する
3. **Actions** タブから `Update Gikai Kaishaku Data` ワークフローを一度手動実行する（`workflow_dispatch`）
   - これにより、MHLWページを実際にスクレイピングし、その１〜９すべてのPDFを取得・構造化し、
     `site/qa.json` が全件分に更新されて、GitHub Pages にデプロイされます
4. 以降は毎日自動実行され、新しい号（その10, その11, ...）が公開されると自動的に取り込まれます

## 更新頻度・タイミングの変更

`.github/workflows/update.yml` の `cron` の値を変更してください。
例: 1日3回にしたい場合は `cron: "0 0,8,16 * * *"` のようにします。

## パーサーの精度について

`parse_qa.py` は、以下の実際のPDF構造を前提にしたヒューリスティックパーサーです。

```
医科診療報酬点数表関係       <- 区分の見出し
【○○加算】                  <- 話題(トピック)の見出し
問１ ...                    <- 質問
（答）...                   <- 回答
```

大部分のケースで正しく抽出できることを確認していますが、まれにPDFのレイアウト崩れ
（表・図中心のページ、特殊な改行等）で取りこぼしが生じる可能性があります。
`data/raw_text/` に生テキストを保存しているので、取りこぼしを見つけた場合は
そのテキストを見ながら `parse_qa.py` の正規表現を調整してください。

## 検索サイトの使い方

`site/index.html` を開くと（GitHub Pages経由、もしくはローカルで簡易サーバ越しに）、
- キーワードでの全文検索(問・答・トピックが対象、AND検索)
- 「その◯」号数での絞り込み
- 区分(医科・歯科・調剤・訪問看護・DPC・看護職員処遇改善等)での絞り込み
- 各カードから原文PDFへのリンク

ができます。サーバーもDBも不要で、GitHub Pagesの無料枠だけで運用できます。

## ローカルでの動作確認

```bash
pip install -r requirements.txt
python scripts/run_pipeline.py   # 実際にMHLWへアクセスして全件取得・更新
cd site && python -m http.server 8000
# ブラウザで http://localhost:8000 を開く
```
[README.md](https://github.com/user-attachments/files/29670387/README.md)
