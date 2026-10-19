"""リリースの自動化(.github/workflows/release.yml)が前提にするものを、マージ前に検査する。"""
import re
import unittest

from helpers import ROOT, SKILL


class ReleaseNotes(unittest.TestCase):
    def test_current_version_has_release_notes_with_a_title_line(self):
        version = (SKILL / "VERSION").read_text(encoding="utf-8").strip()
        notes = ROOT / "docs" / "release-notes" / f"v{version}.md"
        self.assertTrue(notes.is_file(), f"{notes.relative_to(ROOT)} がない。版を上げるPRには、リリースノートを入れる(docs/RELEASING.md)")
        first = notes.read_text(encoding="utf-8").splitlines()[0]
        self.assertRegex(first, rf"^# v{re.escape(version)} — \S", "1行目は `# v<版> — <題名>`(リリースの題名になる)")


if __name__ == "__main__":
    unittest.main()
