"""Release identity and publication gates shared by live ISM acquisition."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pandas.tseries.holiday import USFederalHolidayCalendar

NY = ZoneInfo("America/New_York")


def publication_at(reference: datetime, kind: str) -> datetime:
    month = (reference.replace(day=28) + timedelta(days=4)).replace(day=1)
    holidays = {
        x.date() for x in USFederalHolidayCalendar().holidays(month, month + timedelta(days=15))
    }
    day, count = month.date(), 0
    while True:
        if day.weekday() < 5 and day not in holidays:
            count += 1
        if count == (1 if kind == "manufacturing" else 3):
            return datetime.combine(day, time(10), NY).astimezone(UTC)
        day += timedelta(days=1)


def expected_reference(kind: str, now: datetime) -> datetime:
    reference = (now.astimezone(NY).replace(day=1) - timedelta(days=1)).replace(day=1)
    if publication_at(reference, kind) > now:
        reference = (reference - timedelta(days=1)).replace(day=1)
    return reference


def release_identity(report, now: datetime) -> dict:
    reference = datetime.strptime(report.report_month, "%B %Y")
    published = publication_at(reference, report.kind)
    expected = expected_reference(report.kind, now)
    status = (
        "UNPUBLISHED"
        if published > now
        else "CURRENT"
        if reference.strftime("%Y-%m") == expected.strftime("%Y-%m")
        else "STALE"
    )
    return {
        "report_type": report.kind.upper(),
        "reference_month": reference.strftime("%Y-%m"),
        "expected_reference_month": expected.strftime("%Y-%m"),
        "publication_date": published.date().isoformat(),
        "publication_at": published.isoformat(),
        "publication_date_basis": "first/third US business day at 10:00 America/New_York",
        "retrieved_at": now.isoformat(),
        "source_url": report.source_url,
        "release_status": status,
    }
