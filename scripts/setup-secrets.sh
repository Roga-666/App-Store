#!/usr/bin/env bash
# Run on YOUR computer; generates a stable repo INDEX signing key and uploads it as GitHub Secrets.
# Never commit the .p12 file or the password.
set -euo pipefail
umask 077
repo="Roga-666/App-Store"
command -v gh >/dev/null || { echo 'Install GitHub CLI (gh) first'; exit 1; }
command -v keytool >/dev/null || { echo 'Install a Java JDK with keytool first'; exit 1; }
command -v base64 >/dev/null || { echo 'base64 command missing'; exit 1; }
keyfile="$HOME/roga-fdroid-repo.p12"
if [[ -e "$keyfile" ]]; then
  echo "Existing key found at $keyfile — will reuse it. Back it up safely."
else
  echo 'Create a new F-Droid REPOSITORY signing key (not your Android app signing keys).'
  read -rsp 'Choose a long keystore password: ' KEY_PASS; echo
  [[ ${#KEY_PASS} -ge 8 ]] || { echo 'Use at least 8 characters'; exit 1; }
  export KEY_PASS
  keytool -genkeypair -alias fdroidrepo -keyalg RSA -keysize 4096 -validity 10950 \
    -storetype PKCS12 -keystore "$keyfile" -storepass:env KEY_PASS -keypass:env KEY_PASS \
    -dname 'CN=Roga App Repository, O=Roga-666, C=US' -noprompt
  unset KEY_PASS
fi
read -rsp 'Enter the keystore password: ' KEY_PASS; echo
export KEY_PASS
keytool -list -keystore "$keyfile" -storepass:env KEY_PASS -alias fdroidrepo >/dev/null
printf '%s' "$KEY_PASS" | gh secret set FDROID_REPO_KEYSTORE_PASS --repo "$repo"
# Base64 needs no line wrapping in repo secrets; file size is small.
base64 < "$keyfile" | tr -d '\n' | gh secret set FDROID_REPO_KEYSTORE_B64 --repo "$repo"
unset KEY_PASS
printf '\nPaste a fine-grained GitHub PAT with Contents: Read on selected source repos.\n'
read -rsp 'PAT (input hidden): ' GH_PAT; echo
if [[ -n "$GH_PAT" ]]; then
  printf '%s' "$GH_PAT" | gh secret set GH_READ_TOKEN --repo "$repo"
  unset GH_PAT
  echo 'Private release access configured.'
else
  echo 'No PAT configured — private GitHub releases will be skipped.'
fi
echo "Done. Keep $keyfile and its password backed up securely."