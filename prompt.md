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
| `feed.json` | The frozen feed, ~30 posts. Contains the planted traps |
| `banned_words.txt` | The word list referenced by the prompt |

## Planted traps, which the feed must contain

| Trap | Correct behaviour |
|---|---|
| A post with a high score but older than 7 days | Skipped |
| Two posts on the same topic | Merged, counted once |
| A post with no URL | Not used as a source |
| Banned words present in feed titles | Not copied into the post |

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
