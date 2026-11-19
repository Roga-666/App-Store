"""Keep the FlashTrim catalog pinned to stable, update-compatible APKs."""
import json
import re
from pathlib import Path
import unittest

class SignedFlashTrimCatalogTest(unittest.TestCase):
    def test_requires_signed_flashtrim_release(self):
        root = Path(__file__).resolve().parents[1]
        catalog = json.loads((root / "apps.json").read_text(encoding="utf-8"))
        app = next(item for item in catalog["apps"] if item["repository"] == "FlashTrim")
        self.assertFalse(app.get("allow_debug", False))
        self.assertEqual("droidify-", app["release_tag_prefix"])
        pattern = app["asset_pattern"]
        self.assertIsNotNone(re.fullmatch(pattern, "FlashTrim-droidify-16.apk"))
        self.assertIsNone(re.fullmatch(pattern, "FlashTrim-v0.16.apk"))
        self.assertIsNone(re.fullmatch(pattern, "app-debug.apk"))

if __name__ == "__main__":
    unittest.main()
