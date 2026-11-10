#!/usr/bin/env bash
# One-time release signing for Roga-666/External-Cam.
# Follows the same layout and secret naming as setup-android-app-signing.sh.
# Only acts on External-Cam; never touches the other apps or F-Droid repo key.
set -euo pipefail
umask 077

owner="Roga-666"
app="External-Cam"
repo="$owner/$app"
keydir="$HOME/roga-android-signing"
keyfile="$keydir/$app-release.p12"
alias_name="release"

for bin in gh keytool base64; do
  command -v "$bin" >/dev/null || { echo "Missing required program: $bin" >&2; exit 1; }
done
gh auth status >/dev/null
gh repo view "$repo" >/dev/null
mkdir -p "$keydir"
chmod 700 "$keydir"

echo "EXTERNAL CAM - PERMANENT ANDROID RELEASE SIGNING"
echo "Repository: $repo"
echo "Keystore: $keyfile"
echo "The seven existing app keys and your separate Droid-ify repository key are NOT touched."
echo "Keep this key and its password for ALL subsequent External Cam releases."
echo

if [[ -e "$keyfile" && ! -f "$keyfile" ]]; then
  echo "Cannot use $keyfile: it exists but is not a regular file." >&2
  exit 1
fi

if [[ -f "$keyfile" ]]; then
  echo "Reusing existing External Cam signing key; it will NOT be replaced."
  read -r -s -p "Enter the EXISTING keystore password: " keypass
  echo
  [[ -n "$keypass" ]] || { echo "Password required." >&2; exit 1; }
else
  echo "IMPORTANT: If you already created an External Cam signing key elsewhere,"
  echo "do not create a new identity. Reuse your existing key instead."
  read -r -p "Type CREATE to generate a new External Cam key: " confirm
  [[ "$confirm" == "CREATE" ]] || { echo "Cancelled without changes."; exit 0; }

  read -r -s -p "Choose a new strong password (at least 16 characters): " keypass
  echo
  [[ ${#keypass} -ge 16 ]] || { echo "Password is too short." >&2; exit 1; }
  read -r -s -p "Repeat password: " confirm_pass
  echo
  [[ "$keypass" == "$confirm_pass" ]] || { echo "Passwords do not match." >&2; exit 1; }
  unset confirm_pass

  export EXTERNAL_CAM_KEYPASS="$keypass"
  keytool -genkeypair -keystore "$keyfile" -storetype PKCS12 -alias "$alias_name" \
    -keyalg RSA -keysize 4096 -validity 15000 \
    -storepass:env EXTERNAL_CAM_KEYPASS -keypass:env EXTERNAL_CAM_KEYPASS \
    -dname "CN=External Cam Android Release, O=Roga-666, C=US" -noprompt
  chmod 600 "$keyfile"
fi

export EXTERNAL_CAM_KEYPASS="$keypass"
keytool -list -keystore "$keyfile" -storetype PKCS12 \
  -storepass:env EXTERNAL_CAM_KEYPASS -alias "$alias_name" >/dev/null

# Pipe secrets directly from the local machine. Never print passwords or Base64 to screen.
base64 -w0 < "$keyfile" | gh secret set ANDROID_RELEASE_KEYSTORE_BASE64 --repo "$repo"
printf '%s' "$keypass" | gh secret set ANDROID_RELEASE_STORE_PASSWORD --repo "$repo"
printf '%s' "$alias_name" | gh secret set ANDROID_RELEASE_KEY_ALIAS --repo "$repo"
printf '%s' "$keypass" | gh secret set ANDROID_RELEASE_KEY_PASSWORD --repo "$repo"

unset EXTERNAL_CAM_KEYPASS keypass
echo
echo "External Cam: four repository signing secrets configured."
echo "BACK UP securely: $keyfile"
echo "Keep its password in your password manager; never store it in Git or in chat."
echo "Starting External Cam signed-release workflow..."
gh workflow run release.yml --repo "$repo" --ref main
echo "Release workflow requested. Check: https://github.com/$repo/actions/workflows/release.yml"
echo "After successful signature verification, the APK appears at: https://github.com/$repo/releases"
