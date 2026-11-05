# 導入・更新・アンインストール

[使い方の入口](USAGE.md)の手順2。Skills CLI または既存の `tools/ctr_install.py` を使う。

## Skills CLIで導入・更新する

Node.js / npm と Git が必要。Skills CLI 1.7.6 で確認している。

```bash
npx skills add Mr-Kondo/contextual-terminology-review --skill contextual-terminology-review -g --agent claude-code codex antigravity antigravity-cli -y
npx skills update contextual-terminology-review -g
```

初回の `add` は配置と更新元の登録を行う。`-g` はユーザー全体への導入、`--agent` は対象環境である。必要な環境だけ指定できる。`-y` は確認を省略するため、既存の同名配置があれば、先に下の移行手順を行う。

以後は `npx skills update` でも更新できる。このコマンドは他の登録済みスキルも対象にする。上の名前付き・`-g` 付きコマンドなら、このスキルのユーザー配置だけを対象にできる。最新版とは、リリースタグの最大値ではなく、登録したGitHubリポジトリの既定ブランチの内容である。タグ固定で導入したものは、その参照先を追う。

CLIは `~/.agents/.skill-lock.json` に更新元とフォルダーのハッシュを記録する。独自インストーラーや手動コピーだけで配置したものは、`update` だけでは登録されない。ロックファイルは手編集せず、初回に `add` を行う。

### 既存配置からの移行

1. 同名スキルの配置先を確認し、ローカル変更がないか確かめる。配置フォルダーを、スキル検索対象外の場所へバックアップする。
2. 上の `add` を実行する。既定の共有配置とシンボリックリンクを使い、`--copy` は付けない。コピー配置は、実行環境によって更新される対象が異なる場合がある。
3. `npx skills list -g` で配置を確認し、`npx skills update contextual-terminology-review -g` を実行する。配布元と配置先の `VERSION`・内容を照合してからバックアップを片付ける。

CLI 1.7.6 の Antigravity 配置先は `~/.gemini/antigravity/skills/`、Antigravity CLI は `~/.gemini/antigravity-cli/skills/` である。既存インストーラーが使う IDE/App の `~/.gemini/config/skills/` とは異なる。後者を使う環境では、バックアップ後に、このスキルのディレクトリだけを共有配置 `~/.agents/skills/contextual-terminology-review` へのリンクに置き換えるか、既存インストーラーで別途更新する。親の `skills/` や他のスキルは置き換えない。

移行後の配置は Skills CLI で管理する。独自インストーラーの `.ctr-install.json` による照合・保護とは別の管理方式なので、両方式を同じ配置へ交互に適用しない。Skill実行時のPython依存は、別途 [SETUP.md](SETUP.md) に従って用意する。

削除する場合は、`npx skills remove contextual-terminology-review -g -y` を使う。手動で追加した旧配置先のリンクは別途取り除く。用語データや評価履歴はスキル配置の外に保持する。

仕様の参照先: [Skills CLI](https://github.com/vercel-labs/skills)、[更新実装](https://github.com/vercel-labs/skills/blob/main/src/update.ts)。CLIの配置先や挙動は版により変わり得る。

## 最短の導入（Claude Code に入れる例）

導入ツールが使うのはPythonの標準ライブラリだけである。pydantic などの依存は、導入後にSkillを動かすときに要る（[SETUP.md](SETUP.md)）。

作業は、このリポジトリのフォルダで行う。**1行で配置まで進む**。

**macOS / Linux（ターミナル）**

```bash
python3 tools/ctr_install.py install --target claude-code --scope user
python3 tools/ctr_install.py verify  --target claude-code --scope user
```

**Windows（PowerShell）**

```powershell
py -3 tools\ctr_install.py install --target claude-code --scope user
py -3 tools\ctr_install.py verify  --target claude-code --scope user
```

- 1行目が配置で、2行目は配置したものが正本と一致するかの照合である
- 配置の前に計画だけ見たいときは、`--dry-run` を付ける。何も変更せず、配置先と操作を表示する
- Windows に `py` がなければ、`python` で置き換える。どちらも見つからないときは、python.org から Python 3 を入れる（CIは 3.12 で検査している）
- 導入先を手で指定する必要はない。ホームフォルダは自動で決まる（Windows では `C:\Users\<ユーザー名>`）
- Codex や Antigravity に入れるときは、`--target` を `codex`、`antigravity`、`all` に変える
- 同名のものが既にあるときは、上書きも削除もせずに止まる。置き換えるには、下の「既存のSkillとの衝突」の `--on-conflict` を使う

## すでに入れている場合（更新）

リポジトリを最新にしてから、`install` を `update` に変えて実行する。

**macOS / Linux**

```bash
git pull
python3 tools/ctr_install.py update --target claude-code --scope user
python3 tools/ctr_install.py verify --target claude-code --scope user
```

**Windows（PowerShell）**

```powershell
git pull
py -3 tools\ctr_install.py update --target claude-code --scope user
py -3 tools\ctr_install.py verify --target claude-code --scope user
```

- 内容が同じなら、`noop`（変更なし）と表示される。最新である
- `install` を、導入済みの環境で実行すると、版や内容が違えば拒否される。更新には `update` を使う
- 旧版は `skills.bak/` へ退避され、途中で失敗すれば旧版に戻る（詳細は下の「更新」）
- リリースの zip から入れ直すときも同じである。展開したフォルダを `--source` に指定する
- 複数の環境に入れているときは、`--target all` でまとめて更新できる

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

導入先のフォルダ名（`.claude` など）を `--dest` で直接指定するときも、Windows ではドライブ文字から書く。空白を含むときは、引用符で囲む。

## 配置先

| 環境 | user（ホーム。Windows は `%USERPROFILE%` 以下の同名フォルダ） | workspace（プロジェクト） | 公式資料での確認（2026-10-17） |
|---|---|---|---|
| Claude Code | `~/.claude/skills/` | `.claude/skills/` | code.claude.com/docs/en/skills |
| Codex | `~/.agents/skills/` | `.agents/skills/` | developers.openai.com/codex/skills |
| Antigravity IDE/App | `~/.gemini/config/skills/` | `.agents/skills/` | antigravity.google/docs/skills |
| Antigravity CLI | `~/.gemini/antigravity-cli/skills/` | `.agents/skills/` | 同上 |

## コマンド

Windows では、`python3` を `py -3` に読み替える。

```bash
python3 tools/ctr_install.py install   --target claude-code --scope user --dry-run  # 計画の表示（変更なし）
python3 tools/ctr_install.py install   --target claude-code --scope user
python3 tools/ctr_install.py update    --target all --scope user                    # all = claude-code, codex, antigravity-ide, antigravity-cli
python3 tools/ctr_install.py verify    --target codex --scope user                  # 正本との照合
python3 tools/ctr_install.py uninstall --target antigravity --scope user          # このSkillのフォルダだけを削除
```

## 既存のSkillとの衝突

配置したSkillには、`.ctr-install.json`（版と全ファイルのsha256）が付く。

- これが無い同名のものは、「識別できない既存」として扱う
- 導入後に手で編集したファイルがある場合も、同じく扱う

どちらも、既定では上書きも削除もしない。`--on-conflict` で扱いを選ぶ。

| 指定 | 動作 | 旧版 |
|---|---|---|
| `refuse`（既定） | 何もせずに止まる | そのまま |
| `backup` | 退避してから置換、または削除する | `skills.bak/` に残る |
| `overwrite` | 退避せずに置換、または削除する | **残らない**。戻せない |

```bash
python3 tools/ctr_install.py install --target claude-code --scope user --on-conflict backup
python3 tools/ctr_install.py update  --target claude-code --scope user --on-conflict overwrite
```

- 迷うなら `backup` を使う。手で編集したファイルを残したいときに戻せる
- `overwrite` でも、置換の途中で失敗したら旧版に戻る。成功して照合が済んだ後に、旧版を捨てる
- `uninstall` は、識別できない既存を、どの指定でも削除しない。このSkillが置いたと確認できるものだけを消す
- 導入済みで版や内容が違うものに `install` を使うと、`--on-conflict` に関わらず拒否される。`update` を使う

## 更新

更新は、次の順に進む。途中で失敗したら、旧版に戻る。

1. 新版を一時領域に作る
2. 旧版を `skills.bak/` へ退避する
3. 置換する
4. 照合する

更新後は、用語データと索引の版を確認する。索引が古ければ作り直す。

```bash
python3 skill/contextual-terminology-review/scripts/ctr.py check data --improvement-root ABS [--index-meta PATH]
```

`ABS` は絶対パス。Windows では `py -3 skill\contextual-terminology-review\scripts\ctr.py ...` で、ドライブ文字から書く。

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
