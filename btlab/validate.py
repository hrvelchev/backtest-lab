"""The validation layer: where backtests go to be doubted.

A strategy result is never reported alone. It ships with:
- an in-sample / out-of-sample split (chronological, no shuffling),
- a random-entry control distribution matched on trade frequency, stop and
  target geometry, direction mix and hold time,
- a bootstrap of the trade sequence for drawdown expectations,
- sample sizes and a confidence interval on mean R, always.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass

from .data import Bar
from .engine import Frictions, Strategy, Trade, run
from .strategies import RandomEntries


@dataclass(frozen=True)
class Stats:
    n: int
    mean_r: float
    ci_low: float
    ci_high: float
    win_rate: float
    profit_factor: float
    max_dd_r: float

    @property
    def small_sample(self) -> bool:
        return self.n < 30


def summarize(trades: list[Trade]) -> Stats:
    if not trades:
        return Stats(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    rs = [t.r_multiple for t in trades]
    n = len(rs)
    mean = statistics.fmean(rs)
    sd = statistics.stdev(rs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    wins = sum(1 for r in rs if r > 0)
    gp = sum(r for r in rs if r > 0)
    gl = -sum(r for r in rs if r < 0)
    pf = gp / gl if gl > 0 else math.inf
    equity = peak = dd = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    return Stats(n=n, mean_r=mean, ci_low=mean - half, ci_high=mean + half,
                 win_rate=wins / n, profit_factor=pf, max_dd_r=dd)


def split_is_oos(bars: list[Bar], oos_frac: float = 0.3) -> tuple[list[Bar], list[Bar]]:
    """Chronological split: the OOS tail is never touched during development."""
    days = sorted({b.day for b in bars})
    cut = days[int(len(days) * (1 - oos_frac))]
    return [b for b in bars if b.day < cut], [b for b in bars if b.day >= cut]


def control_distribution(bars: list[Bar], reference: list[Trade],
                         frictions: Frictions, runs: int = 200,
                         base_seed: int = 1000) -> list[float]:
    """Mean R of `runs` random-entry controls matched to the reference trades."""
    if not reference:
        return []
    days = len({b.day for b in bars})
    per_day = len(reference) / max(days, 1)
    stops = [t.stop_dist for t in reference]
    targets = [abs(t.exit - t.entry) + t.stop_dist for t in reference]  # rough geometry proxy
    dirs = tuple(t.direction for t in reference)
    hold = max(int(statistics.median(t.bars_held for t in reference)) * 3, 10)
    out = []
    for k in range(runs):
        ctrl = RandomEntries(seed=base_seed + k, trades_per_day=per_day,
                             stop_dists=stops, target_dists=targets,
                             max_bars=hold, directions=dirs)
        out.append(summarize(run(bars, ctrl, frictions)).mean_r)
    return out


def percentile_of(value: float, dist: list[float]) -> float:
    if not dist:
        return float("nan")
    return 100.0 * sum(1 for d in dist if d < value) / len(dist)


def bootstrap_max_dd(trades: list[Trade], runs: int = 1000,
                     seed: int = 7) -> tuple[float, float]:
    """Median and 95th-percentile max drawdown (in R) from resampled trade order."""
    if not trades:
        return 0.0, 0.0
    rs = [t.r_multiple for t in trades]
    rng = random.Random(seed)
    dds = []
    for _ in range(runs):
        sample = [rs[rng.randrange(len(rs))] for _ in rs]
        equity = peak = dd = 0.0
        for r in sample:
            equity += r
            peak = max(peak, equity)
            dd = max(dd, peak - equity)
        dds.append(dd)
    dds.sort()
    return dds[len(dds) // 2], dds[int(len(dds) * 0.95)]


@dataclass(frozen=True)
class Verdict:
    is_stats: Stats
    oos_stats: Stats
    control_pctile_is: float
    control_pctile_oos: float
    dd_median: float
    dd_p95: float
    label: str


def judge(is_stats: Stats, oos_stats: Stats,
          pct_is: float, pct_oos: float,
          dd_median: float, dd_p95: float) -> Verdict:
    """Honest labels only. 'PASS' requires beating controls in BOTH periods
    with a CI clear of zero out-of-sample; everything weaker says so."""
    if is_stats.n == 0 or oos_stats.n == 0:
        label = "NO TRADES — untestable as configured"
    elif oos_stats.small_sample:
        label = "INSUFFICIENT OOS SAMPLE — suggestive at best, not conclusive"
    elif pct_is >= 95 and pct_oos >= 95 and oos_stats.ci_low > 0:
        label = "PASS — beats matched controls IS and OOS, OOS CI clear of zero"
    elif pct_is >= 95 and pct_oos < 50:
        label = "REJECTED — in-sample result did not survive out-of-sample"
    elif pct_is < 70:
        label = "REJECTED — indistinguishable from random entries in-sample"
    else:
        label = "INCONCLUSIVE — weak separation from controls; do not trade this"
    return Verdict(is_stats, oos_stats, pct_is, pct_oos, dd_median, dd_p95, label)
