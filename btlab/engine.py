"""Event-driven bar-walk engine with the dishonesty removed.

Three rules, enforced structurally rather than by discipline:

1. NO LOOKAHEAD. A strategy's ``on_bar(history)`` receives only bars up to
   and including the current one. Signals fill at the NEXT bar's open —
   never at the close of the bar that produced them.

2. PESSIMISTIC INTRABAR RESOLUTION. If a bar touches both stop and target,
   the stop is assumed to have filled first. If price gaps beyond the stop,
   the fill is the (worse) open, not the stop price. OHLC bars do not
   contain the path; when the path is ambiguous, the engine rules against
   the strategy.

3. FRICTION ALWAYS ON. Spread, slippage and commission are applied to every
   trade; they can be set to zero explicitly, but the default is not zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .data import Bar


@dataclass(frozen=True)
class Signal:
    direction: int          # +1 long, -1 short
    stop_dist: float        # distance from entry to stop, price units, > 0
    target_dist: float      # distance from entry to target, price units, > 0
    max_bars: int = 10_000  # time exit if neither level is hit


class Strategy(Protocol):
    def on_bar(self, history: list[Bar]) -> Signal | None: ...


@dataclass(frozen=True)
class Frictions:
    spread: float = 0.02      # price units, paid once per round trip
    slippage: float = 0.01    # price units per side, adverse
    commission: float = 0.0   # price units per round trip equivalent


@dataclass
class Trade:
    day: int
    entry_minute: int
    direction: int
    entry: float
    exit: float
    stop_dist: float
    bars_held: int
    exit_reason: str          # "stop" | "target" | "time" | "eod"
    r_multiple: float = field(init=False)

    def __post_init__(self) -> None:
        gross = (self.exit - self.entry) * self.direction
        self.r_multiple = gross / self.stop_dist if self.stop_dist > 0 else 0.0


def _resolve_exit(bar: Bar, direction: int, stop: float, target: float) -> tuple[float, str] | None:
    """Pessimistic single-bar resolution: gap check first, then stop before target."""
    if direction > 0:
        if bar.open <= stop:
            return bar.open, "stop"
        if bar.low <= stop:
            return stop, "stop"
        if bar.high >= target:
            return target, "target"
    else:
        if bar.open >= stop:
            return bar.open, "stop"
        if bar.high >= stop:
            return stop, "stop"
        if bar.low <= target:
            return target, "target"
    return None


def run(bars: list[Bar], strategy: Strategy,
        frictions: Frictions = Frictions()) -> list[Trade]:
    """Walk bars once; at most one open position at a time.

    ``history`` is one growing list appended to in place (O(1) per bar, not
    an O(n) copy) and always ends at the current bar. Strategies must treat
    it as read-only.
    """
    trades: list[Trade] = []
    half_spread = frictions.spread / 2
    cost_r_adjust = frictions.commission  # applied as exit price penalty

    history: list[Bar] = []
    i = 0
    n = len(bars)
    while i < n - 1:
        history.append(bars[i])
        sig = strategy.on_bar(history)
        if sig is None:
            i += 1
            continue

        entry_bar = bars[i + 1]
        if entry_bar.day != bars[i].day:
            i += 1                      # signal at the last bar of a day dies
            continue

        d = sig.direction
        entry = entry_bar.open + d * (half_spread + frictions.slippage)
        stop = entry - d * sig.stop_dist
        target = entry + d * sig.target_dist

        exit_price: float | None = None
        reason = "time"
        j = i + 1
        while j < n and bars[j].day == entry_bar.day:
            hit = _resolve_exit(bars[j], d, stop, target)
            if hit is not None:
                exit_price, reason = hit
                break
            if j - i >= sig.max_bars:
                exit_price, reason = bars[j].close, "time"
                break
            j += 1
        if exit_price is None:          # session ended with position open
            j = min(j - 1, n - 1)
            exit_price, reason = bars[j].close, "eod"

        exit_price -= d * (half_spread + frictions.slippage + cost_r_adjust)
        trades.append(Trade(day=entry_bar.day, entry_minute=entry_bar.minute,
                            direction=d, entry=entry, exit=exit_price,
                            stop_dist=sig.stop_dist, bars_held=j - i,
                            exit_reason=reason))
        history.extend(bars[i + 1: j + 1])  # bars consumed by the open trade
        i = j + 1                       # no overlapping positions
    return trades
