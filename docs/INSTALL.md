# 導入・更新・アンインストール

[使い方の入口](USAGE.md)の手順2。Skills CLI（`npx skills`）を使う。

## Skills CLIで導入・更新する

Node.js / npm と Git が必要。Skills CLI 1.7.6 で確認している。

**既存の同名配置がある場合は、上書きに備えて先にバックアップする。** 下の「既存配置からの移行」に従う。

```bash
npx skills add Mr-Kondo/contextual-terminology-review --skill contextual-terminology-review -g --agent claude-code codex antigravity antigravity-cli -y
npx skills update contextual-terminology-review -g
```

初回の `add` は配置と更新元の登録を行う。`-g` はユーザー全体への導入、`--agent` は対象環境である。必要な環境だけ指定できる。`-y` は確認を省略するため、既存の同名配置があれば、先に下の移行手順を行う。

以後は `npx skills update` でも更新できるが、更新する範囲に注意する。対話時は範囲を選択する。非対話時や `-y` 指定時は、現在のディレクトリに `skills-lock.json` またはプロジェクトのスキル配置があると、プロジェクトだけを対象にする。空の `skills-lock.json` でも同じで、ユーザー配置は更新されない。ユーザー配置を確実に更新するには、上の名前付き・`-g` 付きコマンドを使う。全ユーザースキルなら `npx skills update -g` である。

最新版とは、リリースタグの最大値ではなく、登録したGitHubリポジトリの既定ブランチの内容である。タグ固定で導入したものは、その参照先を追う。

CLIは通常 `~/.agents/.skill-lock.json` に更新元とフォルダーのハッシュを記録する。`XDG_STATE_HOME` が設定されている場合は、その下の `skills/.skill-lock.json` を使う。独自インストーラーや手動コピーだけで配置したものは、`update` だけでは登録されない。ロックファイルは手編集せず、初回に `add` を行う。

更新時の配置対象は、その実行時にCLIが検出した環境に従う。初回の `--agent` 一覧をそのまま保存・再利用する方式ではない。

### 既存配置からの移行

1. 同名スキルの配置先を確認し、ローカル変更がないか確かめる。配置フォルダーを、スキル検索対象外の場所へバックアップする。
2. 上の `add` を実行する。既定の共有配置とシンボリックリンクを使い、`--copy` は付けない。コピー配置は、実行環境によって更新される対象が異なる場合がある。
3. `npx skills list -g` で配置を確認し、`npx skills update contextual-terminology-review -g` を実行する。配布元と配置先の `VERSION`・内容を照合してからバックアップを片付ける。

CLI 1.7.6 は Codex・Antigravity・Antigravity CLI を共有配置 `~/.agents/skills/` に導入する。旧インストーラー（v0.1.13 まで同梱）で `~/.gemini/config/skills/` や `~/.gemini/antigravity-cli/skills/` に置いたコピーが残っている場合は、バックアップ後に、このスキルのディレクトリだけを、共有配置 `~/.agents/skills/contextual-terminology-review` へのリンクに置き換える。Skills CLI は旧配置先へリンクを作らないので、削除だけにすると、旧配置先を読む環境でスキルが見えなくなる。共有配置を直接読めると確認できた環境だけ、削除でよい。親の `skills/` や他のスキルは置き換えない。旧インストーラーが付けた `.ctr-install.json` は、Skills CLI は使わない。

旧インストーラーはプロジェクト配置（`.claude/skills/` や `.agents/skills/`）にも置けた。そのコピーが残っていると、ユーザー配置より優先され、`-g` の更新後も旧版が使われ続けることがある。残っていれば、バックアップ後に取り除くか、プロジェクト側で `-g` なしの `npx skills add` を使って登録し直す。

Skill実行時のPython依存は、別途 [SETUP.md](SETUP.md) に従って用意する。

削除する場合は、`npx skills remove contextual-terminology-review -g -y` を使う。手動で追加した旧配置先のリンクは別途取り除く。用語データや評価履歴はスキル配置の外に保持する。

仕様の参照先: [Skills CLI](https://github.com/vercel-labs/skills)、[更新実装](https://github.com/vercel-labs/skills/blob/main/src/update.ts)。CLIの配置先や挙動は版により変わり得る。

## OS による書き方の違い

| | macOS / Linux | Windows（PowerShell） |
|---|---|---|
| Python の呼び方 | `python3` | `py -3`（なければ `python`） |
| パスの区切り | `/` | `\`。`/` も多くの場面で通る |
| ホームフォルダ | `~`（例: `~/.claude/skills`） | `$env:USERPROFILE`（例: `$env:USERPROFILE\.claude\skills`） |
| 絶対パス | `/` で始まる（例: `/Users/me/ctr-data`） | **ドライブ文字から始める**（例: `C:\Users\me\ctr-data`） |
| 仮想環境の Python | `.venv/bin/python` | `.venv\Scripts\python` |
| 行の継続 | 行末の `\` | 行末の `` ` ``（バッククォート）。迷うなら1行で書く |

`/abs/path/runtime` のように `/` で始まるパスは、Windows では絶対パスと見なされず、エラーになる。保存先の指定（`--runtime-root` など）には、`C:\Users\me\ctr-data\runtime` のようにドライブ文字から書く。

## 更新後の確認

更新後は、用語データと索引の版を確認する。索引が古ければ作り直す。

```bash
python3 skill/contextual-terminology-review/scripts/ctr.py check data --improvement-root ABS [--index-meta PATH]
```

`ABS` は絶対パス。Windows では `py -3 skill\contextual-terminology-review\scripts\ctr.py ...` で、ドライブ文字から書く。

## アンインストール

`npx skills remove contextual-terminology-review -g -y` で、当該Skillだけを消す。原資料・用語正本・評価履歴・ログ・他のSkillには触れない。これらはSkillフォルダの外に置く設計である。データの削除は別の操作（`ctr.py delete plan/apply`）で行う。

## ChatGPT Work / Claude Cowork（アカウント側）

Skills CLI やスクリプトでは**操作できない**。利用者が、GitHub のリリースに添付されたzip（`contextual-terminology-review-<版>.zip`）を、各サービスのSkill登録の手順に従って登録する。

Claude の公式説明では、Coworkは `~/.claude/skills/` を直接読まない。アカウントで有効なSkillを読み込む。ローカル配置だけで導入完了にしない。

登録後に、次を観測する。

- 呼び出し
- 資料参照
- スクリプト実行（実行できるか）
- 保存

結果は、成功・失敗・未実施に分けて `docs/HOST-EVIDENCE.json` に記録する。スクリプトを実行できない環境では、`references/hosts.md` の手動記録の経路を使う。

次は[初回の使い方](USAGE.md#初回の使い方)。
