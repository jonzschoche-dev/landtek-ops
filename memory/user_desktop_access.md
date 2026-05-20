---
name: user-desktop-access
description: Jonathan accesses Claude Code from desktop (not just phone/Termius); response formatting should not assume mobile constraints
metadata: 
  node_type: memory
  type: user
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

Jonathan accesses Claude Code from desktop, not just phone/Termius (correction made 2026-05-19; earlier CLAUDE.md hint suggesting phone-via-Tailscale-Termius is at least incomplete).

**How to apply:**

- Don't assume 4-inch screen scroll constraints when formatting responses. Full-width tables, longer prose paragraphs, multi-section layouts are all fine.
- For genuinely long-form answers (>3,000 words or dense tables), write to `/root/landtek/drafts/<topic>.md` and surface a 1-paragraph summary + link. This keeps the chat clean while preserving the deep artifact.
- Brief responses still right for simple questions; detail still right for architectural discussions.
- When suggesting how Jonathan can do something on his end, default to desktop-friendly steps (mouse-wheel scroll, Cmd+F search, browser tabs) rather than Termius-specific two-finger swipes.

**History access on desktop:**
- Best: claude.ai/code (web UI with sidebar history + search)
- Fallback: read the session JSONL directly at `/root/.claude/projects/-root-landtek/<session-id>.jsonl`
- For live CLI work: terminal scrollback (bump iTerm/Windows Terminal to 100k+ lines) + `tee ~/claude-$(date +%F).log` if persistence is wanted

**Phone/Termius is still a possibility** — Jonathan does have that path — but it's not the default assumption. If he says he's on his phone, switch to mobile-friendly format. Otherwise, write for desktop.
