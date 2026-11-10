#!/usr/bin/env bash
# One-time setup for stable Android app signing on Vegapunk (works over SSH/Termius).
# Creates one private signing key per app and uploads matching Actions secrets.
# Does NOT merge pull requests, publish APKs, or alter the App-Store F-Droid repo key.
set -euo pipefail
umask 077

apps=(Huddle Redactor FlashTrim RelayLink LCPlus Ace-Abo Shizu-Go)
owner="Roga-666"
keydir="$HOME/roga-android-signing"

for bin in gh keytool base64; do
  command -v "$bin" >/dev/null || { echo "Missing required program: $bin" >&2; exit 1; }
done
gh auth status >/dev/null
mkdir -p "$keydir"
chmod 700 "$keydir"

echo "ANDROID APP SIGNING KEY SETUP"
echo "Separate .p12 keys will be saved under $keydir."
echo "The existing $HOME/roga-fdroid-repo.p12 repository key is NOT changed."
echo "WARNING: Previously installed APKs signed by different keys cannot be updated in place."
echo "If you have an existing reusable signing key, stop and recover it before generating a new one."
echo "These app APKs will be publicly downloadable after Droid-ify publication, even for private source repos."
read -r -p "Type YES to proceed with seven signing identities: " confirmation
[[ "$confirmation" == "YES" ]] || { echo "Cancelled without changes."; exit 0; }

for app in "${apps[@]}"; do
  repo="$owner/$app"
  keyfile="$keydir/$app-release.p12"
  echo
  echo "=== $repo ==="
  if [[ -e "$keyfile" ]]; then
    echo "Reusing existing key $keyfile (never overwriting it)."
    read -r -s -p "Enter its existing keystore password: " keypass
    echo
  else
    read -r -s -p "Choose a NEW, strong password (at least 16 characters) for $app: " keypass
    echo
    [[ ${#keypass} -ge 16 ]] || { echo "Password too short; stopping safely." >&2; exit 1; }
    read -r -s -p "Repeat password for $app: " checkpass
    echo
    [[ "$keypass" == "$checkpass" ]] || { echo "Passwords don't match; stopping safely." >&2; exit 1; }
    unset checkpass
    echo "Save this password in your password manager for $app."
    export APP_KEYSTORE_PASS="$keypass"
    keytool -genkeypair -keystore "$keyfile" -storetype PKCS12 -alias release \
      -keyalg RSA -keysize 4096 -validity 15000 \
      -storepass:env APP_KEYSTORE_PASS -keypass:env APP_KEYSTORE_PASS \
      -dname "CN=$app Android Release, O=Roga-666, C=US" -noprompt
    chmod 600 "$keyfile"
  fi

  export APP_KEYSTORE_PASS="$keypass"
  keytool -list -keystore "$keyfile" -storepass:env APP_KEYSTORE_PASS -alias release >/dev/null

  base64 -w0 < "$keyfile" | gh secret set ANDROID_RELEASE_KEYSTORE_BASE64 --repo "$repo"
  printf '%s' "$keypass" | gh secret set ANDROID_RELEASE_STORE_PASSWORD --repo "$repo"
  printf '%s' release | gh secret set ANDROID_RELEASE_KEY_ALIAS --repo "$repo"
  printf '%s' "$keypass" | gh secret set ANDROID_RELEASE_KEY_PASSWORD --repo "$repo"
  unset APP_KEYSTORE_PASS keypass
  echo "Signing key and four GitHub Actions secrets configured for $repo."
done

echo
echo "All seven app signing identities were configured."
echo "BACK UP $keydir securely; separately keep each app's password in a password manager."
echo "Do not store the keys in a Git repository or send their contents over chat."
echo "Next: review/merge the prepared signing PRs and inspect each release workflow."
