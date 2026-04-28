from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from auroragaze.schemas import KpReading, SolarWind, Visibility


def test_kp_within_bounds() -> None:
    KpReading(kp=5.0, timestamp=datetime.now(UTC))
    with pytest.raises(ValidationError):
        KpReading(kp=10.0, timestamp=datetime.now(UTC))


def test_solar_wind_default_source() -> None:
    sw = SolarWind(
        bz=-10.0,
        bt=12.0,
        speed_kms=500.0,
        density_cm3=5.0,
        timestamp=datetime.now(UTC),
    )
    assert "DSCOVR" in sw.source


def test_visibility_level_literal() -> None:
    v = Visibility(level="likely", boundary_lat_deg=50.0, reasoning="test")
    assert v.level == "likely"
    with pytest.raises(ValidationError):
        Visibility(level="maybe", boundary_lat_deg=50.0, reasoning="test")  # type: ignore[arg-type]
