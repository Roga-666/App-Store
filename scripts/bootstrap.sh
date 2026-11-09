#!/usr/bin/env bash
# One-time setup on your computer; does not expose signing keys or PATs in the public repo.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v git >/dev/null || { echo 'Install Git first'; exit 1; }
command -v gh >/dev/null || { echo 'Install GitHub CLI first: https://cli.github.com/'; exit 1; }
gh auth status >/dev/null || gh auth login
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git init -b main
fi
if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  git add .
  git commit -m 'Create signed F-Droid-compatible Roga App Repository'
fi
if gh repo view Roga-666/App-Store >/dev/null 2>&1; then
  echo 'Using existing Roga-666/App-Store repository'
  if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin https://github.com/Roga-666/App-Store.git
  fi
  git push --set-upstream origin main
else
  gh repo create Roga-666/App-Store --public --source=. --remote=origin --push \
    --description 'Droid-ify app repository automatically importing signed Android releases from my GitHub projects'
fi
echo 'Repository source uploaded.'
echo 'Next: configure repository signing and private release access.'
bash scripts/setup-secrets.sh
printf '\nSet GitHub Pages -> Build and deployment -> Source: GitHub Actions at:\n'
printf 'https://github.com/Roga-666/App-Store/settings/pages\n'
printf 'Then trigger Publish Droid-ify repository at:\n'
printf 'https://github.com/Roga-666/App-Store/actions\n'