# What the verifier should be

For the 2-day framework sprint. Structure follows the spec (the spec); the
quality bar follows how we actually want blogs written.

## The shape, unchanged from the spec

| Layer | Question | Deterministic | Owner |
|---|---|---|---|
| **1. Script** | Did it follow the instructions? | Yes | Quality owner |
| **2. Rubric** | Is it honest and readable? | No | Quality owner |
| **3. Traces** | What did it cost, how did it behave? | Yes | Infrastructure owner |

## The rule that decides everything else

**Grade only what the prompt instructed.** A framework that ignores an unstated
rule has not failed; we have. So every quality standard we want measured has to
be written into the frozen prompt first.

That is why there are two tiers.

## Tier 1 - the sprint

The frozen prompt in `prompt.md`. 17 checks, all prompt compliance:
both files exist, meta.json in the stated shape, 600-800 words, exactly three
topic sections and no other sections, every topic section linked to the feed,
the right top-3 topics, every link from the feed, no banned words, no stale
post cited or its facts used, the URL-less post not used, duplicate topic
merged, nothing written outside `/output`.

Word count and section count are in here **only because the prompt demands
them**, not because they are good blog rules. A real post is bound by the
answer it needs.

Run: `python3 verify.py --output ./output --feed feed.json`

## Tier 2 - how we want blogs written

Requires prompt v2 (`prompt_v2.md`), which adds the standards to the
instruction so they can be fairly graded. Nine scripted checks:

| Check | The rule behind it |
|---|---|
| Title under 60 chars | Fits the SERP |
| Title is not a question | Shape follows prompt type; this feed task is a selection/roundup, which ranks as a list |
| Title carries the top topic phrase | Searched phrase goes in the title, word for word |
| H2s are the topic phrases | Section structure is the strongest on-page signal we have evidence for |
| Every section carries a feed link | Claims are sourced where they are made |
| the product present, once, in the final section | Product arrives after the criteria |
| the product absent from title and intro | Never in the opening answer of a general explainer |
| Every product sentence grounded in the fact sheet | Nothing unverifiable about the product |

Run: `python3 verify.py ... --tier2 --product input/product.md`

## Prose quality

Seven soft checks, aligned to the `write-content` skill's anti-slop list so the
sprint measures the same standard our writers do: banned vocabulary, banned
phrases, binary contrasts, dash chains, transition density, stacked hedges,
triad overuse, and sentence-length variance.

**`harness` is deliberately excluded from the banned list.** It is our category
term. The AI tell is "harness the power of", not the noun.

These are soft: they produce `partial`, never `fail`. They are proxies for
prose that reads generated, not an authorship test. "Written by a human" is
not verifiable and nothing here claims to measure it.

Run: `python3 verify.py ... --tells`

## What is deliberately absent

| Not checked | Why |
|---|---|
| FAQ section | Google stopped showing FAQ rich results; FAQs are the weakest format for AI citation; FAQs are off by default in house style |
| Schema markup | A controlled test found no citation gain. Ship it cheaply, do not grade it |
| Product claim accuracy beyond the fact sheet | A writing input, not a review gate. It belongs in the knowledge base so the claim is never made |
| Keyword or volume targeting | The agent has a frozen feed and no keyword tool. Asking for it invites invented data |
| "Does this read human" | Not verifiable |

## Scoring

- **Pass** - every hard check passes
- **Partial** - hard checks pass, one or more soft checks fail
- **Fail** - any hard check fails

Every check maps to one of the spec's eight failure tags, so a failure
localises the break instead of only lowering a score. That matters because the
sprint's objective is finding where frameworks break, not ranking them.

## Running it for real

```bash
# tier 1 only - this is the sprint, and it is sufficient
python3 verify.py --output ./output --feed feed.json --banned banned_words.txt

# everything
python3 verify.py --output ./output --feed feed.json --banned banned_words.txt \
  --tier2 --product input/product.md --tells --json
```

Three runs per framework, five frameworks. Run the rubric judge three times per
output and take the majority: an LLM judge is non-deterministic too, and one
judgement is one sample.

**If Day 2 runs short, tier 1 is the sprint.** A clean comparison across five
frameworks is worth more than a richer test of one.
