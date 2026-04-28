"""Fleet-level impact assessment for a satellite operator briefing."""

from typing import Literal

from pydantic import BaseModel, Field

from auroragaze.tools.drag import DragDelta, compute_drag_delta


class FleetUnit(BaseModel):
    name: str
    altitude_km: float
    orbit_class: Literal["LEO_low", "LEO_mid", "LEO_high", "MEO", "GEO"]
    hardness: Literal["low", "standard", "hardened"] = "standard"
    mission: str = "communications"


class UnitImpact(BaseModel):
    unit: str
    drag: DragDelta | None = None
    surface_charging_risk: Literal["low", "moderate", "high"]
    recommended_actions: list[str]


class FleetImpact(BaseModel):
    kp: float
    units: list[UnitImpact]
    headline: str = Field(description="One-line top recommendation across the fleet")


def _surface_charging_risk(orbit_class: str, kp: float) -> Literal["low", "moderate", "high"]:
    if orbit_class in {"GEO", "MEO"}:
        if kp >= 7:
            return "high"
        if kp >= 5:
            return "moderate"
        return "low"
    if kp >= 7:
        return "moderate"
    return "low"


def _actions_for_unit(unit: FleetUnit, kp: float) -> list[str]:
    actions: list[str] = []
    if unit.orbit_class in {"LEO_low", "LEO_mid"} and kp >= 6:
        actions.append("Defer non-essential maneuvers; check station-keeping margin.")
    if unit.altitude_km < 350 and kp >= 5:
        actions.append("Consider safe-mode (edge-on flight orientation) to minimise drag.")
    if unit.orbit_class == "GEO" and kp >= 7:
        actions.append("Increase telemetry cadence; monitor for surface-charging anomalies.")
    if unit.orbit_class == "MEO" and kp >= 7:
        actions.append("Watch GNSS payload for SEU rate increase; verify ECC margin.")
    if kp >= 8:
        actions.append("Notify customers of likely service-quality variation; pre-stage on-call.")
    if not actions:
        actions.append("No action required; nominal operations.")
    return actions


def assess_fleet_impact(fleet: list[FleetUnit], kp: float) -> FleetImpact:
    impacts: list[UnitImpact] = []
    for u in fleet:
        drag = None
        if u.orbit_class in {"LEO_low", "LEO_mid", "LEO_high"}:
            drag = compute_drag_delta(altitude_km=u.altitude_km, kp=kp)
        impacts.append(
            UnitImpact(
                unit=u.name,
                drag=drag,
                surface_charging_risk=_surface_charging_risk(u.orbit_class, kp),
                recommended_actions=_actions_for_unit(u, kp),
            )
        )
    headline = _headline(impacts, kp)
    return FleetImpact(kp=kp, units=impacts, headline=headline)


def _headline(impacts: list[UnitImpact], kp: float) -> str:
    if kp < 5:
        return "Quiet conditions; nominal operations across the fleet."
    severe_drag = [i for i in impacts if i.drag and i.drag.severity in {"high", "extreme"}]
    if severe_drag:
        return (
            f"Drag risk elevated for {len(severe_drag)} LEO asset(s); "
            f"defer maneuvers and consider safe-mode for low-altitude units."
        )
    high_charge = [i for i in impacts if i.surface_charging_risk == "high"]
    if high_charge:
        return f"Surface-charging risk elevated for {len(high_charge)} GEO/MEO asset(s); monitor."
    return "Storm conditions but no fleet-critical risks at current Kp."
