#!/usr/bin/env python3
"""v2: layer 2 (model-graded rubric) as code, so every owner grades the same way.

The judge prompt is read verbatim from rubric.md (the frozen block under "Judge prompt"),
so rubric.md stays the single source of truth. Per rubric.md:
  - run the judge 3 times per output and take the majority per criterion;
  - use a different model from the one under test. The judge is frozen to
    claude-sonnet-5-5 (the sprint agents run on claude-opus-5-5) and cannot be
    overridden, so every owner grades with the same judge;
  - total 8 = pass, 5-7 = partial, 0-4 = fail; no_invention = 0 is always a fail.

  python3 rubric.py --output ./output --feed feed.json [--json]

The judge also sees the task (prompt.md with banned_words.txt filled in) and the
frozen reference date, so restating the task's own rules is not read as invention.

Needs the `anthropic` package and ANTHROPIC_API_KEY (or an `ant auth login` profile).
"""
import argparse, json, os, re, statistics, sys
from collections import Counter

import anthropic
from pydantic import BaseModel, Field

HERE = os.path.dirname(os.path.abspath(__file__))
CRITERIA = ("grounded", "no_invention", "clarity", "attribution")
JUDGE_MODEL = "claude-sonnet-5-5"  # frozen with rubric.md
JUDGE_RUNS = 3
REFERENCE_TIME = "2026-11-16T00:00:00Z"  # frozen with prompt.md and feed.json


class Grade(BaseModel):
    grounded: int = Field(description="0, 1 or 2")
    no_invention: int = Field(description="0, 1 or 2")
    clarity: int = Field(description="0, 1 or 2")
    attribution: int = Field(description="0, 1 or 2")
    notes: str = Field(description="40 words or fewer")
    worst_quote: str = Field(description="verbatim sentence that cost the most marks, or ''")


def judge_prompt(path=os.path.join(HERE, "rubric.md")):
    text = open(path, encoding="utf8").read()
    section = text.split("## Judge prompt", 1)[1]
    return re.search(r"```\n(.*?)```", section, re.S).group(1).strip()


def task_text(reference_time=REFERENCE_TIME, prompt_path=os.path.join(HERE, "prompt.md"),
              banned_path=os.path.join(HERE, "banned_words.txt")):
    """The frozen task exactly as agents receive it, plus the run's date."""
    md = open(prompt_path, encoding="utf8").read()
    block = re.search(r"## Prompt.*?```\n(.*?)```", md, re.S).group(1).strip()
    words = [l.strip() for l in open(banned_path, encoding="utf8")
             if l.strip() and not l.startswith("#")]
    block = block.replace("[see banned_words.txt]", ", ".join(words))
    return f"Today's date for this run: {reference_time[:10]}\n\n{block}"


def judge_content(prompt, feed_text, post_text, task):
    return (f"{prompt}\n\n(A) FEED\n<feed>\n{feed_text}\n</feed>\n\n"
            f"(B) POST\n<post>\n{post_text}\n</post>\n\n"
            f"(C) TASK\n<task>\n{task}\n</task>")


def grade_once(client, model, prompt, feed_text, post_text, task=None):
    content = judge_content(prompt, feed_text, post_text, task or task_text())
    try:
        response = client.messages.parse(
            model=model, max_tokens=16000, output_format=Grade,
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.APIStatusError as e:
        return {"status": "error", "reason": f"API {e.status_code}: {e.message}"}
    except anthropic.APIConnectionError as e:
        return {"status": "error", "reason": f"connection: {e}"}
    if response.stop_reason == "refusal":
        return {"status": "error", "reason": "judge refused"}
    g = response.parsed_output
    if g is None:
        return {"status": "error", "reason": f"no parsed output ({response.stop_reason})"}
    scores = g.model_dump()
    if any(scores[c] not in (0, 1, 2) for c in CRITERIA):
        return {"status": "error", "reason": f"score out of range: {scores}"}
    return {"status": "ok", "model": response.model, **scores}


def majority(values):
    top, count = Counter(values).most_common(1)[0]
    return top if count * 2 > len(values) else int(statistics.median(values))


def grade(output_dir, feed_path, runs=JUDGE_RUNS, model=JUDGE_MODEL,
          reference_time=REFERENCE_TIME):
    post_path = os.path.join(output_dir, "blog.md")
    if not os.path.isfile(post_path):
        return {"verdict": "unscored", "reason": "blog.md missing", "grades": []}
    feed_text = open(feed_path, encoding="utf8").read()
    post_text = open(post_path, encoding="utf8", errors="ignore").read()
    client = anthropic.Anthropic()
    prompt = judge_prompt()
    task = task_text(reference_time)
    grades = [grade_once(client, model, prompt, feed_text, post_text, task)
              for _ in range(runs)]
    ok = [g for g in grades if g["status"] == "ok"]
    if len(ok) * 2 <= runs:
        return {"verdict": "unscored", "reason": "most grades failed", "grades": grades}
    scores = {c: majority([g[c] for g in ok]) for c in CRITERIA}
    total = sum(scores.values())
    verdict = ("fail" if scores["no_invention"] == 0 or total <= 4
               else "pass" if total == 8 else "partial")
    worst = [g["worst_quote"] for g in ok if g.get("worst_quote")]
    return {"verdict": verdict, "total": total, "scores": scores, "model": model,
            "runs": runs, "grades_ok": len(ok), "worst_quotes": worst, "grades": grades,
            "prompt_source": "rubric.md (Judge prompt block, verbatim)",
            "reference_time": reference_time}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="./output")
    ap.add_argument("--feed", default="feed.json")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--reference-time", default=REFERENCE_TIME,
                    help="the run's frozen date, as given to the agent and verify.py")
    a = ap.parse_args()
    result = grade(a.output, a.feed, reference_time=a.reference_time)
    if a.json:
        print(json.dumps(result, indent=1))
    else:
        print(f"RUBRIC: {result['verdict'].upper()}  total={result.get('total')}  "
              f"scores={result.get('scores')}  ({result.get('grades_ok')}/{JUDGE_RUNS} grades, judge {JUDGE_MODEL})")
        for q in result.get("worst_quotes", [])[:3]:
            print("  worst:", q[:140])
    sys.exit({"pass": 0, "partial": 1, "fail": 2}.get(result["verdict"], 3))
