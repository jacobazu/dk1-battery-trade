"""Stress tests for a day's battery plan: what the day earns if it goes wrong in a known way."""
import numpy as np
from risk import tail_stats

NEG_HOURS = slice(11, 15)  # 11:00 to 15:00
NEG_PRICE = -50.0          # euro/MWh


def stress_tests(f, q, S):
    """Revenue in euro under each stress, for forecast f, plan q and error scenarios S (rows of 24)."""
    f = np.asarray(f, dtype=float)
    planned = f @ q
    no_peak = f.copy()
    no_peak[q > 0] = np.median(f)  # the hours the battery sells in fall to the day's median price
    negative = f.copy()
    negative[NEG_HOURS] = NEG_PRICE
    return {
        "Worst of the last 250 days": planned + (S @ q).min(),
        "The peak doesn't come": no_peak @ q,
        "Negative prices 11–15": negative @ q,
        "Errors 3 times as big (worst 5%)": tail_stats(planned + 3 * (S @ q))["tail"],
    }
