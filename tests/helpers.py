"""テスト共通部品。実ユーザーの配置先・保存先には触れない(すべて一時ディレクトリ)。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skill" / "contextual-terminology-review" / "scripts"
SKILL = ROOT / "skill" / "contextual-terminology-review"
CTR = SCRIPTS / "ctr.py"
INSTALL = ROOT / "tools" / "ctr_install.py"
FIXTURES = ROOT / "tests" / "fixtures"
HOSTS_DOC = SKILL / "references" / "hosts.md"
ACCEPT = Path(os.environ.get("CTR_ACCEPTANCE_JSON", ROOT / "tests" / "data" / "acceptance-cases.json"))
sys.path.insert(0, str(SCRIPTS))

HAS_PDFPLUMBER = find_spec("pdfplumber") is not None
HAS_ST = find_spec("sentence_transformers") is not None


def acceptance() -> dict:
    return json.loads(ACCEPT.read_text(encoding="utf-8"))


def case(cid: str) -> dict:
    return next(c for c in acceptance()["cases"] if c["id"] == cid)


def run_ctr(*args, env=None, cwd=None):
    """ctr.py をサブプロセスで実行する。戻り: (終了コード, 出力(JSONなら辞書/リスト))"""
    e = {**os.environ, **(env or {})}
    for k in ("CTR_RUNTIME_ROOT", "CTR_IMPROVEMENT_ROOT", "CTR_GOLD_ROOT"):
        if env is None or k not in env:
            e.pop(k, None)
    p = subprocess.run([sys.executable, str(CTR), *map(str, args)], capture_output=True, text=True, env=e, cwd=cwd)
    try:
        return p.returncode, json.loads(p.stdout)
    except ValueError:
        return p.returncode, p.stdout + p.stderr


class TmpCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="ctr-test-")
        self.tmp = Path(self._td.name).resolve()
        self.addCleanup(self._td.cleanup)

    def mk(self, name: str) -> Path:
        p = self.tmp / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def read_all_text(self, root: Path) -> str:
        out = []
        for p in sorted(root.rglob("*")):
            if p.is_file():
                try:
                    out.append(p.read_text(encoding="utf-8"))
                except UnicodeDecodeError:
                    pass
        return "\n".join(out)


def make_cases(cls, case_ids, name, fn):
    """A番号ごとに test_<ID>_<name> を生やす(実行表の対応づけ用)。"""
    for cid in case_ids:
        setattr(cls, f"test_{cid}_{name}", (lambda c: lambda self: fn(self, c))(cid))
