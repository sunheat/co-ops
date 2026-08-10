# Prompt Quality Mini-Benchmark Results

- Report: **COMPLETE** (live)
- Generated at: 2026-08-10T13:18:59.664363+00:00
- Requested provider / model: <code>azure</code>/<code>model-router</code>
- Actual models: <code>gpt-5.5-2026-04-24</code>=60; coverage 60/60
- Planned calls: 60; observed rows: 60; missing calls: 0
- Gradable ok: 60; provider errors: 0; truncated: 0
- Quality ratios use gradable `ok` rows; coverage shows gradable/planned.

| Prompt | Answer correct | Format | Evidence cited | Grounded | Stability | Input tokens | Output tokens | Total tokens | Latency ms | Cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| naive | 100% (20/20) [coverage 20/20] | 100% (20/20) [coverage 20/20] | 100% (20/20) [coverage 20/20] | 100% (20/20) [coverage 20/20] | 100% (10/10) | 303.2 [20/20] | 154.3 [20/20] | 457.5 [20/20] | 3932.0 [20/20] | n/a |
| structured | 100% (20/20) [coverage 20/20] | 100% (20/20) [coverage 20/20] | 100% (20/20) [coverage 20/20] | 100% (20/20) [coverage 20/20] | 100% (10/10) | 310.2 [20/20] | 161.1 [20/20] | 471.2 [20/20] | 3932.0 [20/20] | n/a |
| context_engineered | 100% (20/20) [coverage 20/20] | 100% (20/20) [coverage 20/20] | 100% (20/20) [coverage 20/20] | 100% (20/20) [coverage 20/20] | 100% (10/10) | 345.2 [20/20] | 151.1 [20/20] | 496.2 [20/20] | 3889.5 [20/20] | n/a |
