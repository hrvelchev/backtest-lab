"""Plain-text report writer. Every number ships with its n; every claim
ships with its caveat. If the result is weak the report says so in the
first line, not in a footnote.
"""

from __future__ import annotations

from .validate import Stats, Verdict


def _fmt_stats(name: str, s: Stats) -> list[str]:
    if s.n == 0:
        return [f"{name}: no trades"]
    lines = [
        f"{name}: n={s.n}  mean R={s.mean_r:+.3f}  "
        f"95% CI [{s.ci_low:+.3f}, {s.ci_high:+.3f}]",
        f"  win rate {s.win_rate:.1%}   profit factor {s.profit_factor:.2f}   "
        f"max DD {s.max_dd_r:.1f}R",
    ]
    if s.small_sample:
        lines.append(f"  WARNING: n={s.n} < 30 — treat every number above as noise-dominated")
    return lines


def render(title: str, v: Verdict) -> str:
    out = [
        f"=== {title} ===",
        "",
        f"VERDICT: {v.label}",
        "",
        *_fmt_stats("In-sample", v.is_stats),
        f"  vs matched random-entry controls: {v.control_pctile_is:.0f}th percentile",
        "",
        *_fmt_stats("Out-of-sample", v.oos_stats),
        f"  vs matched random-entry controls: {v.control_pctile_oos:.0f}th percentile",
        "",
        f"Bootstrap drawdown expectation: median {v.dd_median:.1f}R, "
        f"95th percentile {v.dd_p95:.1f}R",
        "",
        "Caveats that apply to every run: OHLC bars cannot resolve intrabar",
        "path — ambiguous bars are settled AGAINST the strategy; frictions are",
        "modeled, not measured; a passing verdict on synthetic data proves the",
        "harness works, not that the strategy earns money.",
    ]
    return "\n".join(out)
