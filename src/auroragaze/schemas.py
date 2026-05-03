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


class KpBin(BaseModel):
    """One 3-hour bin of forecast Kp from NOAA SWPC."""

    start: datetime
    end: datetime
    kp: float = Field(ge=0, le=9)


class KpForecast(BaseModel):
    bins: list[KpBin]
    issued: datetime
    source: str = "NOAA SWPC 3-day Kp forecast"


class NightWindow(BaseModel):
    """Local night for one location on one date.

    Times are zero-padded `HH:MM` strings in the location's timezone, plus
    UTC datetimes for the bookending sunrise / sunset. Twilight values
    can be `None` for high-latitude polar-night / midnight-sun cases.
    """

    sunset_local: str
    civil_dusk_local: str | None = None
    astro_night_start_local: str | None = None
    astro_night_end_local: str | None = None
    civil_dawn_local: str | None = None
    sunrise_local: str
    sunset_utc: datetime
    sunrise_utc: datetime
    timezone: str
    is_daylight_now: bool = Field(
        description="True if the request time falls within civil daylight at this location."
    )


class VisibilityWindow(BaseModel):
    """Aurora visibility scoped to the upcoming local night."""

    evening: Visibility = Field(description="Civil dusk → astronomical night start")
    night: Visibility = Field(description="Astronomical night, the prime viewing block")
    dawn: Visibility = Field(description="Astronomical night end → civil dawn")
    peak_local: str = Field(description="Local time of peak forecast Kp")
    peak_kp: float = Field(ge=0, le=9)
    headline_level: Literal["likely", "possible", "unlikely"]
    summary_window: str = Field(
        description="Best-time bracket as a string, e.g. '21:30 → 03:10 AEST'"
    )


class Chunk(BaseModel):
    text: str
    source: str
    event_date: str | None = None
    kp_peak: float | None = None
    score: float | None = None


class Citation(BaseModel):
    source: str
    detail: str


class RankedSpot(BaseModel):
    """One candidate viewing spot inside the chaser's drive radius."""

    name: str = Field(description="Place name from OSM, or '15 km SW of <base>' fallback")
    lat: float
    lon: float
    distance_km: float = Field(ge=0)
    bearing: str = Field(description="Cardinal/intercardinal: N, NE, E, SE, S, SW, W, NW")
    geomag_visibility: Visibility
    cloud_pct: int = Field(ge=0, le=100, description="Mean cloud cover over night window")
    bortle: int = Field(
        ge=1,
        le=9,
        description="Estimated Bortle class (1=pristine dark, 9=inner-city)",
    )
    score: float = Field(ge=0, le=1, description="Composite 0..1 ranking score")
    rank: int = Field(ge=1)
    why: str = Field(description="One sentence explaining the rank rationale")
    is_base: bool = Field(default=False, description="True for the user's chosen city")


class AuroraBriefing(BaseModel):
    summary: str = Field(description="1-2 plain-English sentences, no jargon")
    location: str
    when_local: str = Field(
        description="Local time bracket the briefing covers, e.g. 'tonight 21:30 → 03:10 AEST'"
    )
    visibility: Visibility
    viewing_window: VisibilityWindow | None = None
    headline: str
    body: str
    citations: list[Citation]
    radius_km: int | None = Field(
        default=None,
        description="Search radius in km for the ranked-spots survey",
    )
    ranked_spots: list[RankedSpot] = Field(
        default_factory=list,
        description="Candidate viewing spots inside radius, best-first",
    )


class SatelliteBriefing(BaseModel):
    summary: str = Field(description="1-2 plain-English sentences, no jargon")
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
    night_window: NightWindow
    kp_forecast: KpForecast
    visibility_window: VisibilityWindow
    request_time_utc: datetime
    fleet_impact: dict[str, object]
    briefing: AuroraBriefing | SatelliteBriefing
    retry_hint: str
    retry_count: int
    radius_km: int
    ranked_spots: list[RankedSpot]
    trace: Annotated[list[str], add]
