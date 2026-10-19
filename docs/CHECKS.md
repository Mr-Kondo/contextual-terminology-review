# 検査の実行と意味審査の依頼

[使い方の入口](USAGE.md)の手順5。開発者と確認者向け。

## 検査の実行

```bash
python3 -m unittest discover -s tests                 # 標準ライブラリのみ。未導入の依存に当たるテストは skip（未実施）
python3 tools/run_acceptance.py                        # A01〜A48 の機械検査と docs/ACCEPTANCE-REPORT.md の生成
```

## Ruri の実検索を含める

既定のモデルは ruri-v3-310m である。重みは約1.2GBで、初回の取得にネットワークが要る。Xet転送がプロキシを通らない環境では、`HF_HUB_DISABLE_XET=1` を付ける。

Windows（PowerShell）では、先に `$env:HF_HUB_DISABLE_XET = "1"` を実行し、`.venv/bin/python` を `.venv\Scripts\python` に読み替える。

```bash
HF_HUB_DISABLE_XET=1 .venv/bin/python tools/bench_search.py --out docs/evidence/search-bench.json
CTR_RUN_RURI=1 .venv/bin/python -m unittest discover -s tests
```

## 意味審査の依頼

[docs/SEMANTIC-REVIEW-SHEET.md](SEMANTIC-REVIEW-SHEET.md) は、独立した確認者向けの票である（A01〜A12, A17, A19, A20, A28, A29）。

機械検査の合格は、意味保持の合格ではない。確認者は、判断・理由・日付を票に記入する。保留は、保留のまま残す。この票の結果が出るまで、意味の合否は「未実施」である。
