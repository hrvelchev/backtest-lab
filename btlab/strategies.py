"""Demo strategies. Deliberately textbook — the point of this repo is the
validation harness, not a tradeable edge. Both are the kind of construction
that LOOKS profitable on a drifting sample, which is what makes them good
demo material for the control-group comparison.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .data import SESSION_MINUTES, Bar
from .engine import Signal


@dataclass
class OpeningRangeBreakout:
    """Classic ORB: form a range over the first `range_minutes` of the day,
    go with the first breakout, stop at the opposite side of the range."""

    range_minutes: int = 15
    target_r: float = 2.0

    def on_bar(self, history: list[Bar]) -> Signal | None:
        bar = history[-1]
        if bar.minute < self.range_minutes:
            return None
        if bar.minute > SESSION_MINUTES - 30:   # no fresh entries near close
            return None
        day_start = len(history) - 1
        while day_start > 0 and history[day_start - 1].day == bar.day:
            day_start -= 1
        day_bars = history[day_start:]
        rng_bars = day_bars[: self.range_minutes]
        if len(rng_bars) < self.range_minutes:
            return None
        hi = max(b.high for b in rng_bars)
        lo = min(b.low for b in rng_bars)
        already = any(b.minute >= self.range_minutes and
                      (b.high > hi or b.low < lo)
                      for b in day_bars[self.range_minutes:-1])
        if already:
            return None                          # only the first breakout
        width = hi - lo
        if width <= 0:
            return None
        if bar.close > hi:
            return Signal(direction=1, stop_dist=width,
                          target_dist=width * self.target_r)
        if bar.close < lo:
            return Signal(direction=-1, stop_dist=width,
                          target_dist=width * self.target_r)
        return None


@dataclass
class MovingAverageCross:
    """Fast/slow close-price cross, long-only. The classic drift harvester."""

    fast: int = 10
    slow: int = 40
    stop_frac: float = 0.002    # stop distance as fraction of price
    target_r: float = 3.0

    def on_bar(self, history: list[Bar]) -> Signal | None:
        if len(history) < self.slow + 1:
            return None
        bar = history[-1]
        if bar.minute > SESSION_MINUTES - 30:
            return None
        closes = [b.close for b in history[-(self.slow + 1):]]
        fast_now = sum(closes[-self.fast:]) / self.fast
        slow_now = sum(closes[-self.slow:]) / self.slow
        fast_prev = sum(closes[-self.fast - 1:-1]) / self.fast
        slow_prev = sum(closes[-self.slow - 1:-1]) / self.slow
        if fast_prev <= slow_prev and fast_now > slow_now:
            stop = bar.close * self.stop_frac
            return Signal(direction=1, stop_dist=stop,
                          target_dist=stop * self.target_r, max_bars=120)
        return None


@dataclass
class RandomEntries:
    """Control strategy: entries at random bars, with stop/target/hold drawn
    to match a reference trade population. If your strategy cannot beat a
    few hundred of these, it has no entry edge — whatever its equity curve
    looks like. Seeded: every control run is reproducible.
    """

    seed: int
    trades_per_day: float
    stop_dists: list[float]
    target_dists: list[float]
    max_bars: int = 120
    directions: tuple[int, ...] = (1, -1)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        self._p = self.trades_per_day / SESSION_MINUTES

    def on_bar(self, history: list[Bar]) -> Signal | None:
        bar = history[-1]
        if bar.minute > SESSION_MINUTES - 30:
            return None
        if self._rng.random() >= self._p:
            return None
        k = self._rng.randrange(len(self.stop_dists))
        return Signal(direction=self._rng.choice(self.directions),
                      stop_dist=self.stop_dists[k],
                      target_dist=self.target_dists[k],
                      max_bars=self.max_bars)
