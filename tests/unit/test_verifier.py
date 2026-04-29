from datetime import UTC, datetime

from auroragaze.agents.verifier import verify_briefing
from auroragaze.schemas import Chunk, KpReading, SolarWind, Visibility


def _state(**extra: object) -> dict[str, object]:
    sw = SolarWind(bz=-12.5, bt=14.0, speed_kms=680.0, density_cm3=8.1, timestamp=datetime.now(UTC))
    kp = KpReading(kp=6.2, timestamp=datetime.now(UTC))
    vis = Visibility(level="possible", boundary_lat_deg=46.0, reasoning="x")
    return {"solar_wind": sw, "kp": kp, "visibility": vis, "chunks": [], **extra}


def test_grounded_briefing_passes() -> None:
    text = "Bz is -12.5 nT, speed 680 km/s, Kp 6.2, oval at 46°S."
    assert verify_briefing(text, _state()) == []


def test_rounded_kp_within_tolerance() -> None:
    text = "Kp is 6 right now, oval near 46°S."
    assert verify_briefing(text, _state()) == []


def test_fabricated_kp_flagged() -> None:
    text = "Kp is 9 right now and Bz is -50 nT."
    bad = verify_briefing(text, _state())
    assert 9.0 in bad or -50.0 in bad


def test_chunk_numbers_count_as_supported() -> None:
    chunks = [Chunk(text="The November 2023 event hit Kp 7 from Hobart.", source="x")]
    text = "Compared to the November 2023 storm at Kp 7, tonight is much quieter."
    assert verify_briefing(text, _state(chunks=chunks)) == []


def test_dates_not_flagged() -> None:
    text = "On 2024-05-11 the Gannon storm peaked at Kp 9; tonight Kp is 6.2."
    chunks = [Chunk(text="May 2024 storm peaked at Kp 9.", source="x")]
    assert verify_briefing(text, _state(chunks=chunks)) == []
