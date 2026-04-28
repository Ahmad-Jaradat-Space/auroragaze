from datetime import datetime
from operator import add
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


class SolarWind(BaseModel):
    bz: float = Field(description="GSM Bz, nT (southward = negative)")
    bt: float = Field(description="Total IMF strength, nT")
    speed_kms: float = Field(description="Bulk solar-wind speed, km/s")
    density_cm3: float = Field(description="Proton density, cm^-3")
    timestamp: datetime
    source: str = "NOAA SWPC DSCOVR (real-time, 5-minute averages)"


class KpReading(BaseModel):
    kp: float = Field(ge=0, le=9)
    timestamp: datetime
    source: str = "NOAA SWPC planetary K-index (3-hour)"


class Visibility(BaseModel):
    level: Literal["likely", "possible", "unlikely"]
    boundary_lat_deg: float = Field(description="Approx equatorward auroral oval boundary, °S")
    reasoning: str
    table_source: str = "Akasofu 1964; NOAA SWPC Kp-to-oval lookup"


class Chunk(BaseModel):
    text: str
    source: str
    event_date: str | None = None
    kp_peak: float | None = None
    score: float | None = None


class Citation(BaseModel):
    source: str
    detail: str


class AuroraBriefing(BaseModel):
    location: str
    when_local: str
    visibility: Visibility
    headline: str
    body: str
    citations: list[Citation]


class SatelliteBriefing(BaseModel):
    fleet_label: str
    storm_summary: str
    headline: str
    body: str
    per_unit_actions: list[str]
    citations: list[Citation]


class BriefingState(TypedDict, total=False):
    persona: Literal["aurora", "satellite"]
    lat: float
    lon: float
    location_label: str
    fleet: list[dict[str, str | float]]
    fleet_label: str
    query: str
    solar_wind: SolarWind
    kp: KpReading
    dst_nt: float
    flare_class: str
    chunks: list[Chunk]
    visibility: Visibility
    fleet_impact: dict[str, object]
    briefing: AuroraBriefing | SatelliteBriefing
    trace: Annotated[list[str], add]
