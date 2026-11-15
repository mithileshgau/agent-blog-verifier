# Layer 3 - infrastructure metrics (Langfuse)

Owner: Infrastructure owner. Captured per run, 3 runs per framework, 5 frameworks = 15 runs.

**These do not pass or fail.** Layers 1 and 2 decide the verdict; this layer
explains the cost of reaching it. A framework that passes at 8x the tokens has
told us something the verdict alone cannot.

## Per run

| Metric | Unit | Source | Why |
|---|---|---|---|
| `tokens_in` / `tokens_out` | count | Langfuse | The headline cost driver |
| `cost_usd` | USD | Langfuse | Comparable across models |
| `wall_clock_s` | seconds | harness timer | What a human waits |
| `llm_calls` | count | Langfuse | Loop detection: 40 calls for a 700-word post is a finding |
| `tool_calls` | count | Langfuse | Split by tool |
| `retries` | count | Langfuse | Directly measures the planted 429 |
| `errors` | count + type | Langfuse | Crash vs handled |
| `peak_rss_mb` | MB | `resource.getrusage` in the runner | Per-run memory ceiling |
| `time_to_first_tool_call_s` | seconds | Langfuse | Planning overhead before work starts |
| `steps` | count | Langfuse | Against the step guardrail |
| `hit_budget_cap` | bool | runner | Did a guardrail stop it, or did it finish |

## Per framework, once

| Metric | Why |
|---|---|
| `setup_minutes` | the spec asks for "time to get running, what hurt". Wall-clock from empty directory to first successful smoke test |
| `deps_installed` | Count of direct dependencies added |
| `loc_to_working_agent` | Lines of code the owner wrote |
| `tracing_effort` | free / config / custom code - how hard Langfuse was to wire |

## Derived, for the sync

- `cost_per_passing_run` = total cost across 3 runs / number that passed.
  **A framework that passes once in three at double the tokens is four times
  the price of one that passes three times.** This number, not the pass rate,
  is what a reader of the final write-up will care about.
- `variance_tokens` = stdev of `tokens_in + tokens_out` across the 3 runs.
  High variance means unpredictable spend, which is an operational finding in
  its own right.
- `retry_recovered` = did the run complete after the planted 429.

## Two things to get right before Day 1

1. **Same model, same temperature, same max-tokens across all five
   frameworks.** If one owner leaves a default temperature at 0.7 and another
   at 0, the token and cost columns are not comparable and neither is anything
   else. Write the model config into the frozen spec.
2. **Record the Langfuse trace URL with every run.** the spec asks each owner
   to bring trace links; collecting them afterwards is how they go missing.

## Suggested shape

One row per run, 15 rows, in the Notion project doc:

```
framework | run | verdict | rubric_total | tokens_in | tokens_out | cost_usd |
wall_clock_s | llm_calls | tool_calls | retries | peak_rss_mb | failure_tags |
trace_url
```
