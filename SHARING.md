# How to share this

## The short answer: do not distribute it. Collect outputs instead.

The verifier only works if **every framework is scored by the identical file**.
Distributing copies means five people can end up on five slightly different
versions, and a single edited threshold silently voids the comparison.

**Recommended:** each owner submits their `/output` directory. One person runs
the verifier over all 15 and publishes the table.

```
submissions/
  langchain/run1/{blog.md,meta.json}
  langchain/run2/...
  langgraph/run1/...
  ...
```

That removes "did everyone run the same version" as a question, and it takes
one person about ten minutes.

## If you must distribute it

Ship **the whole directory**, never `verify.py` alone:

| File | Why it must travel with the script |
|---|---|
| `verify.py` | The checks |
| `prompt.md` | The verifier grades only what the prompt demanded. Without it the checks are arbitrary |
| `feed.json` | Checks compare against the feed. A different feed means different answers |
| `banned_words.txt` | Referenced by both the prompt and a check |
| `rubric.md` | The judge prompt, frozen |
| `VERIFIER.md` | What each tier measures and why |
| `metrics.md` | The trace fields to capture |

Then:

1. Put the directory in one git repo and tag it, for example `verifier-v1`
2. Everyone checks out that tag. **Nobody edits it.**
3. If something needs changing before Day 1, change it once, re-tag, and tell
   everyone. After the first run starts, nothing changes
4. Each owner records the tag they ran against alongside their results

## Checking everyone has the same copy

```bash
shasum -a 256 verify.py prompt.md feed.json banned_words.txt rubric.md
```

Compare the hashes at the start of Day 2. Mismatched hashes mean those runs
are not comparable, and it is better to know before the sync than during it.

## Running it

```bash
python3 verify.py --output ./output --feed feed.json --banned banned_words.txt --json
```

Exit code 0 pass, 1 partial, 2 fail. `--json` for machine-readable output to
paste into the results table.
