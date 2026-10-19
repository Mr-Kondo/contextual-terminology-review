# 前提と保存先の決め方（最初に一度）

[使い方の入口](USAGE.md)の手順1。依存を入れ、保存先を決めて、初期化する。

## 1. 依存を入れる

システムのPythonに入れるか、仮想環境を作る。

**macOS / Linux**

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
```

**Windows（PowerShell）**

```powershell
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

仮想環境を作ったときは、以降のコマンドの `python3`（Windows は `py -3`）を、`.venv/bin/python`（Windows は `.venv\Scripts\python`）に置き換える。

`pydantic` だけでも、レビュー・出典検査・記録は使える。PDF抽出は `pdfplumber`、Ruri検索は `sentence-transformers` が要る。

## 2. 保存先を決める

保存先は**あなたが決める**。このSkillは既定の保存先を持たない。決めること:

- `runtime_data_root`: この実行先の記録の置き場。案件で保存を許可された永続領域の絶対パス（Windows は `C:\...` のようにドライブ文字から。`/` で始まるパスは絶対パスと見なされない）
- `improvement_root`: 許可済み記録の取り込み、更新案、基準データの置き場。本人または承認された管理者が扱う
- `evaluation_gold_root`: 評価用の正解と未使用例の置き場。レビューを生成・改善するAgentから**アクセスできない**場所にする
- 原文を保存してよいか（既定は不可）
- 共有してよい項目、共有範囲、保存期限

Skillのフォルダ、公開リポジトリ、自動同期されるフォルダは、業務ログの置き場にしない。

## 3. 初期化する

```bash
python3 skill/contextual-terminology-review/scripts/ctr.py store init --runtime-root /abs/path/runtime
```

Windows（PowerShell）では、次のように書く。以降の例も、`python3 .../ctr.py` を同じ形に読み替える。

```powershell
py -3 skill\contextual-terminology-review\scripts\ctr.py store init --runtime-root C:\Users\me\ctr-data\runtime
```

`policy.json` が作られる（原文保存=不可、共有=未設定）。許可したときだけ変更する。

```bash
python3 skill/contextual-terminology-review/scripts/ctr.py store set-policy --runtime-root /abs/path/runtime --raw-text allow
python3 skill/contextual-terminology-review/scripts/ctr.py store set-policy --runtime-root /abs/path/runtime --share-fields run_status,versions,problem_axes \
    --share-scope "<共有範囲>" --granted-by "<許可者>"
```

共有できる項目は、次のとおり。

`run_status`, `environment`, `versions`, `domains`, `problem_axes`, `machine_checks`, `human_feedback`, `project_opaque_id`, `effort`

次は[導入](INSTALL.md)。
