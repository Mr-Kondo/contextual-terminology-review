# 利用環境ごとの扱い

共通: 判断・データ・スクリプトは同じ。登録、呼び出し、資料参照、スクリプト実行、保存は環境ごとに確認し、ファイルを置いただけで「呼び出せた」「記録が有効」とは言わない。ホストのフックや履歴形式は仮定しない。

| 環境 | 配置（tools/ctr_install.py） | 注意 |
|---|---|---|
| Claude Code | user: `~/.claude/skills/` / workspace: `.claude/skills/` | CLIの配置。Coworkとは別 |
| Codex | user: `~/.agents/skills/` / workspace: `.agents/skills/` | 配置先は実装時に公式資料で再確認する |
| Gemini Antigravity | IDE: `~/.gemini/config/skills/` / CLI: `~/.gemini/antigravity-cli/skills/` / workspace: `.agents/skills/` | IDEとCLIで場所が違う |
| ChatGPT Work | 配布物（zip）をアカウント側で登録 | ローカル配置では代用できない。登録・接続方法は利用先の公式手順 |
| Claude Cowork | 配布物（zip）をアカウントのSkillとして有効化 | PC上の `~/.claude/skills/` を直接読む方式ではない（2026-10-14確認の公式説明）。ローカル配置だけで導入完了としない |
| リモート | `ctr_install.py package` の配布物を移し、対象ホストで実行 | 接続・権限がなければ未実施 |

Windows では、`python3` を `py -3`（なければ `python`）に、パスの区切りを `\` に読み替える。保存先の絶対パスはドライブ文字から書く（`/` で始まるパスは絶対パスと見なされない）。

アカウント側（Work/Cowork）の登録・置換・削除は、このSkillのスクリプトでは操作しない。配布物と手順を示し、未実施と書く。

## 実行できない・保存できない環境

スクリプトを実行できない、または永続領域がない場合:

1. 「検査・記録は未実施（理由）」と書く。検査済みの出力を作らない。
2. 手動の記録票を出す: 実行日時、環境、モデル、Skillの版、対象（原文の保存可否に従う）、指摘ID、4軸、参照、フィードバック4項目。保存先は利用者が決める。
3. 消失リスク（一時環境）を伝え、終了前に `ctr.py export` するか、記録票を永続領域へ移す手順を案内する。
4. 自動送信・常駐処理は設定しない。
