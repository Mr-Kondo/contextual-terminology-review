# リリースの手順

リリースは、`main` の `skill/contextual-terminology-review/VERSION` が変わると、GitHub Actions（`.github/workflows/release.yml`）が作る。人が手で打つのは、PR を作るところまでである。

## 版を上げるPRに入れるもの

1. `skill/contextual-terminology-review/VERSION` を新しい版にする
2. `docs/release-notes/v<版>.md` を作る。**1行目は `# v<版> — <題名>`**。リリースの題名になる。ノートには、前の版からの違い、検証した範囲、未実施・注意を書く
3. テストを通す（`python3 -m unittest discover -s tests`）

`docs/release-notes/v<版>.md` が無いと、workflow は失敗する。

## 自動で行うこと

- `package` で zip・`ctr_install.py`・`INSTALL-ON-REMOTE.txt` を作る
- ノートの末尾に、zip の SHA-256 を足す
- タグ `v<版>` を打ち、3つのファイルを添付したリリースを作る。同じタグがあれば、何もしない

## マージ

`main` は、CI の `test` が通らないとマージできない（ブランチ保護）。自動マージが許可されているので、PR に自動マージを設定すると、`test` が通った時点でマージされ、作業ブランチも自動で削除される。`test-windows` は参考の結果で、必須ではない。

## 手で行うこと

利用者のマシンの導入先（`~/.claude/skills` など）の更新は、リリース後に、そのマシンで `python3 tools/ctr_install.py update --target all --scope user` を実行する。
