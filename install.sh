#!/bin/sh
# Installs the envisioning-fluency skill into ~/.claude/skills (or $SKILLS_DIR).
#   curl -fsSL https://raw.githubusercontent.com/bdhmin/envisioning-fluency/main/install.sh | sh
#   curl -fsSL .../install.sh | SKILLS_DIR=~/.agents/skills sh
set -eu
dest="${SKILLS_DIR:-$HOME/.claude/skills}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL https://github.com/bdhmin/envisioning-fluency/archive/refs/heads/main.tar.gz | tar -xz -C "$tmp"
mkdir -p "$dest"
rm -rf "$dest/envisioning-fluency"
cp -R "$tmp"/envisioning-fluency-main/skills/envisioning-fluency "$dest/"
echo "Installed to $dest/envisioning-fluency"
echo "Open your agent and ask it for your envisioning fluency."
