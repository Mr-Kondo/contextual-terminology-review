# 用語・文脈レビュー（contextual-terminology-review）

[![CI](https://github.com/Mr-Kondo/contextual-terminology-review/actions/workflows/ci.yml/badge.svg)](https://github.com/Mr-Kondo/contextual-terminology-review/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> English: an agent Skill (Claude Code / Codex / Antigravity) that reviews how domain terms are used in context against cited sources, and proposes meaning-preserving rewrites. Experimental verification build — see the status below.

用語の専門的な適合、文脈に合う意味、相手への伝わりやすさを、資料に照らして確認し、本人の意図と確認済み事実を保った修正案・口頭の言い直しを返すSkillの検証版。設計資料第3版（`00-START-HERE.md` 以降）に基づく実装。**完成品・導入済み・効果測定済みではない**（状態は `docs/ACCEPTANCE-REPORT.md`）。

| 知りたいこと | 見る場所 |
|---|---|
| 使い方・導入・更新・削除・週次の手順 | [docs/USAGE.md](docs/USAGE.md) |
| 実装の判断、既存Skill調査の採否、依存と版、未実施 | [docs/IMPLEMENTATION-NOTES.md](docs/IMPLEMENTATION-NOTES.md) |
| 受入検査の結果（機械検査・意味審査・実呼び出しを別表示） | [docs/ACCEPTANCE-REPORT.md](docs/ACCEPTANCE-REPORT.md) |
| 意味審査の確認票（独立した確認者向け） | [docs/SEMANTIC-REVIEW-SHEET.md](docs/SEMANTIC-REVIEW-SHEET.md) |
| Ruri検索の採否判断（合成データ＋公開された実文章） | [docs/RURI-ADOPTION.md](docs/RURI-ADOPTION.md) |
| 自分のデータでRuriを確認する手順 | [docs/RURI-REAL-DATA-GUIDE.md](docs/RURI-REAL-DATA-GUIDE.md) |
| 効果測定の手順（人による測定と、模擬の受け手による予備試験） | [docs/EFFECT-MEASUREMENT.md](docs/EFFECT-MEASUREMENT.md) |
| 発動精度の評価（descriptionが使うべき依頼で選ばれるか） | [docs/TRIGGER-EVAL.md](docs/TRIGGER-EVAL.md) |
| E2E評価（初見の課題で、Skillありと素のモデルの最終出力を比較） | [docs/E2E-EVAL.md](docs/E2E-EVAL.md) |
| 利用環境ごとの成功・失敗・未実施 | [docs/HOST-EVIDENCE.json](docs/HOST-EVIDENCE.json)（実呼び出しの記録: `docs/evidence/real-host-*.md`） |
| Skill本体 | [skill/contextual-terminology-review/](skill/contextual-terminology-review/SKILL.md) |

```bash
python3 -m unittest discover -s tests          # 機械検査（標準ライブラリ＋pydantic。CIでも同じものを実行）
python3 tools/ctr_install.py install --target all --scope user   # 計画の表示のみ。変更は --apply を付けたときだけ
```

設計資料（`00`〜`07`・`manifest.json`）は、公開にあたりホームディレクトリ名を含むローカルパスを `~` に置換した2点（04・07）以外は変更していない（`manifest.json` の `revision_note` 参照）。実データ・評価正解・ログはSkillにも本リポジトリにも含めない（保存先は利用者が決める）。

ライセンス: [MIT](LICENSE)。依存（pydantic: MIT、pdfplumber: MIT、sentence-transformers: Apache-2.0）とRuriモデル（Apache-2.0）は各ライセンスに従う。
