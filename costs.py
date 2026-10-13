"""Costs in euro per MWh, sources in the README."""
import numpy as np

DKK_PER_EUR = 7.46  # the krone is pegged to the euro

FEE = 0.055                                     # nord pool day-ahead fee 2026, per MWh bought or sold
TARIFF_BUY = (7.2 + 4.3) * 10 / DKK_PER_EUR     # energinet 2026, tariffs on charging (ore/kWh to euro/MWh)
TARIFF_SELL = (0.50 + 0.53) * 10 / DKK_PER_EUR  # energinet 2026, tariffs on discharging
WEAR = 20.0                                     # assumed battery wear per MWh sold


def costs(wear=WEAR, tariffs=False):
    """Cost per MWh bought and per MWh sold."""
    return {"buy": FEE + (TARIFF_BUY if tariffs else 0.0),
            "sell": FEE + wear + (TARIFF_SELL if tariffs else 0.0)}


def cost_of(q, c):
    """Cost of a plan (net sale per hour in MWh, + = sell) in euro."""
    q = np.asarray(q, dtype=float)
    return c["buy"] * -q[q < 0].sum() + c["sell"] * q[q > 0].sum()
