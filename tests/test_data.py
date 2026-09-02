import csv

from btlab.data import SESSION_MINUTES, Bar, generate, load_csv


def test_generate_is_deterministic():
    assert generate(days=5, seed=1) == generate(days=5, seed=1)


def test_generate_seed_changes_output():
    assert generate(days=5, seed=1) != generate(days=5, seed=2)


def test_generate_bar_count():
    bars = generate(days=7, seed=3)
    assert len(bars) == 7 * SESSION_MINUTES


def test_generate_ohlc_sanity():
    for b in generate(days=3, seed=4):
        assert b.high >= max(b.open, b.close)
        assert b.low <= min(b.open, b.close)
        assert b.low > 0


def test_generate_day_minute_structure():
    bars = generate(days=4, seed=5)
    assert sorted({b.day for b in bars}) == [0, 1, 2, 3]
    for d in range(4):
        minutes = [b.minute for b in bars if b.day == d]
        assert minutes == list(range(SESSION_MINUTES))


def test_load_csv_round_trip(tmp_path):
    bars = generate(days=1, seed=6)[:10]
    path = tmp_path / "bars.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["day", "minute", "open", "high", "low", "close"])
        for b in bars:
            w.writerow([b.day, b.minute, b.open, b.high, b.low, b.close])
    assert load_csv(str(path)) == bars
