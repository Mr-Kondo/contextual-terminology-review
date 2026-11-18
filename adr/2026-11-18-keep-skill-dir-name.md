# スキルのディレクトリ名 `skill/` を `skills/` に改名しない

- 状態: 採択（改名を見送る）。再評価の条件あり
- 日付: 2026-11-18
- 関連: [Issue #65](https://github.com/Mr-Kondo/contextual-terminology-review/issues/65)、[Issue #40](https://github.com/Mr-Kondo/contextual-terminology-review/issues/40)、[確認の記録](../docs/upstream/reviews/japanese-readability-editor-0d00397.md)

## 背景

参考先の `japanese-readability-editor` が、`gh skill`（GitHub CLI のプレビュー機能）で名前だけで導入できるよう、`skill/` を `skills/` に改名した。このリポジトリも同じ改名をするかを決める。導入と更新の正は Skills CLI（`npx skills`）で、v0.1.14 で一本化した。

## 実測

環境は macOS。使い捨てのフォルダで測り、リポジトリの導入先には触れていない。

| 確かめたこと | 結果 |
|---|---|
| `gh skill install <repo> <name>`（現状 `skill/`、gh 2.105.0） | `no skills found` |
| `gh skill install <repo> skill/…/SKILL.md` | 入る |
| `gh skill update --dry-run` | 飛ばして「All skills are up to date.」と表示 |
| Skills CLI の発見（`add --list`、現状 `skill/` と、改名した複製 `skills/`。1.9.0） | どちらも 1 件を見つける。1.7.6 は改名した複製だけ確認 |
| Skills CLI の更新（1.9.0 の更新処理をソースで追った。1.7.6 は、同じ関数名と文言があることだけ確認） | 記録した `skillPath` が無くなると、「Skill paths changed」としてクローンし直し、新しい場所を見つけて更新する。実際の GitHub での更新は、実行していない |
| 改名の影響（このリポジトリ） | `skill/contextual-terminology-review` か `"skill" /` を含むのは 21 ファイル・38 行（検索で数えた）。内訳は、テスト 2、ツール 7、`release.yml`（1 ファイル・3 か所）、`docs/` 配下 9、`README.md`、`CLAUDE.local.md`。ZIP は `git archive` の対象を変えるだけで、中身は同じになるはずだが、測っていない |

## 選択肢

1. 改名する。`gh skill` の名前だけの導入と `update` が使える。
2. 改名せず、文書で `gh skill` を対象外と明記する（採択）。
3. `skills/` を追加し、`skill/` を残す。二重管理になるため選ばない。

## 決定

改名しない。理由は次のとおり。

- 利益が小さい。`gh skill` はプレビューで、予告なく変わる。導入と更新の正は Skills CLI で、そこでは、どちらの配置でも発見できる。
- 費用とリスクが、利益に見合わない。21 ファイルの変更と、リリース経路（`release.yml` の対象パスと ZIP の作り方）の変更に加え、既存の導入者の更新が、記録した場所を失う。CLI は新しい場所を見つけ直すと読んだが、GitHub での実際の更新は未確認。
- `gh skill` の利用者の要望を、まだ受けていない。

## 結果

- `docs/INSTALL.md` に、`gh skill` が対象外であることと、その理由を書いた（#66）。
- 利益の測定、または利用者の要望がなければ、`skill/` を保つ。

## 再評価の条件

次のどれかが起きたら、新しい ADR で見直す。

- `gh skill` がプレビューを終え、`skill/` の配置を認めない仕様が固まる。
- `gh skill` で導入したいという要望が、利用者から出る。
- Skills CLI が `skill/` を発見しなくなる（`skills-cli-windows` を含む CI で検知する）。

改名するときは、まず別のブランチで実際の GitHub 上の更新（旧版を入れた状態から `npx skills update`）を確かめてから、リリースする。

## 限界

- `gh skill` の実測は、1 つの gh 版と 1 つの環境のみ。名前だけの導入が改名後に通ることは、上流の記録による。こちらでは測っていない。
- 影響の数は、上の2つの文字列の検索で数えた。別の書き方（Windows の `skill\`、変数での組み立て）は数えていない。
