# 30-minute discovery call guide

**Who runs it:** the CS student, with the finance student joining calls with finance users (fund members, advisors). **Goal:** learn how this person researches companies' AI claims **today**, what it costs them, and what would make a tool worth using or paying for. You're not demoing or selling.

**The one rule:** ask about **what they did last time**, not what they would do someday. "Walk me through the last time you checked a company's AI claim" gives facts. "Would you use a tool that…" gives polite fiction.

## Before the call (10 minutes)

- Read their LinkedIn and one thing they wrote or worked on.
- Copy [NOTES_TEMPLATE.md](NOTES_TEMPLATE.md) to `gtm/discovery/notes/YYYY-MM-DD_<name>.md` (the CS student commits it).
- Ask permission at the start to take notes, and to quote them anonymously in our write-up.

## Agenda

| Minutes | Section | Purpose |
|---|---|---|
| 0–3 | Intro | Who we are, why we're calling, ask permission to take notes |
| 3–18 | Their world | Their workflow, problem, time spent, tools |
| 18–25 | What useful means | What they'd trust, formats, willingness to pay |
| 25–30 | Close | What happens next, referrals, design-partner ask |

## 0–3: Intro (say it in your own words)

> "Thanks for making time. We're building a project that checks whether the AI promises companies make in SEC filings actually paid off. Before we build more, we're talking to people who deal with these claims, to learn how you do it today. There's nothing to buy. Is it OK if I take notes?"

## 3–18: Their world (most of the call)

Pick the questions that fit. Follow interesting answers instead of the list.

1. "What's your role, and where do companies' AI claims come up in your work?"
2. **"Walk me through the last time you had to check whether a company's AI claim was real."** Then: which company, what triggered it, where you looked, what you found.
3. "How long did that take? Roughly how often does it come up?" (Get a number: minutes per check, checks per month.)
4. "What tools or sources did you use?" (Filings, transcripts, Bloomberg/FactSet, news, ChatGPT, analysts' notes.)
5. "What was the hardest or most annoying part?"
6. "When you couldn't find an answer, what did you do?"
7. "Have you ever been burned by an AI claim that didn't hold up? What happened?"

**Segment-specific follow-ups:**
- *Student fund:* "How do AI claims show up in your investment memos? Who checks them?"
- *Professor:* "How do you or your students measure disclosure quality today? What data is missing?"
- *Advisor:* "How do clients phrase AI questions? What can you say given compliance limits?"
- *Journalist:* "What would you need to cite a finding like this: sourcing, caveats, timing?"
- *IR/compliance/legal:* "How do you review AI language before filing? Do you compare against peers? Who asks for that?"

## 18–25: What useful means

8. "If something did this for you, what would it have to get right for you to trust it?"
9. "What format would you actually use?" (A website, a spreadsheet export, alerts, a weekly email, an API or chat tool.)
10. "Which companies would you want covered first?"
11. **Willingness to pay** (ask about what they pay now, not hypotheticals): "What do you pay for research tools today? Who approves that spending? What's a tool like this replacing?" If it fits naturally: "Would $10 a month for alerts on your watchlist be an easy yes, a maybe or a no? Why?"

## 25–30: Close

- "What's the one thing we should build first for someone like you?"
- "Who else should we talk to?" (Ask for one name and an intro.)
- **Design-partner ask** (only if there's real interest): "Could we show you an early version in a few weeks and measure whether it saves you time? It's about 30 minutes of your time, twice."
- Thank them. Promise one specific follow-up and send it within 24 hours.

## After the call (within 1 hour)

1. Finish the notes file while it's fresh. Quote their exact words where you can.
2. Update [../outreach/tracker.csv](../outreach/tracker.csv).
3. If they agreed to be a design partner, record their **baseline time** for the ROI plan ([../ROI_PLAN.md](../ROI_PLAN.md)).
4. After 5 or more calls, Claude Code synthesizes them into `gtm/discovery/SYNTHESIS.md` (requirements, priorities, proposed plan changes).

## Don't

- Pitch, demo or describe features before minute 18.
- Ask "would you use…?" or "would you pay for…?" as your main questions.
- Argue with their answers or explain why they're wrong.
- Share any company verdict that isn't published with citations.
