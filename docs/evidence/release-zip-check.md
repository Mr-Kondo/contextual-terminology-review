# リリース配布物(v0.1.0)の導入確認

実施日: 2026-10-17。すべて一時ディレクトリ(`<work>`)内。実ユーザーのホームには触れていない。

- 取得: `gh release download v0.1.0`(公開リリースの添付ファイル)
- zip の SHA-256: `6b0a23efed16e8a9a1923655fa827e18baf9ad2f13f88904a5d5867bb016068e`(リリースノート・ビルド時の値と一致)
- 内容: 17ファイル。展開物とリポジトリの `skill/contextual-terminology-review/` を `diff -r` で比較し、差が無いことを確認(リポジトリ側にだけ、Claude Code のサンドボックスが作る空の `.claude/` ディレクトリがあるが、追跡対象外で配布物にも入っていない)

## 展開したコピーでの実行(`<work>/home/.claude/skills/` と `.agents/skills/` に展開、`python3 -I` で実行)

| 手順 | 結果 |
|---|---|
| `check refs`(review-example.json と合成の資料登録簿) | 終了コード0、errors なし。出典一覧の行を出力 |
| `store init` → `record start` → `record finish` → `feedback add` | いずれも `verified: true` |
| `export`(共有許可なし) | 終了コード4で停止(未許可のまま書き出さない) |
| `store set-policy`(一時の仮の許可)→ `export` → `import` | 受理4・重複0・隔離0 |
| `check store`(保存先と取り込み先) | ok、問題0 |

## 導入ツールでの一巡(`tools/ctr_install.py`、展開物を `--source`、`--home` は一時ディレクトリ)

`install --target all --apply` → `verify`(4配置先とも ok)→ `update`(`noop`、変更なし)→ `uninstall --apply`(配置先が空になることを確認)。

## 確認していないこと

- zip には導入ツール(`tools/ctr_install.py`)と `INSTALL-ON-REMOTE.txt` が入っていない。後者は `package` コマンドが別ファイルとして出力するが、リリースには添付していない(次回の改善候補)
- 依存(pydantic)は実行したPythonに入っているものを使った。無い環境では導入手順の案内に従って入れる必要がある
- 別のPC・別のOSでの導入は未実施
