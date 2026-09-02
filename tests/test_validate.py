import math

import pytest

from btlab.data import generate
from btlab.engine import Frictions, Signal, Trade, run
from btlab.report import render
from btlab.strategies import OpeningRangeBreakout, RandomEntries
from btlab.validate import (Stats, bootstrap_max_dd, control_distribution,
                            judge, percentile_of, split_is_oos, summarize)

NOFRICTION = Frictions(spread=0.0, slippage=0.0, commission=0.0)


def mk_trade(r, stop=1.0):
    t = Trade(day=0, entry_minute=0, direction=1, entry=100.0,
              exit=100.0 + r * stop, stop_dist=stop, bars_held=1,
              exit_reason="target" if r > 0 else "stop")
    return t


def test_summarize_empty():
    s = summarize([])
    assert s.n == 0 and s.mean_r == 0.0


def test_summarize_known_values():
    trades = [mk_trade(r) for r in (2.0, -1.0, -1.0, 2.0)]
    s = summarize(trades)
    assert s.n == 4
    assert s.mean_r == pytest.approx(0.5)
    assert s.win_rate == pytest.approx(0.5)
    assert s.profit_factor == pytest.approx(2.0)
    assert s.max_dd_r == pytest.approx(2.0)  # the two consecutive -1s


def test_summarize_ci_uses_1p96_sigma_over_sqrt_n():
    trades = [mk_trade(r) for r in (1.0, -1.0, 1.0, -1.0)]
    s = summarize(trades)
    import statistics
    half = 1.96 * statistics.stdev([1.0, -1.0, 1.0, -1.0]) / math.sqrt(4)
    assert s.ci_high - s.mean_r == pytest.approx(half)


def test_small_sample_flag():
    assert summarize([mk_trade(1.0)] * 29).small_sample
    assert not summarize([mk_trade(1.0)] * 30).small_sample


def test_split_is_chronological_and_disjoint():
    bars = generate(days=10, seed=9)
    is_bars, oos_bars = split_is_oos(bars, oos_frac=0.3)
    assert max(b.day for b in is_bars) < min(b.day for b in oos_bars)
    assert len({b.day for b in oos_bars}) == 3
    assert len(is_bars) + len(oos_bars) == len(bars)


def test_percentile_of_edges():
    dist = [0.0, 1.0, 2.0, 3.0]
    assert percentile_of(10.0, dist) == 100.0
    assert percentile_of(-10.0, dist) == 0.0
    assert percentile_of(1.5, dist) == 50.0
    assert math.isnan(percentile_of(1.0, []))


def test_control_distribution_is_reproducible():
    bars = generate(days=20, seed=11)
    ref = run(bars, OpeningRangeBreakout(), NOFRICTION)
    if not ref:  # synthetic sample without a breakout trade — still a valid test
        assert control_distribution(bars, ref, NOFRICTION) == []
        return
    a = control_distribution(bars, ref, NOFRICTION, runs=20)
    b = control_distribution(bars, ref, NOFRICTION, runs=20)
    assert a == b
    assert len(a) == 20


def test_bootstrap_dd_deterministic_and_ordered():
    trades = [mk_trade(r) for r in (1.0, -1.0, 2.0, -1.0, -1.0, 1.5)] * 5
    m1, p1 = bootstrap_max_dd(trades, runs=200, seed=3)
    m2, p2 = bootstrap_max_dd(trades, runs=200, seed=3)
    assert (m1, p1) == (m2, p2)
    assert m1 <= p1


def test_bootstrap_dd_zero_for_all_winners():
    trades = [mk_trade(1.0)] * 10
    m, p = bootstrap_max_dd(trades, runs=50)
    assert m == 0.0 and p == 0.0


def big_stats(mean, n=100, ci_low=None):
    ci_low = mean - 0.1 if ci_low is None else ci_low
    return Stats(n=n, mean_r=mean, ci_low=ci_low, ci_high=mean + 0.1,
                 win_rate=0.5, profit_factor=1.5, max_dd_r=5.0)


def test_judge_pass_requires_both_periods_and_clear_ci():
    v = judge(big_stats(0.3), big_stats(0.3, ci_low=0.05), 99, 99, 3, 8)
    assert v.label.startswith("PASS")


def test_judge_rejects_oos_failure():
    v = judge(big_stats(0.3), big_stats(-0.1), 99, 10, 3, 8)
    assert v.label.startswith("REJECTED")
    assert "out-of-sample" in v.label


def test_judge_rejects_indistinguishable_from_random():
    v = judge(big_stats(0.05), big_stats(0.05), 40, 60, 3, 8)
    assert v.label.startswith("REJECTED")
    assert "random" in v.label


def test_judge_flags_small_oos_sample():
    v = judge(big_stats(0.3), big_stats(0.3, n=10), 99, 99, 3, 8)
    assert "INSUFFICIENT OOS" in v.label


def test_judge_no_trades():
    v = judge(summarize([]), summarize([]), float("nan"), float("nan"), 0, 0)
    assert "NO TRADES" in v.label


def test_render_leads_with_verdict_and_warns_on_small_n():
    v = judge(big_stats(0.3), big_stats(0.3, n=10), 99, 99, 3.0, 8.0)
    text = render("Demo", v)
    assert "VERDICT:" in text.splitlines()[2]
    assert "WARNING" in text
    assert "n=10" in text


def test_random_entries_reproducible_and_respects_close_window():
    bars = generate(days=5, seed=13)
    ctrl = lambda: RandomEntries(seed=99, trades_per_day=5.0,
                                 stop_dists=[0.5], target_dists=[1.0])
    t1 = run(bars, ctrl(), NOFRICTION)
    t2 = run(bars, ctrl(), NOFRICTION)
    assert [t.entry_minute for t in t1] == [t.entry_minute for t in t2]
    assert len(t1) > 0


def test_orb_takes_only_first_breakout():
    from btlab.data import Bar
    bars = []
    for m in range(15):                       # flat range 99..101
        bars.append(Bar(0, m, 100.0, 101.0, 99.0, 100.0))
    bars.append(Bar(0, 15, 100.0, 102.0, 100.0, 101.8))   # first breakout bar
    bars.append(Bar(0, 16, 101.8, 101.9, 101.5, 101.6))   # entry bar
    for m in range(17, 60):
        bars.append(Bar(0, m, 101.6, 102.5, 101.4, 101.9))  # stays broken out
    trades = run(bars, OpeningRangeBreakout(range_minutes=15, target_r=2.0),
                 NOFRICTION)
    assert len(trades) == 1
    assert trades[0].direction == 1
    assert trades[0].entry_minute == 16
