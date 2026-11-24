import sys

import numpy as np

sys.path.insert(0, "solar")
from solar import day_out, plan  # noqa: E402

PRICE = np.r_[np.full(8, 50.0), np.full(8, 20.0), np.full(8, 120.0)]
FC = np.r_[np.zeros(8), np.full(8, 0.6), np.zeros(8)]


def test_buffer_kept_and_grid_respected():
    up, dn = np.full(24, 0.2) * (FC > 0), np.full(24, 0.2) * (FC > 0)
    p = plan(PRICE, FC, np.minimum(up, 1 - FC), np.minimum(dn, FC))
    assert np.allclose(p["bu"], np.minimum(up, 1 - FC), atol=1e-6)
    assert np.allclose(p["bd"], np.minimum(dn, FC), atol=1e-6)
    assert (p["sol"] + p["dis"] - p["ch"] <= 1 + 1e-6).all()
    assert (p["sol"] <= FC + 1e-6).all()


def test_shortfall_inside_buffer_is_covered():
    up, dn = np.full(24, 0.2) * (FC > 0), np.full(24, 0.2) * (FC > 0)
    p = plan(PRICE, FC, np.minimum(up, 1 - FC), np.minimum(dn, FC))
    act = FC - 0.1 * (FC > 0)          # a little less sun than sold
    out = day_out(p, FC, act, PRICE, np.full(24, 80.0), np.zeros((24, 3)))
    sun = out[FC > 0]
    assert np.abs(sun["imbalance MWh"]).max() < 1e-6
