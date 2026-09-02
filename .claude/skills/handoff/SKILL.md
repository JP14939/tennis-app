---
name: handoff
description: Refresh HANDOVER.md and STATUS.md into a clean, current handoff for a new Claude Code session picking up this project. Project-specific to RallyMax/tennis_app — does not write to a temp file.
argument-hint: "optional: what this session focused on, if it's not obvious from the conversation"
disable-model-invocation: true
---

# Handoff: refresh HANDOVER.md + STATUS.md

This project keeps three docs, each with a distinct job (defined in
`CLAUDE.md` — read that section first if you haven't):

- **`HANDOVER.md`** — comprehensive, mostly-chronological project log. The
  "give someone the full picture" doc.
- **`STATUS.md`** — short, hand-curated, fully **overwritten** each time
  (not appended to) — "where do things stand right now," readable in under
  2 minutes.
- **`TODO_MANUAL.md`** — separate doc, things only a human can do. **Not
  this skill's job** — don't touch it here unless the user explicitly asks.

The failure mode this skill exists to prevent: `HANDOVER.md` growing into
an append-only wall of chronological narration (it's over 1000 lines as of
writing, with a single "Last updated" line listing a dozen-plus
parenthetical session extensions) that's technically complete but too
dense for a fresh session — or a human — to get oriented from quickly.
`STATUS.md` is supposed to be the fast-read antidote, but only if it's
actually kept current.

## Steps

1. **Gather real state before writing anything.** Don't work from memory
   of the conversation alone:
   - Read the current `HANDOVER.md`, `STATUS.md` in full.
   - Run `git log --oneline -20` and `git status --short` — anything
     committed or in-flight that isn't reflected in the docs yet is a gap
     to close.
   - If the user passed an argument, treat it as what this session focused
     on and make sure that's what gets captured — don't guess if it
     conflicts with what you observe in git/conversation.
   - Skim this conversation's own history for anything decided, built,
     fixed, or found that isn't already committed/documented (a bug found
     but not yet fixed, a decision made but not yet acted on, a thing the
     user explicitly deferred).

2. **Append one new dated entry to `HANDOVER.md`'s changelog** (top of
   file, matching the existing "Last updated: ... extended again
   YYYY-MM-DD (...)" pattern) summarizing what happened since the last
   entry — factual, specific, no fluff. Reference PR/commit/issue numbers
   where they exist instead of re-describing the diff. If something is a
   **standing open bug or decision**, say so explicitly — don't let it
   read as resolved if it isn't.

3. **Compress stale detail while appending** — same principle as
   `TODO_MANUAL.md`'s 2026-08-26 compression pass (check `git log` for
   that commit if you want the reference shape): anything in "Read This
   First," "Known Gaps," or elsewhere that's since been resolved gets
   collapsed to a one-line breadcrumb (what it was + resolution date),
   not deleted outright (history has value) and not left at full original
   length (that's the bloat this skill exists to fix). Anything still
   open or architecturally load-bearing stays at full detail. Do **not**
   collapse the giant "Last updated" line's old entries — that line is
   itself the changelog; leave earlier entries in it alone and just add
   the new one. If it's grown unreadably long as a single run-on sentence,
   ask the user before restructuring it into a list — that's a bigger
   format change than a normal update.

4. **Fully rewrite `STATUS.md`** (overwrite, don't append) to reflect true
   current state, readable in under 2 minutes:
   - What's actually working / shipped and confirmed.
   - What's in-flight or half-done, and exactly where it was left off.
   - Any standing open bugs or decisions blocking on the user, stated
     plainly (this is the single most important thing a fresh session or
     a human catching up needs to see immediately — don't bury it).
   - Immediate next step(s), if there's an obvious one.

5. **Redact secrets.** API keys, tokens, passwords, or anything
   personally identifying beyond the user's own known email/name — check
   both docs for anything that slipped in before finishing.

6. **Report back**: line-count before/after for `HANDOVER.md`, and a short
   list of what the new changelog entry and `STATUS.md` now say — so the
   user can sanity-check the summary before trusting it, not just take it
   on faith.

## Notes

- This is a deliberate, occasional action (end of a substantial session,
  or explicitly requested) — not something to run automatically or
  invoke the model into doing unprompted, hence
  `disable-model-invocation: true`.
- If `HANDOVER.md` or `STATUS.md` don't exist yet, create them following
  the structure/tone of whichever one does exist, or ask the user for the
  minimum context needed (what the project is, current architecture) if
  neither exists.
