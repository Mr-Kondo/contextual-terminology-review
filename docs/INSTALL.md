# 導入・更新・アンインストール

[使い方の入口](USAGE.md)の手順2。操作には `tools/ctr_install.py` を使う。

既定は**計画の表示だけ**である。操作・配置先・変更点を確認してから `--apply` を付ける。

## 配置先

| 環境 | user（ホーム） | workspace（プロジェクト） | 公式資料での確認（2026-10-17） |
|---|---|---|---|
| Claude Code | `~/.claude/skills/` | `.claude/skills/` | code.claude.com/docs/en/skills |
| Codex | `~/.agents/skills/` | `.agents/skills/` | developers.openai.com/codex/skills |
| Antigravity IDE/App | `~/.gemini/config/skills/` | `.agents/skills/` | antigravity.google/docs/skills |
| Antigravity CLI | `~/.gemini/antigravity-cli/skills/` | `.agents/skills/` | 同上 |

## コマンド

```bash
python3 tools/ctr_install.py install   --target claude-code --scope user            # 計画の表示（変更なし）
python3 tools/ctr_install.py install   --target claude-code --scope user --apply
python3 tools/ctr_install.py update    --target all --scope user --apply            # all = claude-code, codex, antigravity-ide, antigravity-cli
python3 tools/ctr_install.py verify    --target codex --scope user                  # 正本との照合
python3 tools/ctr_install.py uninstall --target antigravity --scope user --apply    # このSkillのフォルダだけを削除
```

## 既存のSkillとの衝突

配置したSkillには、`.ctr-install.json`（版と全ファイルのsha256）が付く。

- これが無い同名のものは、「識別できない既存」として扱う。上書きも削除もしない。`--on-conflict backup` を付けると、退避してから置換する
- 導入後に手で編集したファイルがある場合も同じ

## 更新

更新は、次の順に進む。途中で失敗したら、旧版に戻る。

1. 新版を一時領域に作る
2. 旧版を `skills.bak/` へ退避する
3. 置換する
4. 照合する

更新後は、用語データと索引の版を確認する。索引が古ければ作り直す。

```bash
ctr.py check data --improvement-root ABS [--index-meta PATH]
```

## アンインストール

消すのは、当該Skillのフォルダだけである。原資料・用語正本・評価履歴・ログ・他のSkillには触れない。これらはSkillフォルダの外に置く設計である。データの削除は別の操作（`ctr.py delete plan/apply`）で行う。

## 別の場所への配置と配布

- 他のホームや別の作業領域を試すには、`--home DIR`、`--workspace DIR`、`--dest DIR` を使う
- リモートでは、対象ホストで同じスクリプトを実行する
- `package` で配布物を作れる

```bash
python3 tools/ctr_install.py package --out dist/     # zip と INSTALL-ON-REMOTE.txt（再現できるzip）
```

## ChatGPT Work / Claude Cowork（アカウント側）

ローカルスクリプトでは**操作できない**。利用者が、`package` が作る zip を、各サービスのSkill登録の手順に従って登録する。

Claude の公式説明では、Coworkは `~/.claude/skills/` を直接読まない。アカウントで有効なSkillを読み込む。ローカル配置だけで導入完了にしない。

登録後に、次を観測する。

- 呼び出し
- 資料参照
- スクリプト実行（実行できるか）
- 保存

結果は、成功・失敗・未実施に分けて `docs/HOST-EVIDENCE.json` に記録する。スクリプトを実行できない環境では、`references/hosts.md` の手動記録の経路を使う。

次は[初回の使い方](USAGE.md#初回の使い方)。
