#!/bin/bash
# Mac side of the drip: stage "make the draft" items as UNSENT drafts / print sets. Never sends, never prints.
cd "$HOME/landtek" || exit 1
ssh -o BatchMode=yes -o ConnectTimeout=10 -N -L 15432:172.18.0.3:5432 landtek & T=$!; trap "kill $T 2>/dev/null" EXIT; sleep 4
/usr/bin/env python3 scripts/drip_stager.py >> ops/drip/drip_stager.log 2>&1
