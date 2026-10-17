# 参照記録と出典一覧

## 流れ

review.json（判断と参照記録）→ `ctr.py check refs --review review.json --sources sources.json` → 検査結果と出典一覧。出典一覧は検査した参照記録から生成する。手で書き足さない。`--footer-only` で一覧の行だけを出せる。

## sources.json（資料登録簿）

`{"sources": [ {id, title, version, kind: text|pdf|image, lines: [...] | page_text: {"1": "..."} , pages, figures: {"図1": {page, regions: [...]}}, text_origin: original|machine_text|ocr|manual, copy_of, relation: copy|translation|summary, link, sha256} ]}`

- `lines` の先頭が行1。資料の本文が変わると `sha256` が合わなくなり、`source_hash_mismatch`（再確認候補）になる。ハッシュの変化から意味が反転したとは断定しない。
- PDFは `ctr.py pdf extract` で作る。誌面ページ番号は抽出できないので空のまま（補わない）。
- `link` は利用者が開ける元ファイルまたはURL。抽出用の一時ファイルをリンクにしない。無ければ「リンク未確認」と表示される。

## review.json

`Review`（`scripts/ctr_refs.py`）に従う。要点:

- `findings[]`: `id`, `target`, `judgment`（confirmed/provisional/pending）、4軸、`reason`, `proposal_text`, `oral_rephrase`, `ref_ids`, 必要なら `correction`
- `refs[]`: `ref_id`, `finding_ids`, `basis`（source / user_statement）, `source_id`, `version`, `mode`（direct_quote / summary / inference）, `location`, `quote`（直接引用のみ）, `used_content`（要約・推論）, `elided`, `visual_check`
- `semantic_reviews[]`: 人が書く意味適合の記録（reviewer, independent, verdict, reason, date）。ツールは自動で埋めない。

例は `references/review-example.json`。

## 場所の書き方

- テキスト: `{"kind":"lines","start":2,"end":2}`（確認した版の行番号）
- PDF: `{"kind":"pdf_page","page":1,"printed_page":"iii"}`。ページ番号（PDFの何枚目）と誌面番号を区別する。
- 図: `{"kind":"figure","page":1,"figure":"図1","region":"右上の凡例"}`。座標は確認できたものだけ `bbox` に入れる。
- 図中の文字の引用（direct_quote）と、矢印・配置から読み取った内容（inference）を分ける。画像は `visual_check` が `agent_viewed` / `human_viewed` でなければ `needs_visual`（確認済みにしない）。

## 検査（機械検査）の誤りクラス

`unknown_source_id`（未登録）/ `source_version_mismatch`（版違い）/ `location_out_of_range`（範囲外）/ `location_missing` / `quote_mismatch`（改変・否定の欠落・要約を直接引用にした記録）/ `quote_missing` / `mode_content_missing` / `source_hash_mismatch` / `visual_check_missing`。

- 引用の一致は、空白と改行だけ緩める。非ASCII文字どうしの間の改行は除き、それ以外の連続空白は半角空白1つにする。NFKCなどの正規化はしない（`m/s²` が `m/s2` に化けるため）。語・数値・単位・否定を変えて一致にしない。
- 省略引用は `elided: true` とし、`…` か `[...]` で区切る。各断片が元の範囲に順に現れる必要がある。
- 判断が `confirmed` でも、合格した資料の参照がなければ `needs_confirmation` に下げられる（`unsupported_confirmed_judgment`）。本人の説明は意図の根拠として表示できるが、専門的適合の確定根拠にはならない。

## 警告（`warnings`。エラーではない確認候補）

- `proposal_adds_protected_term`: 修正案（`proposal_text`・`oral_rephrase`）に、承認・決裁・合意・確定・保証・責任・完了・最終判断の語があり、原文・目的・本人の意図・確認済み事実・紐づく引用のどこにも無い。語が資料にあるなら、その引用を紐づける。無ければ修正案から外す。
- `surrounding_condition_unaddressed`: 引用の前後2行か直近の見出しに、草案・旧版・失効・未合意・暫定・改定・ただし・除く・例外などがあり、引用・理由・修正案に出てこない。適用範囲や文書の状態が引用と違わないか確認し、違うなら理由か確認点に書く。
- 警告は語の有無だけを見る。言い換え（例: 「承認」を「了解」と書く）は拾えない。警告が無いことは、意味が保たれている証拠ではない。

## 機械検査では分からないこと

構造と文字列が合っても、引用が判断を支えるとは限らない（例: 「最終承認は部長が行う」は引用として正しいが「私が最終承認する」を支えない）。この判断は人または独立した確認者が `semantic_reviews` に残す。出力には `mechanical` と `semantic`（not_run / supports / does_not_support / unclear）を別に出す。
