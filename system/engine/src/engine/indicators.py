from __future__ import annotations

from typing import Iterable


def sma(values: Iterable[float], period: int) -> float | None:
    seq = list(values)
    if period <= 0 or len(seq) < period:
        return None
    window = seq[-period:]
    return sum(window) / period


def pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current / previous) - 1.0


def bar_range_pct(high: float, low: float, close: float) -> float | None:
    if close == 0:
        return None
    return (high - low) / close


# ---------------------------------------------------------------------------
# Trend / Momentum Indicators
# ---------------------------------------------------------------------------

def ema(values: Iterable[float], period: int) -> float | None:
    """Exponential Moving Average.

    Returns the latest EMA value, or None if insufficient data.
    """
    seq = list(values)
    if period <= 0 or len(seq) < period:
        return None
    multiplier = 2.0 / (period + 1)
    # Seed with SMA of first *period* values
    ema_val = sum(seq[:period]) / period
    for price in seq[period:]:
        ema_val = (price - ema_val) * multiplier + ema_val
    return ema_val


def ema_slope(
    values: Iterable[float],
    period: int,
    lookback: int = 3,
) -> float | None:
    """Normalized EMA slope over *lookback* bars.

    Returns (latest_ema / prior_ema) - 1.0, or None if insufficient data.
    """
    seq = list(values)
    if period <= 0 or lookback <= 0:
        return None
    if len(seq) < period + lookback:
        return None

    latest_ema = ema(seq, period)
    prior_ema = ema(seq[:-lookback], period)
    if latest_ema is None or prior_ema in (None, 0):
        return None
    return (latest_ema / prior_ema) - 1.0


def rsi(values: Iterable[float], period: int = 14) -> float | None:
    """Relative Strength Index (Wilder smoothing).

    Returns RSI value (0–100), or None if insufficient data.
    """
    seq = list(values)
    # Need period+1 prices to produce *period* changes
    if period <= 0 or len(seq) < period + 1:
        return None

    changes = [seq[i] - seq[i - 1] for i in range(1, len(seq))]

    gains = [c if c > 0 else 0.0 for c in changes]
    losses = [-c if c < 0 else 0.0 for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def bollinger(
    values: Iterable[float], period: int = 20, std_dev: int = 2
) -> tuple[float | None, float | None, float | None]:
    """Bollinger Bands.

    Returns (upper, middle, lower) or (None, None, None) if insufficient data.
    """
    seq = list(values)
    if period <= 0 or len(seq) < period:
        return (None, None, None)

    window = seq[-period:]
    middle = sum(window) / period
    variance = sum((x - middle) ** 2 for x in window) / period
    sd = variance ** 0.5
    upper = middle + std_dev * sd
    lower = middle - std_dev * sd
    return (upper, middle, lower)


def macd(
    fast_values: Iterable[float],
    slow_values: Iterable[float],
    signal_period: int = 9,
) -> tuple[float | None, float | None, float | None]:
    """MACD (Moving Average Convergence Divergence).

    Expects *fast_values* and *slow_values* to be **aligned price series**
    (typically the same close series).  EMA-12 and EMA-26 are computed
    internally; the MACD line is EMA12 − EMA26.

    Returns (macd_line, signal_line, histogram) or (None, None, None).
    """
    fast_seq = list(fast_values)
    slow_seq = list(slow_values)
    if len(fast_seq) != len(slow_seq) or len(fast_seq) < 26:
        return (None, None, None)

    ema12 = ema(fast_seq, 12)
    ema26 = ema(slow_seq, 26)
    if ema12 is None or ema26 is None:
        return (None, None, None)

    # Build MACD line series (we need enough history for signal EMA)
    # Recompute full EMA-12 and EMA-26 series
    multiplier_12 = 2.0 / 13
    multiplier_26 = 2.0 / 27

    ema12_val = sum(fast_seq[:12]) / 12
    ema26_val = sum(slow_seq[:26]) / 26

    macd_series: list[float] = []
    for i in range(12, len(fast_seq)):
        ema12_val = (fast_seq[i] - ema12_val) * multiplier_12 + ema12_val
        if i >= 25:  # 0-indexed, so index 25 = 26th element
            ema26_val = (slow_seq[i] - ema26_val) * multiplier_26 + ema26_val
            macd_series.append(ema12_val - ema26_val)

    if len(macd_series) < signal_period:
        return (None, None, None)

    signal = ema(macd_series, signal_period)
    if signal is None:
        return (None, None, None)

    macd_line = macd_series[-1]
    histogram = macd_line - signal
    return (macd_line, signal, histogram)


# ---------------------------------------------------------------------------
# Volatility / Volume Indicators
# ---------------------------------------------------------------------------

def atr(
    highs: Iterable[float],
    lows: Iterable[float],
    closes: Iterable[float],
    period: int = 14,
) -> float | None:
    """Average True Range.

    Returns the latest ATR value, or None if insufficient data.
    """
    h = list(highs)
    l = list(lows)
    c = list(closes)
    if period <= 0 or len(h) < period + 1 or len(l) < period + 1 or len(c) < period + 1:
        return None

    # True Range: max(high-low, |high-prev_close|, |low-prev_close|)
    tr_list: list[float] = []
    for i in range(1, len(c)):
        hl = h[i] - l[i]
        hc = abs(h[i] - c[i - 1])
        lc = abs(l[i] - c[i - 1])
        tr_list.append(max(hl, hc, lc))

    if len(tr_list) < period:
        return None

    atr_val = sum(tr_list[:period]) / period
    for tr in tr_list[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val


def volume_ratio(volumes: Iterable[float], period: int = 20) -> float | None:
    """Volume Ratio — current volume / average volume over *period* bars.

    Returns the ratio, or None if insufficient data or average is zero.
    """
    seq = list(volumes)
    if period <= 0 or len(seq) < period + 1:
        return None
    avg = sum(seq[-(period + 1):-1]) / period
    if avg == 0:
        return None
    return seq[-1] / avg
