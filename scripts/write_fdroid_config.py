#!/usr/bin/env python3
"""Write fdroidserver config with the index-signing secrets only in ephemeral CI files."""
import json
import os
from pathlib import Path
import yaml

catalog = json.loads(Path("apps.json").read_text())
password = os.environ.get("FDROID_REPO_KEYSTORE_PASS", "")
keystore = os.environ.get("FDROID_REPO_KEYSTORE", "")
if len(password) < 8 or not keystore or not Path(keystore).is_file():
    raise SystemExit("Missing signing keystore or signing password (>=8 characters required)")
config = {
    "repo_url": catalog["repo_url"],
    "repo_name": "Roga App Repository",
    "repo_description": "Android apps built by Roga-666. APKs are copied from GitHub Releases.",
    "repo_keyalias": "fdroidrepo",
    "repo_icon": "fdroid-icon.png",
    "keystore": keystore,
    "keystorepass": password,
    "keypass": password,
    "keydname": "CN=Roga App Repository, O=Roga-666, C=US",
    "archive_older": 0,
}
out = Path("build/fdroid/config.yml")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
out.chmod(0o600)