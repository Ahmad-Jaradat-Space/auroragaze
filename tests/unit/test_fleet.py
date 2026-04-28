from auroragaze.tools.fleet import FleetUnit, assess_fleet_impact


def _starlink_like() -> list[FleetUnit]:
    return [
        FleetUnit(name="bus-A", altitude_km=350, orbit_class="LEO_low"),
        FleetUnit(name="bus-B", altitude_km=550, orbit_class="LEO_mid"),
        FleetUnit(name="geo-comms", altitude_km=35786, orbit_class="GEO"),
    ]


def test_quiet_fleet_no_action() -> None:
    impact = assess_fleet_impact(_starlink_like(), kp=2.0)
    assert impact.headline.startswith("Quiet")
    for u in impact.units:
        assert u.recommended_actions[0].startswith("No action")


def test_g4_fleet_high_drag_for_low_leo() -> None:
    impact = assess_fleet_impact(_starlink_like(), kp=8.0)
    low_leo = next(u for u in impact.units if u.unit == "bus-A")
    assert low_leo.drag is not None
    assert low_leo.drag.severity in {"high", "extreme"}


def test_geo_charging_risk_at_g3() -> None:
    impact = assess_fleet_impact(_starlink_like(), kp=7.0)
    geo = next(u for u in impact.units if u.unit == "geo-comms")
    assert geo.surface_charging_risk == "high"
    assert geo.drag is None
