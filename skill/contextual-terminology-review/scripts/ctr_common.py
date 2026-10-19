"""共通部品: 原子的な保存、ハッシュ、エラー、版。標準ライブラリのみ。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
CHECKER_VERSION = "ctr-checker-1"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class CtrError(Exception):
    """利用者に見せてよい失敗。code は固定語、message に原文を入れない。"""

    def __init__(self, code: str, message: str = ""):
        super().__init__(code)
        self.code, self.message = code, message


def need_pydantic():
    try:
        import pydantic  # noqa: F401
    except ImportError as exc:  # pragma: no cover - 環境依存
        raise CtrError("pydantic_missing", "pydantic が必要です: pip install -r requirements.txt") from exc


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(3)}"


def canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_obj(obj) -> str:
    return sha256_bytes(canonical(obj))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def skill_version() -> str:
    try:
        return (skill_root() / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def read_json(path: Path):
    try:
        with open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    except FileNotFoundError as exc:
        raise CtrError("file_not_found", path.name) from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise CtrError("invalid_json", path.name) from exc


def write_json(path: Path, obj, *, overwrite: bool = False) -> dict:
    """同一ディレクトリの一時ファイルに書き、fsync して原子的に置く。保存後に再読込して照合する。

    overwrite=False は既存IDを上書きしない(os.link は既存なら失敗する)。
    戻り値の verified は「再読込したバイト列が書いたものと一致した」ことだけを示す。"""
    path = Path(path)
    data = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            if overwrite:
                os.replace(tmp, path)
            else:
                try:
                    os.link(tmp, path)
                except FileExistsError as exc:
                    raise CtrError("already_exists", path.name) from exc
                except OSError:
                    # shortcut: ハードリンクできない保存先(exFAT・一部のネットワーク共有)では、排他的に作って直接書く。途中で止まると半端なファイルが残るが、下の再読込の照合で検出する。
                    try:
                        fd2 = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0))
                    except FileExistsError as exc:
                        raise CtrError("already_exists", path.name) from exc
                    with os.fdopen(fd2, "wb") as f2:
                        f2.write(data)
                        f2.flush()
                        os.fsync(f2.fileno())
                finally:
                    os.unlink(tmp)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        reread = path.read_bytes()
    except CtrError:
        raise
    except OSError as exc:
        raise CtrError("storage_unwritable", f"{type(exc).__name__}") from exc
    if reread != data:
        raise CtrError("verify_failed", path.name)
    return {"path": str(path), "sha256": sha256_bytes(data), "bytes": len(data), "verified": True}


def valid_id(value: str, what: str = "id") -> str:
    if not isinstance(value, str) or not ID_RE.match(value):
        raise CtrError("invalid_id", what)
    return value
