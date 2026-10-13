#!/bin/sh
# Copies the drive's copy of the skill into this repo. Run, review the diff, commit, push.
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
rsync -a --delete --exclude __pycache__ \
  "$HOME/Marble Drive/.claude/skills/envisioning-fluency/" "$here/skills/envisioning-fluency/"
git -C "$here" status --short
