"""End-to-end demo: synthetic data -> strategy vs matched controls, IS/OOS.

    python run_demo.py

Runs the textbook ORB and the MA-cross drift harvester through the full
validation pipeline and prints both reports. Expect honesty, not glory:
on drifting synthetic data these usually read REJECTED or INCONCLUSIVE —
which is the point of the harness.
"""

from __future__ import annotations

from btlab.data import generate
from btlab.engine import Frictions, run
from btlab.report import render
from btlab.strategies import MovingAverageCross, OpeningRangeBreakout
from btlab.validate import (bootstrap_max_dd, control_distribution, judge,
                            percentile_of, split_is_oos, summarize)


def evaluate(name: str, strategy, bars, frictions: Frictions) -> str:
    is_bars, oos_bars = split_is_oos(bars, oos_frac=0.3)
    is_trades = run(is_bars, strategy, frictions)
    oos_trades = run(oos_bars, strategy, frictions)
    is_stats, oos_stats = summarize(is_trades), summarize(oos_trades)
    pct_is = percentile_of(is_stats.mean_r,
                           control_distribution(is_bars, is_trades, frictions))
    pct_oos = percentile_of(oos_stats.mean_r,
                            control_distribution(oos_bars, oos_trades, frictions,
                                                 base_seed=5000))
    dd_med, dd_p95 = bootstrap_max_dd(is_trades + oos_trades)
    return render(name, judge(is_stats, oos_stats, pct_is, pct_oos, dd_med, dd_p95))


def main() -> None:
    bars = generate(days=250, seed=42)
    frictions = Frictions(spread=0.02, slippage=0.01, commission=0.005)
    print(evaluate("Opening Range Breakout (15m, 2R)",
                   OpeningRangeBreakout(), bars, frictions))
    print()
    print(evaluate("MA Cross 10/40 long-only",
                   MovingAverageCross(), bars, frictions))


if __name__ == "__main__":
    main()
