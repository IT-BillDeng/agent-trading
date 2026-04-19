from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from engine.indicators import (
    atr,
    bollinger,
    ema,
    ema_slope,
    macd,
    rsi,
    volume_ratio,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _arithmetic_series(start: float, step: float, n: int) -> list[float]:
    return [start + step * i for i in range(n)]


# ── ema ──────────────────────────────────────────────────────────────────────

class TestEMA:
    def test_basic(self):
        prices = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        result = ema(prices, 5)
        assert result is not None
        # EMA-5 of 1..10 should be > SMA-5 (5.0) because later values are higher
        assert result > 5.0

    def test_insufficient_data(self):
        assert ema([1, 2, 3], 5) is None

    def test_period_zero(self):
        assert ema([1, 2, 3], 0) is None

    def test_negative_period(self):
        assert ema([1, 2, 3], -1) is None

    def test_exact_length(self):
        # Exactly period elements → returns SMA as EMA
        prices = [10.0, 20.0, 30.0]
        result = ema(prices, 3)
        assert result is not None
        assert math.isclose(result, 20.0)


class TestEMASlope:
    def test_positive_slope_on_uptrend(self):
        prices = _arithmetic_series(100.0, 1.0, 20)
        result = ema_slope(prices, 5, 3)
        assert result is not None
        assert result > 0

    def test_negative_slope_on_downtrend(self):
        prices = _arithmetic_series(120.0, -1.0, 20)
        result = ema_slope(prices, 5, 3)
        assert result is not None
        assert result < 0

    def test_insufficient_data(self):
        assert ema_slope([1, 2, 3, 4], 5, 2) is None


# ── rsi ──────────────────────────────────────────────────────────────────────

class TestRSI:
    def test_all_gains(self):
        prices = list(range(1, 20))  # strictly increasing
        result = rsi(prices, 5)
        assert result is not None
        assert result > 70  # strong uptrend → high RSI

    def test_all_losses(self):
        prices = list(range(20, 0, -1))  # strictly decreasing
        result = rsi(prices, 5)
        assert result is not None
        assert result < 30  # strong downtrend → low RSI

    def test_insufficient_data(self):
        assert rsi([1, 2, 3], 14) is None

    def test_period_zero(self):
        assert rsi(list(range(20)), 0) is None

    def test_flat_prices(self):
        prices = [50.0] * 30
        result = rsi(prices, 14)
        assert result is not None
        assert math.isclose(result, 100.0)  # no losses → RSI = 100


# ── bollinger ────────────────────────────────────────────────────────────────

class TestBollinger:
    def test_basic(self):
        prices = list(range(1, 26))  # 25 values
        upper, middle, lower = bollinger(prices, 20, 2)
        assert upper is not None
        assert middle is not None
        assert lower is not None
        assert upper > middle > lower
        # middle should be mean of last 20 values (6..25) = 15.5
        assert math.isclose(middle, 15.5)

    def test_insufficient_data(self):
        upper, middle, lower = bollinger([1, 2, 3], 20)
        assert (upper, middle, lower) == (None, None, None)

    def test_period_zero(self):
        upper, middle, lower = bollinger([1, 2, 3], 0)
        assert (upper, middle, lower) == (None, None, None)

    def test_std_dev_zero(self):
        prices = [10.0] * 20
        upper, middle, lower = bollinger(prices, 20, 0)
        assert upper is not None
        assert math.isclose(upper, middle)
        assert math.isclose(lower, middle)


# ── macd ─────────────────────────────────────────────────────────────────────

class TestMACD:
    def test_basic(self):
        # Need at least 26 values; use a simple rising series
        prices = list(range(1, 40))
        ml, sl, hist = macd(prices, prices, 9)
        assert ml is not None
        assert sl is not None
        assert hist is not None
        assert math.isclose(hist, ml - sl)

    def test_insufficient_data(self):
        prices = list(range(1, 20))
        ml, sl, hist = macd(prices, prices, 9)
        assert (ml, sl, hist) == (None, None, None)

    def test_mismatched_lengths(self):
        ml, sl, hist = macd([1, 2, 3], [1, 2])
        assert (ml, sl, hist) == (None, None, None)


# ── atr ──────────────────────────────────────────────────────────────────────

class TestATR:
    def test_basic(self):
        # 20 bars of simple data
        highs = [110, 112, 115, 113, 116, 118, 120, 119, 121, 123,
                 125, 124, 126, 128, 127, 130, 132, 131, 133, 135]
        lows = [100, 102, 105, 103, 106, 108, 110, 109, 111, 113,
                115, 114, 116, 118, 117, 120, 122, 121, 123, 125]
        closes = [105, 108, 110, 108, 112, 115, 118, 116, 118, 120,
                  122, 120, 123, 125, 124, 128, 130, 128, 131, 133]
        result = atr(highs, lows, closes, 14)
        assert result is not None
        assert result > 0

    def test_insufficient_data(self):
        assert atr([1, 2], [0, 1], [0.5, 1.5], 14) is None

    def test_period_zero(self):
        assert atr([1, 2], [0, 1], [0.5, 1.5], 0) is None


# ── volume_ratio ─────────────────────────────────────────────────────────────

class TestVolumeRatio:
    def test_basic(self):
        vols = [100] * 20 + [200]  # last bar 2× average
        result = volume_ratio(vols, 20)
        assert result is not None
        assert math.isclose(result, 2.0)

    def test_insufficient_data(self):
        assert volume_ratio([1, 2, 3], 20) is None

    def test_zero_average(self):
        vols = [0] * 20 + [100]
        assert volume_ratio(vols, 20) is None

    def test_period_zero(self):
        assert volume_ratio([1, 2, 3], 0) is None


class IndicatorUnittestBridge(unittest.TestCase):
    def test_ema_slope_positive_on_uptrend(self):
        prices = _arithmetic_series(100.0, 1.0, 20)
        result = ema_slope(prices, 5, 3)
        self.assertIsNotNone(result)
        self.assertGreater(result, 0)

    def test_rsi_bounds(self):
        result = rsi(list(range(1, 20)), 5)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result, 0)
        self.assertLessEqual(result, 100)


if __name__ == '__main__':
    unittest.main()
