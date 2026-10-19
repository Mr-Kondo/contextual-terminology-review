# 用語・文脈レビュー（contextual-terminology-review）

[![CI](https://github.com/Mr-Kondo/contextual-terminology-review/actions/workflows/ci.yml/badge.svg)](https://github.com/Mr-Kondo/contextual-terminology-review/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> English: an agent Skill (Claude Code / Codex / Antigravity) that reviews how domain terms are used in context against cited sources, and proposes meaning-preserving rewrites. Experimental verification build — see the status below.

## このSkillについて

用語の専門的な適合、文脈に合う意味、相手への伝わりやすさを、資料に照らして確認するSkillの検証版。返すのは、本人の意図と確認済み事実を保った修正案と、口頭の言い直し。初期の設計資料（第3版。`00`〜`07`）に基づく実装である。設計資料は、タグ v0.1.11 または git の履歴で読める。

**完成品・導入済み・効果測定済みではない。** 状態は [docs/ACCEPTANCE-REPORT.md](docs/ACCEPTANCE-REPORT.md) を見る。

## まず試す

```bash
python3 -m unittest discover -s tests          # 機械検査（標準ライブラリ＋pydantic。CIでも同じものを実行）
python3 tools/ctr_install.py install --target all --scope user --dry-run   # 計画の表示のみ。--dry-run を外すと配置する
```

Windows（PowerShell）では `python3` を `py -3` に、パスの `/` を `\` に読み替える。導入の手順と、Mac との書き方の違いは [docs/INSTALL.md](docs/INSTALL.md) にある。

続きは [docs/USAGE.md](docs/USAGE.md) の「全体の流れ」を見る。

## ドキュメント

### 使う

| 知りたいこと | 見る場所 |
|---|---|
| 使い方の入口、初回の依頼、発動のしやすさ | [docs/USAGE.md](docs/USAGE.md) |
| 保存先の決め方と初期化 | [docs/SETUP.md](docs/SETUP.md) |
| 導入・更新・削除、ChatGPT Work / Claude Cowork への登録 | [docs/INSTALL.md](docs/INSTALL.md) |
| 週次の手順、記録の集め方、更新案の採用 | [docs/WEEKLY.md](docs/WEEKLY.md) |
| 検査の実行、意味審査の依頼 | [docs/CHECKS.md](docs/CHECKS.md) |

### 評価と結果

| 知りたいこと | 見る場所 |
|---|---|
| 受入検査の結果（機械検査・意味審査・実呼び出しを別表示） | [docs/ACCEPTANCE-REPORT.md](docs/ACCEPTANCE-REPORT.md) |
| 意味審査の確認票（独立した確認者向け） | [docs/SEMANTIC-REVIEW-SHEET.md](docs/SEMANTIC-REVIEW-SHEET.md) |
| 効果測定の手順（人による測定と、模擬の受け手による予備試験） | [docs/EFFECT-MEASUREMENT.md](docs/EFFECT-MEASUREMENT.md) |
| 発動精度の評価（descriptionが使うべき依頼で選ばれるか） | [docs/TRIGGER-EVAL.md](docs/TRIGGER-EVAL.md) |
| E2E評価（初見の課題で、Skillありと素のモデルの最終出力を比較） | [docs/E2E-EVAL.md](docs/E2E-EVAL.md) |
| 利用環境ごとの成功・失敗・未実施 | [docs/HOST-EVIDENCE.json](docs/HOST-EVIDENCE.json)（実呼び出しの記録: `docs/evidence/real-host-*.md`） |

### 設計と実装

| 知りたいこと | 見る場所 |
|---|---|
| リリースの手順(自動化、ノートの置き場所) | [docs/RELEASING.md](docs/RELEASING.md) |
| 受入の区分(A01〜A48の合格に要る証拠の種類) | [docs/ACCEPTANCE-MATRIX.md](docs/ACCEPTANCE-MATRIX.md) |
| 記録・収集・比較・削除の仕様 | [docs/FEEDBACK-AND-STORAGE.md](docs/FEEDBACK-AND-STORAGE.md) |
| 実装の判断、既存Skill調査の採否、依存と版、未実施 | [docs/IMPLEMENTATION-NOTES.md](docs/IMPLEMENTATION-NOTES.md) |
| Ruri検索の採否判断（合成データ＋公開された実文章） | [docs/RURI-ADOPTION.md](docs/RURI-ADOPTION.md) |
| 自分のデータでRuriを確認する手順 | [docs/RURI-REAL-DATA-GUIDE.md](docs/RURI-REAL-DATA-GUIDE.md) |
| Skill本体 | [skill/contextual-terminology-review/](skill/contextual-terminology-review/SKILL.md) |

## データの扱い

- 実データ・評価正解・ログは、Skillにも本リポジトリにも含めない。保存先は利用者が決める。

## ライセンス

[MIT](LICENSE)。依存とRuriモデルは、各ライセンスに従う。

- pydantic: MIT
- pdfplumber: MIT
- sentence-transformers: Apache-2.0
- Ruriモデル: Apache-2.0
