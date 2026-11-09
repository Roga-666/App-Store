# Roga App Repository (Droid-ify / F-Droid)

A GitHub Pages-hosted, signed F-Droid-compatible app catalog for your own Android apps. The site and APK downloads are **public**. Source repositories can remain private. Only GitHub Releases APKs are imported; this tool does not build or re-sign application APKs.

**Planned site:** `https://roga-666.github.io/App-Store/`  
**Repository URL for Droid-ify:** `https://roga-666.github.io/App-Store/repo`

The URLs above are **not live until you create the repo, provide GitHub secrets, enable Pages, and successfully run the workflow**.

## Finish setup (Linux / macOS / WSL)

**The `Roga-666/App-Store` repository is already created and its source files are uploaded. Do not run the old bootstrap/push step.** The initial GitHub Action will fail until the repository-index signing secrets are configured; this is expected and prevents untrusted auto-generated keys.

1. On your computer, install [GitHub CLI](https://cli.github.com/) and a Java JDK with `keytool` (Linux Mint: `sudo apt install gh default-jdk`). Authenticate GitHub CLI with `gh auth login`.
2. Download this repository using `git clone https://github.com/Roga-666/App-Store.git` or download its ZIP from GitHub, and open a terminal in the `App-Store` folder.
3. Run `bash scripts/setup-secrets.sh`. This securely creates or reuses your long-lived F-Droid **repository-index signing key** at `~/roga-fdroid-repo.p12` and uploads the encrypted `FDROID_REPO_KEYSTORE_B64` and `FDROID_REPO_KEYSTORE_PASS` GitHub Actions secrets. **Back up the `.p12` key and password offline**; never paste them in chat or commit them to GitHub.
4. For importing your **private GitHub projects**, create a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new) scoped only to those source repositories, with **Contents: Read-only**. Paste it into the hidden script prompt; it will become the `GH_READ_TOKEN` GitHub Actions secret. Public projects like Attendance and RoMote Emerald do not need this token.
5. At [App-Store Settings → Pages](https://github.com/Roga-666/App-Store/settings/pages), select **Build and deployment → Source → GitHub Actions**.
6. At [App-Store Actions](https://github.com/Roga-666/App-Store/actions), choose **Publish Droid-ify repository → Run workflow**. Verify the job finishes successfully.
7. Then in Droid-ify → Repositories → Add, enter `https://roga-666.github.io/App-Store/repo`. The URL is not live until the Pages deployment succeeds.

**App signing is separate.** The repository-index signing key generated here does not replace any Android application signing keys. Only previously signed, compatible APK releases are selected for publishing; the draft signing fixes for your individual projects remain pending until you set up their own keys.

## How new releases are collected

GitHub Actions runs on manual dispatch, pushes to the configuration/scripts, and four times daily (every six hours). Each run:

1. Reads `apps.json` for the source repositories you chose.
2. Queries GitHub Releases, using the optional read-only `GH_READ_TOKEN` for private repos.
3. Selects the newest eligible **stable-signed** release with a single APK asset. Historical debug releases are excluded. The catalog currently expects `droidify-*` release tags from the newly signed apps, `emerald-upstream-*` from RoMote Emerald, and `v*` from Attendance.
4. Verifies APK signing with Android's `apksigner` and reads `packageName` / `versionCode` with `aapt`.
5. Blocks updates if the signer or application ID changes or the `versionCode` fails to increase for a changed APK. On a rejected update, attempts to retain the previously published version.
6. Creates signed F-Droid index files (`fdroidserver`), a catalog website, and a machine-readable publication report.
7. Deploys `repo/` and the website using GitHub Pages Actions.

## Add or remove apps

Edit `apps.json`, using the exact GitHub repository name. You can set:

```json
{
  "repository": "Your-App-Repository",
  "name": "Your App",
  "summary": "What this app does",
  "include_prereleases": false,
  "allow_debug": false,
  "release_tag_prefix": "droidify-",
  "asset_pattern": "universal.*\\.apk$"
}
```

`asset_pattern` is optional and useful when a GitHub release has several APK assets. Entries with no `enabled` field are enabled by default. Set `"enabled": false` to exclude an app without deleting its configuration. **PokeDialer Revived is explicitly disabled** until its experimental dialer behavior is tested; keep your stock Phone app. A repository with no eligible signed release (including apps whose signing migration is not yet configured) is skipped automatically. This is intentional: incompatible historical debug APKs must not appear as Droid-ify updates.

## Signing and updating: important

- The **repository-index key** created by `setup-secrets.sh` signs the F-Droid catalog, not Android apps. Keep the file `~/roga-fdroid-repo.p12` **and its password safely backed up**. If you lose it, existing Droid-ify installations may no longer trust a replacement repository index without re-adding a new repo.
- The Android **application signing certificate must be the same across APK versions** for updates to install over an existing app. Debug APKs are signed, but debug keys are frequently replaced when CI builds run on fresh runners. The catalog explicitly excludes historical debug APKs; it cannot make them stable. If the signature differs from the installed version, Android will refuse the update.
- Changing an app from an existing debug signing key to a production signing key will require a **one-time reinstall** for that app unless its keys already match. Back up app data first. The import script does not silently re-sign anyone's APKs.
- An app must increment Android `versionCode` on each changed APK to be detected as an update.
- Public GitHub Pages hosts **public APK files** even when they originated from private source repositories. Don't put confidential information, tokens, or secrets inside APKs. Always inspect builds before publishing.
- If the F-Droid signing secrets are missing, the workflow fails rather than generating a new repository key.

## Troubleshooting

- **The site is 404:** Check Pages is set to GitHub Actions and the `Publish Droid-ify repository` workflow succeeded.
- **Private repo returns 404:** Add the private repository to the `GH_READ_TOKEN` fine-grained PAT access list and check expiry. The default `GITHUB_TOKEN` does *not* read your other private repos.
- **App is missing:** Read the Actions job's `Publication summary`, or the deployed `report.json`. It may have no release APK, an ambiguous selection, invalid APK signing, or incompatible signature/version.
- **Update fails:** Check that both APKs use the same signing certificate and that the new APK's `versionCode` increased. Debug APKs from different runners may use different keys.
- **Failed to sign F-Droid index:** Check `FDROID_REPO_KEYSTORE_B64` and `FDROID_REPO_KEYSTORE_PASS` secrets and whether your saved keystore's alias is `fdroidrepo`.
- **Site is very large:** Only one APK per app is published. GitHub Pages has storage/bandwidth limits; consider moving to a different host if you expand greatly.

## Security model

- `GH_READ_TOKEN`: fine-grained, **Contents: Read** on selected source repos. The only use is to download release metadata and APKs. **Do not grant write access** for this importer.
- `FDROID_REPO_KEYSTORE_B64`: a base64-encoded repository-index keystore in Actions secrets.
- `FDROID_REPO_KEYSTORE_PASS`: password for that keystore, also in Actions secrets.
- Workflow temporary config and keys are **not uploaded** to Pages. Only the generated catalog, APK files, `state.json`, and `report.json` are deployed.
- GitHub Pages catalog trust is anchored by a persistent index signing key. Separately, each app APK remains signed by the upstream project's existing key.

## Local checks

Run `python -m pip install -r requirements.txt` and `python -m unittest discover -s tests -v` to test Python selection/signature policies. The full APK import and signed index publication require Android SDK build tools, a signing key, live releases, and GitHub Actions.