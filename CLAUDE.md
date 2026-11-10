# CLAUDE.md: rules for working on AIPayback

Read this file and `docs/PROGRESS.md` before doing anything. The full brief is `docs/BRIEF.md`; the approved plan is `docs/PLAN.md`.

## Start of every session
1. `git pull`. If there are conflicts, stop and explain them; never resolve them silently.
2. Read `docs/PROGRESS.md`: current phase, next step, blockers, budget.
3. `uv run aipb doctor` (checks billing safety; spends nothing).

## Money rules (hard; they override everything else)
- The app has **$15** of API credit (a $4 reserve is locked). Check with `uv run aipb budget`.
- Claude Code runs on the Claude subscription. **Never set or export `ANTHROPIC_API_KEY`**, in any shell, file or workflow. The app's key is `AIPAYBACK_API_KEY`, kept only in `.env` (git-ignored) and in GitHub Actions secrets.
- Every LLM call goes through `aipb.llm.client.LLMClient` inside a `BudgetGuard.start_run(...)` reservation. Never construct `anthropic.Anthropic` anywhere else.
- Before any paid run: print the worst-case estimate. Runs over $0.50 need `--confirm` **and** the CS student's go-ahead in chat. The S&P 100 run needs explicit cost approval.
- Never edit `config/budget.yaml` (`reserve_unlocked_usd`) without explicit approval recorded in `docs/DECISIONS.md`.
- Default model `claude-haiku-5-5`. Set thinking or effort explicitly on every stage (Haiku 5.5 thinks at `medium` by default, and thinking bills as output). Keep prompts under 100k tokens. Use batches for anything non-interactive and caching for stable prefixes.
- Commit every LLM output (`data/outputs/`) and the ledger (`data/ledger/`). Never pay twice.
- Re-check `config/pricing.yaml` against https://platform.claude.com/docs/en/about-claude/pricing before large runs.

## Accuracy and wording rules
- A wrong verdict about a real company is the worst failure. When unsure, publish "Status pending review", not a guess.
- Neutral language only. No "failed", "misled", "broke a promise". Statuses are: Delivered, On track, No evidence yet, Walked back (silent walk-backs are flagged separately).
- Quotes must match the source verbatim (checked by code). Every status cites both the promise and the evidence.
- Never invent, round up or cherry-pick numbers. Not investment or legal advice.

## Engineering conventions
- Python 3.12, uv (this Windows machine needs `system-certs`, already set in pyproject), ruff, pytest, typer CLI `aipb`. Each Makefile target is a one-line `uv run aipb ...`; `make` is optional on Windows.
- Stages are idempotent, resumable and cached. Prompts live in `prompts/<stage>/vN.md`; every result records its prompt version and model.
- CI is offline (`AIPAYBACK_OFFLINE=true`): no SEC calls, no API calls. Tests use fakes and fixtures only.
- Write JSONL with LF line endings (`newline="\n"`). The ledger and outputs use `merge=union`.
- `.env` is never committed; the pre-commit hook and CI block key patterns.

## Checkpoints (GitHub is the source of truth)
Commit and push every 30–45 minutes of work, whenever usage or context is getting high, and whenever the user types **"checkpoint"**. Update `docs/PROGRESS.md` first: phase, done, in progress (exact file and next step), blocked and on whom, resume commands, gotchas, latest eval numbers, budget spent and remaining. Never leave main broken without a note.

## End of every phase
Run tests (and evals once they exist), show `aipb budget`, update README, `docs/DECISIONS.md`, `docs/INTERVIEW_NOTES.md` and `docs/PROGRESS.md`, then commit and push. Report what was built, the key numbers, next steps for each human, and a 5-bullet "what you should understand" summary. **Then stop and wait for approval.**

## People
- **CS student (Gavin):** operator, approver, customer-facing lead. Approves phases and spend.
- **Finance student:** domain expert; not a programmer. Everything for them opens in Excel/Sheets or reads as Markdown, with step-by-step instructions. Files go through the shared Google Drive folder; the CS student commits them.

## Commit attribution
End commit messages with:
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
