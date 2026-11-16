# The frozen prompt

Ship this file with the verifier. **Neither means anything without the other** -
the verifier grades only what this prompt demands.

Freeze both at the same moment. If the prompt changes, every run taken before
the change is void.

---

## Prompt (paste verbatim into every framework)

```
Using the search tool, find the top 3 AI agent topics from the last 7 days by
score. A topic's score is its highest-scoring post. Use all search results.
Write a draft, check it against these rules, then fix it.

Final post: 600-800 words in markdown. Title, a short intro, then exactly one
## section per topic. No other sections.

Use only facts and links from the search results. Link each fact to its source
in the sentence where you use it.

Don't use these words: [see banned_words.txt].

Save blog.md and meta.json to /output only. meta.json has this shape:
{"topics": ["..."], "source_urls": ["..."]}
```

## Inputs, identical for every framework

| File | What it is |
|---|---|
| `feed.json` | The frozen feed, 30 posts over 3 search pages. Contains the planted traps |
| `banned_words.txt` | The word list referenced by the prompt |

Grade with `--reference-time 2026-11-16T00:00:00Z`. Fresh posts are dated
Nov 11-15 and stale ones Oct 28 - Nov 2, so the expected top 3 (agent memory,
tool calling, agent evals) is the same for any reference date from Nov 15 to
Nov 18, and the same whether a topic is scored by its best post or the sum of
its posts. Every post is fictional, on the reserved `.example` domain.

## Planted traps, which the feed must contain

| Trap | Correct behaviour |
|---|---|
| A post with a high score but older than 7 days | Skipped |
| Two posts on the same topic | Merged, counted once |
| A post with no URL | Not used as a source |
| Banned words present in feed titles | Not copied into the post |

In `feed.json`: the stale high scorers are ids 1, 14 and 23 (scores 99, 96, 98,
each with a banned word and a number found nowhere else); duplicate topics are
agent memory (2, 16, 28) and tool calling (5, 13, 26); the URL-less post is id 8,
the highest-scoring agent memory post, with its own number (72 hours); banned
words also appear in the title of id 27.

## Run rules

- One owner per framework
- Same model, same temperature, same max-tokens, same tool set, same budget
- Prompt frozen once the first run starts
- No human help during a run
- 3 runs per framework
- Every run traced

## Model settings, which must also be frozen

Write them down before Day 1. A framework whose owner left temperature at a
different default produces token and cost numbers that cannot be compared with
anyone else's, and the rest of the comparison goes with it.

```
model:        <exact model id>
temperature:  <value>
max_tokens:   <value>
tool timeout: <value>
```
