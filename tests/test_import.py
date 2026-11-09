import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import import_releases as m

class ReleaseTests(unittest.TestCase):
    def test_skips_drafts_and_prerelease(self):
        releases = [
            {"draft": True, "prerelease": False, "published_at": "2026-11-11", "tag_name": "draft", "assets": [{"name": "secret.apk", "size": 1000}]},
            {"draft": False, "prerelease": True, "published_at": "2026-11-10", "tag_name": "preview", "assets": [{"name": "preview.apk", "size": 1000}]},
            {"draft": False, "prerelease": False, "published_at": "2026-11-09", "tag_name": "stable", "assets": [{"name": "stable.apk", "size": 1000}]},
        ]
        self.assertEqual(m.choose_release(releases, {"include_prereleases": False, "allow_debug": False})[0]["tag_name"], "stable")
        self.assertEqual(m.choose_release(releases, {"include_prereleases": True, "allow_debug": True})[0]["tag_name"], "preview")

    def test_only_selects_permanent_signed_release_tags(self):
        releases = [
            {"draft": False, "prerelease": False, "published_at": "2026-11-11", "tag_name": "v0.9-debug", "assets": [{"name": "app-debug.apk", "size": 1000}]},
            {"draft": False, "prerelease": False, "published_at": "2026-11-10", "tag_name": "droidify-12", "assets": [{"name": "Redactor-droidify-12.apk", "size": 1000}]},
        ]
        config = {"include_prereleases": False, "allow_debug": False, "release_tag_prefix": "droidify-"}
        self.assertEqual(m.choose_release(releases, config)[0]["tag_name"], "droidify-12")
        self.assertEqual(m.choose_release(releases, {**config, "release_tag_prefix": "not-found"}), (None, None))

    def test_ambiguous_assets_rejected(self):
        releases = [{"draft": False, "published_at": "2026-11-09", "tag_name": "v1", "assets": [{"name": "arm64.apk", "size": 1000}, {"name": "x86.apk", "size": 1000}]}]
        with self.assertRaises(ValueError):
            m.choose_release(releases, {"include_prereleases": True, "allow_debug": True})

    def test_signer_digest_formats_fail_closed(self):
        digest = "a" * 64
        for identity in ["Signer #1", "Signer (minSdkVersion=24, maxSdkVersion=32)", "V2 Signer:", "V3.0 Signer:"]:
            self.assertEqual(
                m.parse_signer_details(f"{identity} certificate SHA-256 digest: {digest}"),
                (digest, False),
            )
            self.assertEqual(
                m.parse_signer_details(f"{identity} certificate SHA-256 digest:\n{digest}"),
                (digest, False),
            )
            self.assertEqual(
                m.parse_signer_details(
                    f"{identity} certificate SHA-256 digest: {digest}\n"
                    f"{identity} certificate DN: CN=Android Debug,O=Android"
                ),
                (digest, True),
            )
        with self.assertRaisesRegex(ValueError, "Multiple distinct"):
            m.parse_signer_details(
                f"Signer #1 certificate SHA-256 digest: {digest}\n"
                f"Signer #2 certificate SHA-256 digest: {'b' * 64}"
            )
        with self.assertRaisesRegex(ValueError, "malformed"):
            m.parse_signer_details("Signer #1 certificate SHA-256 digest: broken")
        with self.assertRaisesRegex(ValueError, "Cannot identify"):
            m.parse_signer_details("No signer certificates")

    def test_incompatible_signatures_and_version_codes(self):
        old = {"package": "app.a", "certificate_sha256": "abc", "version_code": 2, "sha256": "old"}
        base = dict(old)
        self.assertIsNone(m.validate_update(base, old))
        self.assertIn("certificate", m.validate_update({**base, "certificate_sha256": "def"}, old))
        self.assertIn("backwards", m.validate_update({**base, "version_code": 1}, old))
        self.assertIn("without increasing", m.validate_update({**base, "sha256": "new"}, old))
        self.assertIsNone(m.validate_update({**base, "sha256": "new", "version_code": 3}, old))

    def test_metadata_and_site_generated(self):
        item = {"name": "Test app", "summary": "A useful app", "source_url": "https://github.com/user/Test", "package": "com.example.test", "filename": "com.example.test_2.apk", "version_name": "1.2", "version_code": 2}
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            m.generate_metadata(p / "metadata", [item])
            (p / "site").mkdir()
            m.generate_home(p / "site", [item], "https://example.com", "https://example.com/repo")
            self.assertIn("Test app", (p / "metadata/com.example.test.yml").read_text())
            self.assertIn("https://example.com/repo", (p / "site/index.html").read_text())

    def test_bad_prior_filename_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(m.restore_previous(Mock(), {"filename": "../evil.apk"}, Path(temp), "https://example.com"))

if __name__ == '__main__':
    unittest.main()