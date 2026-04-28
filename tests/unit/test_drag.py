from auroragaze.tools.drag import compute_drag_delta


def test_quiet_kp_low_severity() -> None:
    d = compute_drag_delta(altitude_km=400, kp=2.0)
    assert d.severity == "low"
    assert d.drag_dv_fraction_increase < 0.10


def test_g3_at_300km_moderate() -> None:
    d = compute_drag_delta(altitude_km=300, kp=7.0)
    assert d.severity in {"moderate", "high"}


def test_g5_at_300km_extreme() -> None:
    d = compute_drag_delta(altitude_km=300, kp=9.0)
    assert d.severity == "extreme"


def test_higher_altitude_lower_drag() -> None:
    low = compute_drag_delta(altitude_km=300, kp=8.0).drag_dv_fraction_increase
    high = compute_drag_delta(altitude_km=800, kp=8.0).drag_dv_fraction_increase
    assert high < low
