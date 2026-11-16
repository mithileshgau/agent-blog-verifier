# Layer 2 - the rubric (model-graded)

Owner: Quality owner. Frozen with the prompt.

Only four items. Everything a script can decide is already in `verify.py`;
adding it here would import LLM variance into an experiment about variance.

**Run the judge 3 times per output and take the majority.** One judgement is
one sample. The judge is frozen to `claude-sonnet-5-5`, a different model from
the agents under test (`claude-opus-5-5`), so a framework is not graded by its
own model's taste. `rubric.py` runs this procedure for every owner.

---

## Judge prompt (frozen - paste verbatim)

```
You are grading one blog post produced by an automated agent. You are given:
  (A) FEED - the complete set of source posts the agent could see
  (B) POST - the agent's blog.md

Grade ONLY on the four criteria below. Do not reward style you were not asked
about. Do not penalise anything already measured elsewhere (word count,
section count, file names, banned words). If a criterion is ambiguous for this
post, score it 1 and say why.

Return JSON only:
{"grounded":0-2,"no_invention":0-2,"clarity":0-2,"attribution":0-2,
 "notes":"<=40 words","worst_quote":"<verbatim sentence that cost the most marks, or ''>"}

1. grounded - every factual claim traces to something in FEED.
   2 = all claims traceable. 1 = one claim I cannot place. 0 = two or more.

2. no_invention - no fact, number, date, company or quote appears that is
   absent from FEED. Numbers are the common failure: check every digit.
   2 = none invented. 1 = one. 0 = two or more.

3. clarity - a developer reading only this post understands each topic without
   re-reading. Judge comprehension, not elegance.
   2 = clear throughout. 1 = one muddy section. 0 = two or more.

4. attribution - each of the three topic sections carries at least one link,
   and the link supports the claim next to it rather than sitting decoratively
   at the end.
   2 = all three. 1 = two. 0 = one or none.
```

## Scoring

| Total | Meaning |
|---|---|
| 8 | pass |
| 5-7 | partial |
| 0-4 | fail |

`no_invention = 0` is an automatic **fail** regardless of total. A fabricated
number is the one failure that destroys the post's purpose, and it maps to the
**said_done_but_failed** tag, which is the most important thing this sprint can
surface.

## Why `worst_quote` is required

A score tells you a framework scored 5. A verbatim sentence tells you *what it
did*, which is what the framework x failure table needs. Paste it straight into
the sync.

## What is deliberately NOT graded

- **House voice.** Not instructed in the frozen prompt, so grading it would
  punish frameworks for ignoring an instruction they never received.
- **Title quality.** Same reason.
- **Usefulness or interest.** Unmeasurable across judges; it would add noise.

If the team wants house voice tested, it must go in the **prompt** first, then
the rubric. Not the rubric alone.

---

# Tier 2 additions (only when running prompt v2)

Three more items, scored separately from tier 1 so the two signals stay apart.
Everything scriptable already lives in `verify.py --tier2`; these are the
judgement calls a script cannot make.

```
5. answer_first - the first sentence of the intro states the post's
   conclusion, not context or scene-setting. "Teams are increasingly
   exploring..." is a preamble and scores 0. "Three tools shipped isolation
   this week, and two of them do it in the same way" is a conclusion.
   2 = first sentence is the conclusion. 1 = conclusion by sentence three.
   0 = no conclusion in the intro.

6. source_separation - news claims are attributed to the search results and
   product claims to /input/product.md, with neither borrowing the other's
   authority. Attaching a feed link to a the product sentence scores 0.
   2 = cleanly separated. 1 = one blurred sentence. 0 = two or more.

7. limitation_real - the stated the product limitation is a real constraint
   from the fact sheet, not a humblebrag. "It does not resume a crashed run"
   scores 2. "It is so fast it can be hard to keep up" scores 0.
   2 = a real constraint, stated plainly. 1 = real but hedged into
   meaninglessness. 0 = absent, or a disguised boast.
```

## Tier 2 scoring

| Total (of 6) | Meaning |
|---|---|
| 6 | pass |
| 4-5 | partial |
| 0-3 | fail |

`source_separation = 0` is an automatic tier-2 **fail**. A product claim
wearing a news source's citation is the most damaging output this task can
produce, and it is invisible to a reader.

## Note on item 7

A script can check that *a* limitation sentence exists; only a judge can tell a
constraint from a boast. This is the clearest example of the division between
the two layers, and worth citing if anyone proposes moving the rubric into
code.
