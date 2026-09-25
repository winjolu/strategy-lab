"""The fee function against the exchange's published table, and the multiplier timeline."""
import pytest

from lab.engine import event_costs as ec

# Exchange's published "General Trading Fees Table" (July 2026 edition):
# price, fee for 1 contract, fee for 100 contracts.
PUBLISHED = [
    ("0.01", "0.01", "0.07"), ("0.05", "0.01", "0.34"), ("0.10", "0.01", "0.63"),
    ("0.15", "0.01", "0.90"), ("0.20", "0.02", "1.12"), ("0.25", "0.02", "1.32"),
    ("0.30", "0.02", "1.47"), ("0.35", "0.02", "1.60"), ("0.40", "0.02", "1.68"),
    ("0.45", "0.02", "1.74"), ("0.65", "0.02", "1.60"), ("0.70", "0.02", "1.47"),
    ("0.75", "0.02", "1.32"), ("0.80", "0.02", "1.12"), ("0.85", "0.01", "0.90"),
    ("0.90", "0.01", "0.63"), ("0.95", "0.01", "0.34"), ("0.99", "0.01", "0.07"),
]


@pytest.mark.parametrize("price,one,hundred", PUBLISHED)
def test_matches_the_published_table(price, one, hundred):
    assert ec.taker_fee(price, 1) == float(one)
    assert ec.taker_fee(price, 100) == float(hundred)


def test_floating_point_does_not_add_a_cent():
    assert 0.07 * 100 * 0.10 * 0.90 > 0.63  # the trap: binary float lands above
    assert ec.taker_fee("0.10", 100) == 0.63


def test_rounding_is_per_order_not_per_contract():
    ten_singles = sum(ec.taker_fee("0.10", 1) for _ in range(10))
    assert ten_singles == pytest.approx(0.10) and ec.taker_fee("0.10", 10) == 0.07


def test_the_multiplier_scales_before_rounding():
    assert ec.taker_fee("0.10", 100, 0.5) == 0.32   # 0.315 rounds up
    assert ec.taker_fee("0.10", 100, 0) == 0.0
    assert ec.taker_fee("0.50", 100, 2) == 3.50


def test_the_fee_is_symmetric_between_yes_and_no():
    assert ec.taker_fee("0.07", 37) == ec.taker_fee("0.93", 37)


@pytest.mark.parametrize("bad", ["0", "1", "1.2", "-0.1"])
def test_a_price_outside_the_open_interval_is_refused(bad):
    with pytest.raises(ValueError):
        ec.taker_fee(bad, 1)


@pytest.mark.parametrize("bad", [0, -1, 1.5])
def test_a_fractional_or_empty_order_is_refused(bad):
    with pytest.raises(ValueError):
        ec.taker_fee("0.10", bad)


CHANGES = [("A", "2025-10-04T07:00:00Z", 1.0), ("A", "2026-08-07T04:59:00Z", 0.5),
           ("B", "2026-03-03T05:00:00Z", 0.0)]


def test_before_the_first_recorded_change_the_default_applies():
    s = ec.FeeSchedule(CHANGES)
    assert s.multiplier("B", "2026-03-02T00:00:00Z") == 1.0
    assert s.multiplier("UNLISTED", "2026-01-01T00:00:00Z") == 1.0


def test_a_change_applies_from_its_scheduled_time_inclusive():
    s = ec.FeeSchedule(CHANGES)
    assert s.multiplier("A", "2026-08-07T04:58:59Z") == 1.0
    assert s.multiplier("A", "2026-08-07T04:59:00Z") == 0.5
    assert s.multiplier("A", "2027-01-01T00:00:00Z") == 0.5


def test_changes_are_ordered_by_time_not_by_arrival():
    s = ec.FeeSchedule(list(reversed(CHANGES)))
    assert s.multiplier("A", "2026-01-01T00:00:00Z") == 1.0
    assert s.multiplier("A", "2026-09-01T00:00:00Z") == 0.5


def test_a_timeline_that_ends_away_from_the_listing_is_reported():
    s = ec.FeeSchedule(CHANGES, current={"A": 0.5, "B": 1.0})
    assert s.disagreements() == {"B": (0.0, 1.0)}
