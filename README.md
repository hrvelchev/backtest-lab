# backtest-lab

A small, dependency-free intraday backtest engine built around one conviction:
**most backtests lie, and the harness itself should make the common lies
impossible.** The interesting code here is not the strategies — they are
deliberately textbook — it is the engine that refuses to flatter them and the
validation layer that assumes every result is noise until proven otherwise.

Standard library only. Runs anywhere Python 3.10+ runs.

```bash
python run_demo.py        # synthetic data -> two strategies -> honest verdicts
python -m pytest          # 37 tests, fully offline, ~0.3s
```

## Why this exists

I build and run live trading systems, and the expensive lessons were never
about strategy ideas — they were about backtests that looked brilliant and
were wrong. This repo distills the guardrails I now apply to every study,
stripped down to a form small enough to read in one sitting. (The production
engines these guardrails protect — order-flow features on 1-minute footprint
data, tick-exact simulation over 19M+ ticks, options gamma-exposure analytics,
prop-firm constraint sweeps — are private, for data-licensing and IP reasons.
This is the methodology, not those systems.)

Three real mistakes shaped the design:

- **The intrabar mirage.** A grid strategy once backtested to +350%. On real
  tick data it was −96%. The backtest had filled an add at a bar's low and a
  take-profit at the same bar's high — as if it knew the path inside the bar.
  OHLC bars do not contain the path. → *Rule 2 below.*
- **The barrier illusion.** A no-stop strategy with a tiny target posts a 98%
  win rate at literally zero edge — the wins are just frequent and the losses
  rare and huge. A high win rate is not evidence of anything. → *the report
  leads with mean R and profit factor, never win rate.*
- **Drift is not edge.** A long-only strategy tested over a rising sample looks
  great and has learned nothing but "the market went up." → *Rule: every
  result is compared against random entries matched on the same geometry, and
  split in-sample / out-of-sample chronologically.*

## The three engine rules (enforced structurally)

1. **No lookahead.** A strategy's `on_bar(history)` only ever receives bars up
   to and including the current one. Signals fill at the **next** bar's open,
   never at the close of the bar that produced them.
2. **Pessimistic intrabar resolution.** If one bar touches both stop and
   target, the stop is assumed first. If price gaps beyond the stop, the fill
   is the worse open price, not the stop. When a bar's path is ambiguous, the
   engine rules **against** the strategy.
3. **Frictions always on.** Spread, slippage and commission apply to every
   trade. You can set them to zero, but you have to do it on purpose.

These are not comments asking the author to be careful — they are properties
the test suite pins down (`tests/test_engine.py`): gap-through-stop fills at
the open, both-levels-touched resolves to the stop, entry lands at the next
open, frictions strictly worsen the result.

## The validation layer

A result is never reported alone. `btlab/validate.py` ships every strategy with:

- a **chronological IS/OOS split** (the out-of-sample tail is never touched
  during development),
- a **random-entry control distribution** matched on trade frequency, stop and
  target geometry, direction mix and hold time — if a strategy can't beat a few
  hundred of these, it has no entry edge whatever its equity curve says,
- a **bootstrap** of the trade sequence for realistic drawdown expectations,
- **sample size and a 95% confidence interval on mean R, always**, with an
  explicit small-sample (n < 30) warning.

The verdict labels are deliberately hard to game: `PASS` requires beating
controls in *both* periods with an out-of-sample CI clear of zero. Everything
weaker says exactly how it is weaker — `REJECTED`, `INCONCLUSIVE`, or
`INSUFFICIENT OOS SAMPLE`.

## What the demo prints

Both demo strategies are honest failures on the synthetic data, which is the
point — the harness is designed to catch this, not hide it:

```
=== Opening Range Breakout (15m, 2R) ===
VERDICT: REJECTED — indistinguishable from random entries in-sample
In-sample: n=147  mean R=-0.076  95% CI [-0.288, +0.135]
  win rate 35.4%   profit factor 0.88   max DD 24.2R
  vs matched random-entry controls: 34th percentile
...
```

35th-percentile against random entries means the "strategy" did *worse* than
throwing darts. A win rate near 40% with a negative mean R is the barrier
illusion in miniature. The report says REJECTED on the first line.

## Layout

| File | What |
|---|---|
| `btlab/data.py` | seeded synthetic minute-bar generator + CSV loader |
| `btlab/engine.py` | the bar-walk engine and the three rules |
| `btlab/strategies.py` | ORB, MA-cross, and the random-entry control |
| `btlab/validate.py` | IS/OOS split, control distribution, bootstrap, verdicts |
| `btlab/report.py` | plain-text report; caveats are not optional |
| `run_demo.py` | end-to-end example |
| `tests/` | 37 offline tests |

## Bring your own data

Implement `on_bar(history) -> Signal | None`, or load real bars with
`btlab.data.load_csv` (columns `day,minute,open,high,low,close`). The engine
and validation layer do not care where the bars came from.

## License

MIT — see [LICENSE](LICENSE).
