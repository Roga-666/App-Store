#!/usr/bin/env python3
"""Import checked GitHub release APKs into a binary F-Droid repo.

- Existing signatures must match across updates.
- Android versionCode must increase for changed APKs.
- Only the latest APK per source project is published.
- Source repositories may be private, but published APKs WILL BE PUBLIC.
"""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import requests
import yaml

USER_AGENT = "roga-fdroid-publisher/1.0"
MAX_APK_SIZE = 150 * 1024 * 1024
TIMEOUT = (15, 120)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def request_json(session, url, *, allow_missing=False):
    response = session.get(url, timeout=TIMEOUT)
    if response.status_code == 404 and allow_missing:
        return None
    response.raise_for_status()
    return response.json()


def download(session, url, output, *, expected_size=None):
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".download")
    if tmp.exists():
        tmp.unlink()
    try:
        with session.get(url, stream=True, timeout=TIMEOUT, headers={"Accept": "application/octet-stream"}) as response:
            response.raise_for_status()
            if response.headers.get("Content-Type", "").startswith("application/json"):
                raise RuntimeError("Expected APK bytes, got JSON instead")
            size = 0
            with open(tmp, "wb") as out:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > MAX_APK_SIZE:
                        raise ValueError(f"APK exceeds {MAX_APK_SIZE} byte limit")
                    out.write(chunk)
        if size < 512 or (expected_size is not None and size != expected_size):
            raise ValueError(f"Unexpected APK size: {size}")
        with open(tmp, "rb") as f:
            if f.read(2) != b"PK":
                raise ValueError("Downloaded file is not an APK/ZIP")
        tmp.replace(output)
    finally:
        tmp.unlink(missing_ok=True)


def parse_signer_details(signature):
    """Extract a verified signer certificate from supported apksigner output formats.

    Android build-tools can print 'Signer #1' or 'Signer (minSdkVersion=..., maxSdkVersion=...)'.
    Fail closed if any certificate digest is malformed or if multiple distinct
    certificates are present; do not silently accept an ambiguous signing identity.
    """
    lines = signature.splitlines()
    digests = []
    pattern = re.compile(
        r"^\\s*Signer (?:#\\d+|\\([^)]*\\)) certificate SHA-256 digest:\\s*(.*)$",
        re.IGNORECASE,
    )
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match is None:
            continue
        raw = match.group(1).strip()
        if not raw and index + 1 < len(lines):
            raw = lines[index + 1].strip()
        digest = raw.replace(":", "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("APK signing certificate digest was malformed")
        digests.append(digest)
    if not digests:
        raise ValueError("Cannot identify verified APK signing certificate")
    if len(set(digests)) != 1:
        raise ValueError("Multiple distinct APK signing certificates; manual review required")
    debug = bool(re.search(
        r"^\\s*Signer (?:#\\d+|\\([^)]*\\)) certificate DN:.*CN=Android Debug",
        signature, re.IGNORECASE | re.MULTILINE,
    ))
    return digests[0], debug


def inspect_apk(path):
    metadata = subprocess.run(["aapt", "dump", "badging", str(path)], check=True, capture_output=True, text=True).stdout
    package_line = next((line for line in metadata.splitlines() if line.startswith("package: ")), "")
    m = re.search(r"name='([^']+)'\s+versionCode='(\d+)'\s+versionName='([^']*)'", package_line)
    if not m:
        raise ValueError("Cannot identify Android package ID/versionCode from APK")
    signature = subprocess.run(["apksigner", "verify", "--print-certs", str(path)], check=True, capture_output=True, text=True).stdout
    certificate_sha256, debug = parse_signer_details(signature)
    return {
        "package": m.group(1), "version_code": int(m.group(2)),
        "version_name": m.group(3), "certificate_sha256": certificate_sha256,
        "debug_certificate": debug,
    }


def choose_release(releases, app):
    for release in sorted((r for r in releases if not r.get("draft")), key=lambda r: r.get("published_at") or "", reverse=True):
        # Never accidentally pick a newer historical debug APK over a stable signed APK.
        prefix = app.get("release_tag_prefix")
        if prefix and not str(release.get("tag_name") or "").startswith(prefix):
            continue
        if release.get("prerelease") and not app.get("include_prereleases", False):
            continue
        assets = [a for a in release.get("assets", []) if a["name"].lower().endswith(".apk") and a.get("size", 0) <= MAX_APK_SIZE]
        if not app.get("allow_debug", False):
            assets = [a for a in assets if "debug" not in a["name"].lower() and "preview" not in a["name"].lower()]
        if not assets:
            continue
        if len(assets) > 1:
            regex = app.get("asset_pattern")
            if regex:
                assets = [a for a in assets if re.search(regex, a["name"], re.IGNORECASE)]
            elif sum("universal" in a["name"].lower() for a in assets) == 1:
                assets = [a for a in assets if "universal" in a["name"].lower()]
            elif sum("release" in a["name"].lower() and "debug" not in a["name"].lower() for a in assets) == 1:
                assets = [a for a in assets if "release" in a["name"].lower() and "debug" not in a["name"].lower()]
        if len(assets) != 1:
            raise ValueError(f"Ambiguous APK assets in {release.get('tag_name')}: {[a['name'] for a in assets]}; set asset_pattern")
        return release, assets[0]
    return None, None


def validate_update(fresh, old):
    if not old:
        return None
    if fresh["package"] != old["package"]:
        return "Android package ID changed"
    if fresh["certificate_sha256"] != old["certificate_sha256"]:
        return "APK signing certificate changed"
    if fresh["version_code"] < old["version_code"]:
        return "Android versionCode went backwards"
    if fresh["version_code"] == old["version_code"] and fresh["sha256"] != old["sha256"]:
        return "APK changed without increasing Android versionCode"
    return None


def restore_previous(session, previous, dest, site_url):
    if not previous:
        return False
    filename = previous["filename"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.apk", filename):
        return False
    try:
        download(session, f"{site_url}/repo/{filename}", dest / filename)
        if sha256(dest / filename) != previous["sha256"]:
            raise ValueError("Previously published APK checksum mismatch")
        return True
    except Exception as e:
        print(f"  Couldn't restore previous APK: {e}", file=sys.stderr)
        (dest / filename).unlink(missing_ok=True)
        return False


def generate_metadata(metadata_dir, installed):
    metadata_dir.mkdir(parents=True, exist_ok=True)
    for entry in installed:
        info = {
            "Name": entry["name"],
            "Summary": entry["summary"],
            "Description": entry["summary"] + ". This APK is distributed by the project's owner.",
            "Categories": ["System"],
            "License": "Unknown",
            "SourceCode": entry["source_url"],
        }
        (metadata_dir / (entry["package"] + ".yml")).write_text(yaml.safe_dump(info, sort_keys=False, allow_unicode=True), encoding="utf-8")


def generate_home(site_dir, installed, site_url, repo_url):
    cards = []
    for item in installed:
        name, version = html.escape(item["name"]), html.escape(item["version_name"])
        source, filename = html.escape(item["source_url"], quote=True), html.escape(item["filename"], quote=True)
        cards.append(f'<article><h2>{name}</h2><p>{html.escape(item["summary"])} · {version} ({item["version_code"]})</p><a href="repo/{filename}">Download APK</a> · <a href="{source}">Source project</a></article>')
    body = "\n".join(cards) or "<p>No verified APKs available yet.</p>"
    page = f'''<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Roga App Repository</title><style>html{{color-scheme:dark;font:16px system-ui;background:#101816;color:#e6f1ed}}body{{max-width:760px;margin:40px auto;padding:0 20px}}h1{{font-size:2rem}}article{{background:#1b2925;padding:14px 20px;border-radius:16px;margin:12px 0}}a{{color:#90e5bf}}code{{overflow-wrap:anywhere;background:#24352f;padding:4px;border-radius:5px}}.sub{{color:#a4b6ad}}</style></head><body><h1>Roga App Repository</h1><p class="sub">Android apps from Roga-666 GitHub releases, distributed with a signed F-Droid index.</p><p>In Droid-ify, add the custom repository URL:</p><p><code>{html.escape(repo_url)}</code></p><p class="sub">These APKs are public downloads. APK signatures must remain consistent between app versions.</p>{body}<p><a href="{html.escape(site_url, quote=True)}/state.json">Publication details</a></p></body></html>'''
    (site_dir / "index.html").write_text(page, encoding="utf-8")
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="apps.json")
    parser.add_argument("--work", default="build/fdroid")
    parser.add_argument("--site", default="build/site")
    args = parser.parse_args()
    conf = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    work, site = Path(args.work), Path(args.site)
    repo = work / "repo"
    if work.exists():
        shutil.rmtree(work)
    if site.exists():
        shutil.rmtree(site)
    repo.mkdir(parents=True)
    site.mkdir(parents=True)
    token = os.environ.get("GH_READ_TOKEN") or os.environ.get("GITHUB_TOKEN")
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
    try:
        old_state = request_json(requests.Session(), f'{conf["site_url"]}/state.json', allow_missing=True) or {}
    except Exception as e:
        print(f"No previous published state: {e}")
        old_state = {}
    old_apps = old_state.get("apps", {})
    state = {}
    errors = {}
    seen_packages = set()
    for app in conf["apps"]:
        if not app.get("enabled", True):
            print(f'Skipping disabled app: {app["repository"]}')
            continue
        name = app["repository"]
        print(f"Checking {name}...", flush=True)
        previous = old_apps.get(name)
        try:
            url = f'https://api.github.com/repos/{conf["owner"]}/{name}/releases?per_page=30'
            try:
                releases = request_json(session, url)
            except requests.HTTPError as error:
                if error.response is not None and error.response.status_code == 404:
                    raise RuntimeError(
                        "GitHub returned 404. For private repositories, confirm GH_READ_TOKEN "
                        "is a valid fine-grained PAT belonging to the correct resource owner "
                        "with Contents: Read and access to this repository."
                    ) from error
                raise
            release, asset = choose_release(releases, app)
            if not asset:
                raise RuntimeError("No matching published APK releases")
            if previous and previous.get("asset_id") == asset["id"]:
                if not restore_previous(requests.Session(), previous, repo, conf["site_url"]):
                    raise RuntimeError("Previously published APK unavailable")
                entry = previous.copy()
            else:
                # Avoid authenticating to or trusting arbitrary release asset URLs.
                download_url = f'https://api.github.com/repos/{conf["owner"]}/{name}/releases/assets/{asset["id"]}'
                scratch = repo / f"download-{name}.apk"
                download(session, download_url, scratch, expected_size=asset.get("size"))
                details = inspect_apk(scratch)
                if details["debug_certificate"] and not app.get("allow_debug", False):
                    raise RuntimeError("Debug-signed APK excluded by policy")
                if details["package"] in seen_packages:
                    scratch.unlink(missing_ok=True)
                    raise RuntimeError("Another configured project has the same package ID")
                entry = {
                    "name": app["name"], "summary": app.get("summary", app["name"]),
                    "source_url": f'https://github.com/{conf["owner"]}/{name}',
                    "asset_id": asset["id"], "release_tag": release["tag_name"],
                    "sha256": sha256(scratch), **details,
                }
                rejection = validate_update(entry, previous)
                if rejection:
                    scratch.unlink(missing_ok=True)
                    raise RuntimeError(f"Blocked incompatible update: {rejection}")
                entry["filename"] = f'{name}_{details["package"]}_{details["version_code"]}.apk'
                scratch.replace(repo / entry["filename"])
            if entry["package"] in seen_packages:
                (repo / entry["filename"]).unlink(missing_ok=True)
                raise RuntimeError("Another configured project has the same package ID")
            seen_packages.add(entry["package"])
            state[name] = entry
            print(f'  Included: {entry["package"]} v{entry["version_name"]} code={entry["version_code"]}')
        except Exception as e:
            errors[name] = str(e)
            print(f"  Skipped {name}: {e}", file=sys.stderr, flush=True)
            if restore_previous(requests.Session(), previous, repo, conf["site_url"]):
                if previous["package"] not in seen_packages:
                    state[name] = previous
                    seen_packages.add(previous["package"])
                    print("  Kept previously published APK")
                else:
                    (repo / previous["filename"]).unlink(missing_ok=True)
    if not state:
        raise SystemExit("No APKs available; refusing to publish an empty repository")
    installed = list(state.values())
    generate_metadata(work / "metadata", installed)
    (site / "state.json").write_text(json.dumps({"apps": state}, indent=2) + "\n", encoding="utf-8")
    (site / "report.json").write_text(json.dumps({"included": list(state), "warnings": errors}, indent=2) + "\n", encoding="utf-8")
    generate_home(site, installed, conf["site_url"], conf["repo_url"])
    print(f"Imported {len(installed)} APKs. Skipped/warned on {len(errors)} repositories.")


if __name__ == "__main__":
    main()