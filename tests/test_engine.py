import math

import pytest

from btlab.data import Bar
from btlab.engine import Frictions, Signal, run

NOFRICTION = Frictions(spread=0.0, slippage=0.0, commission=0.0)


def mk_bar(day, minute, o, h, l, c):
    return Bar(day=day, minute=minute, open=o, high=h, low=l, close=c)


def flat_day(day, minutes, price=100.0):
    return [mk_bar(day, m, price, price, price, price) for m in range(minutes)]


class SignalAt:
    """Signal exactly once, at a given (day, minute)."""

    def __init__(self, day, minute, signal):
        self.day, self.minute, self.signal = day, minute, signal
        self.calls = []

    def on_bar(self, history):
        self.calls.append(len(history))
        bar = history[-1]
        if bar.day == self.day and bar.minute == self.minute:
            return self.signal
        return None


def test_history_only_grows_and_ends_at_current_bar():
    bars = flat_day(0, 50)
    seen = []

    class Recorder:
        def on_bar(self, history):
            seen.append((len(history), history[-1].minute))
            return None

    run(bars, Recorder(), NOFRICTION)
    lengths = [n for n, _ in seen]
    assert lengths == sorted(lengths)
    for n, minute in seen:
        assert minute == n - 1  # last bar of the slice IS the current bar


def test_entry_fills_at_next_bar_open():
    bars = flat_day(0, 10, price=100.0)
    bars[5] = mk_bar(0, 5, 101.5, 101.5, 101.5, 101.5)  # next bar after signal
    strat = SignalAt(0, 4, Signal(direction=1, stop_dist=1.0, target_dist=100.0))
    trades = run(bars, strat, NOFRICTION)
    assert len(trades) == 1
    assert trades[0].entry == pytest.approx(101.5)
    assert trades[0].entry_minute == 5


def test_signal_on_last_bar_of_day_is_dropped():
    bars = flat_day(0, 10) + flat_day(1, 10)
    strat = SignalAt(0, 9, Signal(direction=1, stop_dist=1.0, target_dist=1.0))
    assert run(bars, strat, NOFRICTION) == []


def test_stop_wins_when_bar_touches_both_levels_long():
    bars = flat_day(0, 3, 100.0)
    bars.append(mk_bar(0, 3, 100.0, 103.0, 97.0, 100.0))  # touches both
    bars.append(mk_bar(0, 4, 100.0, 100.0, 100.0, 100.0))
    strat = SignalAt(0, 2, Signal(direction=1, stop_dist=1.0, target_dist=1.0))
    trades = run(bars, strat, NOFRICTION)
    assert trades[0].exit_reason == "stop"
    assert trades[0].r_multiple == pytest.approx(-1.0)


def test_stop_wins_when_bar_touches_both_levels_short():
    bars = flat_day(0, 3, 100.0)
    bars.append(mk_bar(0, 3, 100.0, 103.0, 97.0, 100.0))
    bars.append(mk_bar(0, 4, 100.0, 100.0, 100.0, 100.0))
    strat = SignalAt(0, 2, Signal(direction=-1, stop_dist=1.0, target_dist=1.0))
    trades = run(bars, strat, NOFRICTION)
    assert trades[0].exit_reason == "stop"
    assert trades[0].r_multiple == pytest.approx(-1.0)


def test_gap_through_stop_fills_at_open_not_stop_long():
    bars = flat_day(0, 3, 100.0)
    bars.append(mk_bar(0, 3, 100.0, 100.0, 100.0, 100.0))  # entry bar
    bars.append(mk_bar(0, 4, 95.0, 95.0, 95.0, 95.0))      # gap far below stop
    strat = SignalAt(0, 2, Signal(direction=1, stop_dist=1.0, target_dist=5.0))
    trades = run(bars, strat, NOFRICTION)
    assert trades[0].exit == pytest.approx(95.0)            # worse than stop 99.0
    assert trades[0].r_multiple == pytest.approx(-5.0)


def test_gap_through_stop_fills_at_open_not_stop_short():
    bars = flat_day(0, 3, 100.0)
    bars.append(mk_bar(0, 3, 100.0, 100.0, 100.0, 100.0))
    bars.append(mk_bar(0, 4, 105.0, 105.0, 105.0, 105.0))
    strat = SignalAt(0, 2, Signal(direction=-1, stop_dist=1.0, target_dist=5.0))
    trades = run(bars, strat, NOFRICTION)
    assert trades[0].exit == pytest.approx(105.0)
    assert trades[0].r_multiple == pytest.approx(-5.0)


def test_clean_target_exit():
    bars = flat_day(0, 3, 100.0)
    bars.append(mk_bar(0, 3, 100.0, 100.0, 100.0, 100.0))
    bars.append(mk_bar(0, 4, 100.0, 102.5, 100.0, 102.0))
    strat = SignalAt(0, 2, Signal(direction=1, stop_dist=1.0, target_dist=2.0))
    trades = run(bars, strat, NOFRICTION)
    assert trades[0].exit_reason == "target"
    assert trades[0].r_multiple == pytest.approx(2.0)


def test_time_exit_after_max_bars():
    bars = flat_day(0, 60, 100.0)
    strat = SignalAt(0, 2, Signal(direction=1, stop_dist=1.0,
                                  target_dist=50.0, max_bars=5))
    trades = run(bars, strat, NOFRICTION)
    assert trades[0].exit_reason == "time"
    assert trades[0].bars_held <= 6


def test_eod_exit_when_session_ends():
    bars = flat_day(0, 10, 100.0) + flat_day(1, 10, 100.0)
    strat = SignalAt(0, 5, Signal(direction=1, stop_dist=1.0, target_dist=50.0))
    trades = run(bars, strat, NOFRICTION)
    assert len(trades) == 1
    assert trades[0].exit_reason == "eod"
    assert trades[0].day == 0


def test_frictions_make_long_entry_worse():
    bars = flat_day(0, 10, 100.0)
    fr = Frictions(spread=0.10, slippage=0.05, commission=0.0)
    strat = SignalAt(0, 4, Signal(direction=1, stop_dist=1.0, target_dist=100.0))
    trades = run(bars, strat, fr)
    assert trades[0].entry == pytest.approx(100.0 + 0.05 + 0.05)


def test_frictions_drag_shows_in_r_multiple():
    bars = flat_day(0, 3, 100.0)
    bars.append(mk_bar(0, 3, 100.0, 100.0, 100.0, 100.0))
    bars.append(mk_bar(0, 4, 100.0, 103.0, 100.0, 102.0))
    fr = Frictions(spread=0.02, slippage=0.01, commission=0.005)
    strat = SignalAt(0, 2, Signal(direction=1, stop_dist=1.0, target_dist=2.0))
    trades = run(bars, strat, fr)
    assert trades[0].r_multiple < 2.0  # strictly worse than frictionless 2R


def test_no_overlapping_positions():
    bars = flat_day(0, 200, 100.0)

    class Always:
        def on_bar(self, history):
            return Signal(direction=1, stop_dist=1.0, target_dist=1.0, max_bars=10)

    trades = run(bars, Always(), NOFRICTION)
    assert len(trades) >= 2
    for a, b in zip(trades, trades[1:]):
        assert b.entry_minute > a.entry_minute + a.bars_held - 1


def test_stop_loss_is_minus_one_r():
    bars = flat_day(0, 3, 100.0)
    bars.append(mk_bar(0, 3, 100.0, 100.0, 100.0, 100.0))
    bars.append(mk_bar(0, 4, 100.0, 100.0, 98.9, 99.0))
    strat = SignalAt(0, 2, Signal(direction=1, stop_dist=1.0, target_dist=5.0))
    trades = run(bars, strat, NOFRICTION)
    assert trades[0].exit_reason == "stop"
    assert trades[0].r_multiple == pytest.approx(-1.0)
