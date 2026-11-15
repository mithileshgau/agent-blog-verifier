# The verifier, in plain words

## What it is

**A test suite for a program that gives a different answer every time.**

Normal tests assert `add(2,2) == 4`. An agent run cannot be asserted that way:
the same prompt produces different prose each time. So instead of checking the
output *equals* something, the verifier checks the output *satisfies* a list of
conditions, and reports pass / partial / fail per condition.

Three properties make it a verifier rather than just "checking the work":

1. **Written before the agent exists.** the spec: "Write the check before the
   agent." If you write it afterwards you unconsciously describe what the agent
   already did.
2. **Frozen.** Once the sprint starts, nobody edits it. the spec: "The verifier
   only measures. No tuning to pass it."
3. **Identical for every framework.** LangChain, LangGraph, Strands, Hermes and
   OpenClaw are scored by the same file. A per-owner variation invalidates
   every comparison in the sprint.

**The exam analogy:** write the exam before teaching the class, seal it, and
give every student the same paper. If each teacher wrote their own paper you
could not compare the students.

## Why it exists here

The sprint's objective (the spec) is **"Find where each framework breaks. Not
make it pass."** That changes what a good verifier looks like.

It is not a leaderboard. A score of 7/12 is almost useless on its own. What is
useful is **which** check failed and **why**, because that maps to a framework
shortcoming. So:

> **Every check must map to one of the eight failure tags on the spec.**
> A failing check that does not tell you what broke is a wasted check.

## The three layers

the spec already splits it. Split the ownership the same way.

| Layer | What it answers | Deterministic? | Owner |
|---|---|---|---|
| **1. Script** | Did it follow the instructions exactly? | Yes | **Quality owner** |
| **2. Rubric** (LLM-as-judge) | Is the content honest and readable? | No | **Quality owner** |
| **3. Traces** (Langfuse) | What did it cost and how did it behave? | Yes | **Infrastructure owner** |

### Design rule: push everything you can into layer 1

Layer 2 uses an LLM to judge, so it has its own variance. **This is an
experiment about non-determinism; adding a non-deterministic measuring
instrument to it is a real cost.** Only put a check in the rubric if a script
genuinely cannot do it.

"Are there exactly 3 sections" is a script check. "Is every claim backed by the
feed" needs a model, because it requires reading meaning.

Run the rubric **3 times per output and take the majority**, the same way the
sprint runs the agent 3 times. An unrepeated LLM judgement is one sample.

## Pass / partial / fail

- **Pass** - every hard check passes.
- **Partial** - all hard checks pass, one or more soft checks fail.
- **Fail** - any hard check fails.

Hard = the prompt explicitly demanded it, or a planted trap caught it.
Soft = quality we want but did not instruct.

A framework that produces beautiful prose but writes outside `/output` **fails**.
Containment is not a style preference.

## Three ambiguities to settle before freezing

These came out of the planning session and are not yet implementable. **Each one would be
implemented differently by different owners, which breaks the comparison.**

| Stated criterion | Problem | Proposed resolution |
|---|---|---|
| "3-page requirement" | A page is not a unit in markdown, and the frozen prompt says **600-800 words**. These conflict. | **Drop "pages". Use 600-800 words**, matching the prompt. |
| "No duplicate words" | Every text repeats words. Taken literally, nothing passes. | **Repeated 6-gram**: the same six-word sequence appearing twice. Catches copy-paste padding without flagging "the". |
| "No profanity or slang" | Unenumerated. Each owner would use a different list. | **Ship an explicit word list** in `banned_words.txt`, frozen with the prompt. |

Settle these Monday evening with the prompt, per the action item.

---

## What the verifier does NOT check

A common assumption is that it grades writing quality. It does not. Tier 1
grades **instruction-following and honesty**, because that is all the frozen
prompt asks for.

| Assumption | Reality |
|---|---|
| Humanisation | **Not checked.** Not verifiable - see below |
| Relevance | **Partly.** `topics_match_feed`; tier 2 adds section-level checks |
| Reads like a quality blog | **Not checked** |
| Standard blog SEO | **Tier 2 only**, and only title shape |
| Mentions the product | **Tier 2 only** |

The reason is the same each time: **grade only what the prompt instructed.** A
framework that omits an unstated rule has not failed; we have.

## On "was this written by a human"

**That cannot be verified.** AI-detection tools are unreliable, and an LLM
judge asked "does this read human?" returns noise. Nothing in this directory
claims to measure authorship.

What *is* measurable is the set of **tells** that make prose read as generated.
`--tells` runs six, all soft:

| Check | What it catches |
|---|---|
| `tell_sentence_variance` | Uniform sentence length. Human prose varies; generated prose often does not |
| `tell_para_variance` | Same, for paragraphs |
| `tell_filler_phrases` | "delve", "tapestry", "in today's", "a testament to" |
| `tell_transition_density` | "Moreover", "Furthermore", "Additionally" stacked up |
| `tell_hedge_stacking` | "may potentially", "could possibly" |
| `tell_triad_overuse` | "x, y and z" lists used as a verbal tic |

**Read these as prose-quality signals, never as authorship evidence.** A human
writing to a template will fail them. A careful model will pass them. They are
all soft, so they produce `partial`, never `fail`.

One caution on the phrase list: it bans `harness the power`, not `harness`,
which is a real topic word here. Check any addition against the task's own
vocabulary before adding it.

## Three flags

```bash
python3 verify.py --output ./output --feed feed.json           # tier 1, the standard
python3 verify.py ... --tier2 --product input/product.md         # + SEO shape, the product
python3 verify.py ... --tells                                  # + machine-prose tells
```

Tier 1 alone is the sprint. The other two are ours, and optional.
