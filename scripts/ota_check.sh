#!/usr/bin/env bash
# va7 skillset OTA check.
# Checks the skills repo remote for new commits vs the local copy.
# NEVER pulls automatically — prints what changed and how to apply.
#
# Usage: ota_check.sh [--repo /path/to/local/clone] [--remote owner/name]
# Env:   VA7_SKILLS_REPO   local clone path (default ~/.claude/skills-va7)
#        VA7_SKILLS_REMOTE git remote (default 1va7/va7-skills)

set -euo pipefail

REPO="${VA7_SKILLS_REPO:-$HOME/.claude/skills-va7}"
REMOTE="${VA7_SKILLS_REMOTE:-1va7/va7-skills}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --remote) REMOTE="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ ! -d "$REPO/.git" ]]; then
  echo '{"ok":false,"error":"no local clone at '"$REPO"'; clone first"}'
  exit 1
fi

cd "$REPO"
git fetch --quiet origin 2>/dev/null || {
  echo '{"ok":false,"error":"git fetch failed (offline or no access)"}'
  exit 1
}

LOCAL=$(git rev-parse HEAD)
REMOTE_REF=""
for candidate in origin/HEAD origin/main origin/master; do
  if git rev-parse --verify --quiet "$candidate" >/dev/null; then
    REMOTE_REF="$candidate"
    break
  fi
done
if [[ -z "$REMOTE_REF" ]]; then
  echo '{"ok":false,"error":"no origin/HEAD|main|master ref found"}'
  exit 1
fi

if [[ "$LOCAL" == "$(git rev-parse "$REMOTE_REF")" ]]; then
  echo '{"ok":true,"up_to_date":true,"local":"'"$LOCAL"'"}'
  exit 0
fi

# Behind: collect what changed
COUNT=$(git rev-list --count HEAD.."$REMOTE_REF")
COMMITS=$(git log --oneline --no-decorate HEAD.."$REMOTE_REF" | head -20)
FILES=$(git diff --stat HEAD.."$REMOTE_REF" | tail -5)

REMOTE_SHA=$(git rev-parse "$REMOTE_REF")
echo '{"ok":true,"up_to_date":false,'
echo '"local":"'"$LOCAL"'","remote":"'"$REMOTE_SHA"'","new_commits":'"$COUNT"','
echo '"commits":'
git log --pretty=format:'{"hash":"%h","subject":"%s"}' HEAD.."$REMOTE_REF" | head -20 | python3 -c "import json,sys; print(json.dumps([json.loads(l) for l in sys.stdin]))"
echo ',"changed_files":'
git diff --name-only HEAD.."$REMOTE_REF" | head -50 | python3 -c "import json,sys; print(json.dumps([l.strip() for l in sys.stdin]))"
echo '}'
