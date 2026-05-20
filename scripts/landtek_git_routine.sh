#!/usr/bin/env bash
# landtek_git_routine.sh — the multi-agent git routine, scriptified.
# Works on either VPS (/root/landtek) or Mac (~/landtek).
# Safe by default: never force-pushes, never blanket-adds, never auto-merges.
#
# Per [[feedback_multi_agent_git_routine]] (P0 memory rule).
#
# Usage:
#   landtek_git_routine.sh start       # session-start: sync + report state
#   landtek_git_routine.sh end         # session-end: surface unpushed work
#   landtek_git_routine.sh check       # one-shot health snapshot (no changes)
#   landtek_git_routine.sh deploy <NN> "short description" path1 path2 ...
#                                       # commit specific files with deploy_NN tag + push

set -euo pipefail

# Resolve repo path — VPS uses /root/landtek, Mac uses $HOME/landtek
if [ -d "/root/landtek/.git" ]; then
  REPO=/root/landtek
elif [ -d "$HOME/landtek/.git" ]; then
  REPO="$HOME/landtek"
else
  echo "✗ Can't find landtek repo at /root/landtek or \$HOME/landtek" >&2
  exit 1
fi

cd "$REPO"

# Identify which side we're on (for handoff messages)
if [ -d "/root/landtek/.git" ] && [ "$REPO" = "/root/landtek" ]; then
  SIDE="VPS"
else
  SIDE="Mac"
fi

CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; GREEN='\033[0;32m'; RESET='\033[0m'

hdr() { printf "${CYAN}━━━ %s ━━━${RESET}\n" "$1"; }
warn() { printf "${YELLOW}⚠ %s${RESET}\n" "$1"; }
err()  { printf "${RED}✗ %s${RESET}\n" "$1"; }
ok()   { printf "${GREEN}✓ %s${RESET}\n" "$1"; }

cmd=${1:-check}

case "$cmd" in
  start)
    hdr "Session start — $SIDE side · $(date -u +%H:%M:%SZ)"
    echo ""

    hdr "Step 1: fetch origin"
    git fetch origin main 2>&1 | tail -3 || true
    echo ""

    hdr "Step 2: any pre-existing dirty state?"
    dirty=$(git status --short)
    if [ -n "$dirty" ]; then
      warn "Working tree dirty before pull:"
      echo "$dirty"
      echo ""
      warn "Decide before pulling: commit, discard daemon-churn, or ask Jonathan."
      exit 2
    else
      ok "Working tree clean"
    fi
    echo ""

    hdr "Step 3: incoming commits from other agents"
    incoming=$(git log --oneline HEAD..origin/main 2>/dev/null || true)
    if [ -n "$incoming" ]; then
      echo "$incoming"
      echo ""
      hdr "Step 4: pull --rebase"
      git pull --rebase 2>&1 | tail -5
      ok "Pulled $(echo "$incoming" | wc -l | tr -d ' ') new commits"
    else
      ok "Up to date with origin/main"
    fi
    echo ""

    hdr "Session-start summary"
    echo "  Side:         $SIDE"
    echo "  Repo:         $REPO"
    echo "  HEAD:         $(git log -1 --oneline)"
    echo "  Branch:       $(git rev-parse --abbrev-ref HEAD)"
    echo "  Memory:       $(ls memory/ 2>/dev/null | wc -l | tr -d ' ') files"
    ;;

  end)
    hdr "Session end — $SIDE side · $(date -u +%H:%M:%SZ)"
    echo ""

    hdr "Uncommitted work"
    dirty=$(git status --short)
    if [ -n "$dirty" ]; then
      echo "$dirty"
      warn "Commit before close OR explicitly defer."
    else
      ok "None"
    fi
    echo ""

    hdr "Committed but unpushed"
    unpushed=$(git log --oneline @{push}..HEAD 2>/dev/null || true)
    if [ -n "$unpushed" ]; then
      echo "$unpushed"
      warn "Push now or other agents see stale state."
    else
      ok "None"
    fi
    echo ""

    hdr "Untracked files (likely real work?)"
    # set -e + pipefail makes empty grep results exit 1, masking real state.
    # `|| true` keeps the pipeline successful when nothing matches.
    untracked=$(git ls-files --others --exclude-standard \
                  | { grep -v '^drafts/daily_digest_' || true; } \
                  | { grep -v '\.mac-backup\|\.vps-backup' || true; } \
                  | head -20)
    if [ -n "$untracked" ]; then
      echo "$untracked"
      warn "Review — stage + commit, gitignore, or leave as scratch?"
    else
      ok "None worth flagging"
    fi
    echo ""

    hdr "Handoff template"
    cat <<EOF
  Session summary ($SIDE side):
    HEAD:    $(git log -1 --oneline)
    PUSHED:  $(git log --oneline HEAD..origin/main 2>/dev/null | wc -l | tr -d ' ') commits behind origin
    PENDING ON OTHER END: <fill in>
    NEXT NATURAL MOVE:    <fill in>
EOF
    ;;

  check)
    hdr "Quick health snapshot — $SIDE"
    echo "  HEAD:         $(git log -1 --oneline)"
    echo "  Behind origin: $(git fetch origin main >/dev/null 2>&1; git log --oneline HEAD..origin/main | wc -l | tr -d ' ') commits"
    echo "  Ahead origin:  $(git log --oneline origin/main..HEAD | wc -l | tr -d ' ') commits"
    echo "  Modified:     $(git status --short --untracked-files=no | wc -l | tr -d ' ') files"
    echo "  Untracked:    $(git ls-files --others --exclude-standard | wc -l | tr -d ' ') files"
    ;;

  deploy)
    [ $# -lt 4 ] && { err "Usage: deploy <NN> \"description\" path1 [path2 ...]"; exit 2; }
    nn="$2"; desc="$3"; shift 3
    paths=("$@")

    hdr "deploy_${nn}: $desc"
    echo "  Side:  $SIDE"
    echo "  Files: ${paths[*]}"
    echo ""

    # Pull-rebase first (per protocol)
    hdr "Pre-flight pull"
    git fetch origin main 2>&1 | tail -1
    if [ -n "$(git log --oneline HEAD..origin/main 2>/dev/null)" ]; then
      git pull --rebase 2>&1 | tail -3
    else
      ok "Already at tip"
    fi
    echo ""

    # Truth-test gate (deploy_221C onward). Asserts the bulletproof base
    # is intact against VPS DB. Failure blocks the deploy.
    # Skip with: LANDTEK_SKIP_TRUTH_TESTS=1 (only for cases where the deploy
    # explicitly modifies a previously-locked truth — must be matched by a
    # truth_tests/ assertion update in the same deploy).
    if [ -z "$LANDTEK_SKIP_TRUTH_TESTS" ] && [ -d "$REPO/truth_tests" ]; then
      hdr "truth_tests pre-deploy gate"
      if [ "$SIDE" = "VPS" ]; then
        if ! python3 "$REPO/truth_tests/run_all.py"; then
          err "truth_tests FAILED — deploy blocked. Investigate data-layer drift before retrying."
          err "If this is an intentional truth update, run with: LANDTEK_SKIP_TRUTH_TESTS=1 $0 deploy ... (and include the corresponding test update)."
          exit 3
        fi
      else
        # Mac side: tests run against VPS DB state via SSH.
        if ! ssh -o ConnectTimeout=10 root@100.85.203.58 \
            "cd /root/landtek && python3 truth_tests/run_all.py" ; then
          err "truth_tests FAILED on VPS — deploy blocked."
          err "Skip with: LANDTEK_SKIP_TRUTH_TESTS=1 $0 deploy ..."
          exit 3
        fi
      fi
      ok "truth_tests passed"
      echo ""
    fi

    hdr "Stage specific paths"
    git add "${paths[@]}"
    git status --short | head -10
    echo ""

    hdr "Commit"
    git commit -m "deploy_${nn}: ${desc}

Auto-tagged by landtek_git_routine.sh on ${SIDE}."
    echo ""

    hdr "Push"
    if ! git push origin main 2>&1 | tail -3; then
      warn "Push rejected — re-pulling + retrying"
      git pull --rebase 2>&1 | tail -3
      git push origin main 2>&1 | tail -3
    fi
    ok "deploy_${nn} live"
    ;;

  *)
    err "Unknown command: $cmd"
    echo "Usage: $0 {start|end|check|deploy <NN> \"desc\" paths...}"
    exit 2
    ;;
esac
