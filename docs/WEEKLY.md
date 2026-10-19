# 週次の手順

[使い方の入口](USAGE.md)の手順4。本人の時間は、初期設定と日々の入力を含めて、合計30分程度である。

## 毎週やること

| 時間 | やること | コマンド |
|---|---|---|
| 5分 | 当週の実例を選び、原文・意図・相手・場面を記録 | （日々は `feedback add` の4項目だけでもよい） |
| 15分 | 根拠を読み、判断可能な範囲と正解を確認 | `check sample`（指摘なし例を含む確認候補） |
| 5分 | AIの指摘・修正案と照合し、フィードバックを残す | `feedback add --validity ... --intent ... --usage ... --receiver ...` |
| 5分 | AIなしで言い直し、更新候補を残す | `propose create --spec spec.json` |

固定件数や全分野を毎週こなす必要はない。30分を超えたら、確認数を減らして保留を残す。

## 時間と集計

時間は、次のコマンドで記録する。

`ctr.py` の呼び方と Windows での読み替えは、[USAGE.md](USAGE.md#コマンドの書き方windows)にある。

```bash
ctr.py feedback time --category setup|record|evidence|compare|practice --minutes N --who self|collaborator
```

集計は、次のコマンドで出す。分母が0なら未評価になり、利用総数が未知なら収集率は出ない。

```bash
ctr.py evaluate metrics --runtime-root ... --improvement-root ...
```

## 別PC・他の利用者・リモートの記録を集める（ファイル方式）

```bash
ctr.py export --runtime-root ABS_ON_THAT_HOST            # 共有許可が設定済みのときだけ。outbox/<package_id>/ ができる
ctr.py import /path/to/package --improvement-root ABS     # 一時領域で検査してから確定
```

自動送信・常駐・定期実行は設定しない。パッケージのハッシュが保証するのは、移送中の同一性だけである。送信者の認証や内容の正しさは保証しない。

## 更新案の採用（明示的な人の判断のみ）

採用は、次の順に進める。

1. `propose create` で更新案を作る
2. `evaluate compare` で、同条件の新旧を比べる
3. 人が確認する
4. `evaluate adopt --approved-by ... --reason ... --i-approve` で採用する

評価後に基準が変わったら、競合として止まる。悪化したら `evaluate restore` で戻す。AIの採点や提案を、採用承認として扱わない。
