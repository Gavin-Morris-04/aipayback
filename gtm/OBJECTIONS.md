# Objection handling

Answer with the mechanism first, then the measured number (fill `[[...]]` from the latest eval results; if a number isn't measured yet, say so).

**"How do I know it's accurate?"**
Three layers. Code checks every quote against the filing text. Every status cites the sentences it relies on, and code checks each citation too. Accuracy is measured against hand labels by a finance student on companies we never tuned on: `[[F1]]` for finding promises and `[[precision]]` for published statuses. The Methodology page shows those numbers and their intervals.

**"LLMs hallucinate."**
That's why the model never writes a fact on its own. Quotes must match the filing word for word (checked by code). Numbers come from XBRL and arithmetic is done by code. Explanations can only cite the documents we give the model, and each citation is verified. When the evidence is thin, we publish "Status pending review" instead of a guess.

**"Why not just ask ChatGPT?"**
Try it on one of your companies and compare. Check whether you get every promise across three years of filings, the exact sentences, and the later evidence with SEC links, and whether you get the same answer twice. We publish our measured error rate, and our results are the same for everyone, so you can cite them.

**"Isn't 'Walked back' accusatory?"**
It only means a later filing lowered, delayed or dropped the commitment, and we quote that filing. It needs two independent checks that agree. We never use words like "failed" or "misled", and code blocks them in every generated sentence.

**"How fresh is it?"**
New filings are processed monthly, and each promise page shows the latest filing date we used. Promises from late 2025 often read "No evidence yet" simply because little time has passed; we say so.

**"Is this investment or legal advice?"**
No. It's data about what filings say. Every page and email says so.

**"What about earnings calls and news?"**
Out of scope for v1, on purpose: SEC filings are the record companies are accountable for. If partners need calls, that's a candidate for a later phase.

**"Is our data safe?"**
We only use public SEC data, and nothing you share with us is published. Keys and credentials are kept out of the code and scanned for on every commit.

**"It's a student project. Will it be maintained?"**
The monthly update and newsletter run automatically, with budget caps and fail-closed checks. Pilots are scoped to deliverables that are complete on delivery.
