from auroragaze.tools.physics import assess_visibility


def test_quiet_kp_unlikely_in_hobart() -> None:
    v = assess_visibility(lat=-42.88, lon=147.32, kp=1.0)
    assert v.level == "unlikely"


def test_strong_storm_likely_in_hobart() -> None:
    v = assess_visibility(lat=-42.88, lon=147.32, kp=8.0)
    assert v.level == "likely"


def test_possible_in_melbourne_at_kp_six() -> None:
    v = assess_visibility(lat=-37.81, lon=144.96, kp=6.0)
    assert v.level in {"possible", "likely"}


def test_brisbane_unlikely_unless_extreme() -> None:
    v = assess_visibility(lat=-27.47, lon=153.03, kp=5.0)
    assert v.level == "unlikely"
    v_strong = assess_visibility(lat=-27.47, lon=153.03, kp=9.0)
    assert v_strong.level in {"possible", "likely"}


def test_boundary_lat_decreases_with_kp() -> None:
    quiet = assess_visibility(lat=-42.88, lon=147.32, kp=2.0).boundary_lat_deg
    storm = assess_visibility(lat=-42.88, lon=147.32, kp=7.0).boundary_lat_deg
    assert storm < quiet
