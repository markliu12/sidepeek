"""Guards against releasing with a stale version number."""

import pathlib
import re
import unittest

from sidepeek import __version__

ROOT = pathlib.Path(__file__).resolve().parents[1]


class VersionConsistencyTest(unittest.TestCase):
    def test_version_resource_matches_the_package(self):
        text = (ROOT / "version_info.txt").read_text(encoding="utf-8")

        strings = set(re.findall(
            r"StringStruct\('(?:File|Product)Version',\s*'([^']+)'\)", text))
        self.assertEqual(strings, {__version__}, "version_info.txt strings are stale")

        numeric = re.findall(r"(?:file|prod)vers=\(([^)]*)\)", text)
        self.assertEqual(len(numeric), 2)
        for group in numeric:
            parts = [p.strip() for p in group.split(",")]
            self.assertEqual(".".join(parts[:3]), __version__,
                             "version_info.txt numeric version is stale")

    def test_changelog_documents_the_current_version(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"## [{__version__}]", changelog)

    def test_package_version_is_semver(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
