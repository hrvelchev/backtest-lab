"""Minute-bar data: a seeded synthetic generator and a CSV loader.

The generator exists so the repo is runnable with zero external data (and no
exchange-data redistribution questions). It is not a market model — it just
produces bars with the features that break naive backtests: intraday
U-shaped volatility, drift regimes, and gaps between sessions.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Bar:
    day: int          # session index, 0-based
    minute: int       # minute within session, 0-based
    open: float
    high: float
    low: float
    close: float


SESSION_MINUTES = 390  # 6.5h cash-session-like day


def _minute_vol_factor(minute: int) -> float:
    """U-shaped intraday volatility: busy open, quiet lunch, busy close."""
    x = minute / (SESSION_MINUTES - 1)
    return 0.6 + 1.2 * ((2 * x - 1) ** 2)


def generate(days: int, seed: int, start_price: float = 100.0,
             base_vol: float = 0.0006) -> list[Bar]:
    """Deterministic synthetic minute bars, calibrated to stay realistic.

    Per-minute log returns are ~N(daily_drift/390, minute_vol); daily
    volatility lands near 1-2% and price wanders but does not run away.

    Drift regimes: the generator alternates multi-week up/flat/down drift
    segments, each a few tenths of a percent per day. This is deliberate —
    a naive long-only test during an up segment posts a positive equity
    curve, which is exactly the illusion the validation layer exists to
    puncture (see README: "drift is not edge"). The drift is intentionally
    small enough that it never survives the random-entry control.
    """
    rng = random.Random(seed)
    bars: list[Bar] = []
    price = start_price
    day = 0
    while day < days:
        regime_len = rng.randint(15, 40)
        drift_daily = rng.choice([-1.0, 0.0, 0.0, 1.0]) * 0.0015  # <=0.15%/day
        drift_min = drift_daily / SESSION_MINUTES
        for _ in range(regime_len):
            if day >= days:
                break
            price *= math.exp(rng.gauss(0, base_vol * 2))  # small overnight gap
            for minute in range(SESSION_MINUTES):
                vol = base_vol * _minute_vol_factor(minute)
                o = price
                r1, r2, r3 = (rng.gauss(drift_min, vol) for _ in range(3))
                path = [o, o * math.exp(r1), o * math.exp(r1 + r2),
                        o * math.exp(r1 + r2 + r3)]
                bar = Bar(day=day, minute=minute, open=o,
                          high=max(path), low=min(path), close=path[-1])
                bars.append(bar)
                price = bar.close
            day += 1
    return bars


def load_csv(path: str) -> list[Bar]:
    """Load bars from CSV with columns: day,minute,open,high,low,close."""
    out: list[Bar] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out.append(Bar(day=int(row["day"]), minute=int(row["minute"]),
                           open=float(row["open"]), high=float(row["high"]),
                           low=float(row["low"]), close=float(row["close"])))
    return out
