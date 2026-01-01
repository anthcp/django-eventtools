import pytest
from datetime import datetime
import pendulum

def test_convert_between_contexts(London, NewYork):
    meeting = London.datetime(2025, 6, 1, 14, 0)
    meeting_ny = meeting.convert(NewYork)

    assert meeting.timezone_name == "Europe/London"
    assert meeting_ny.timezone_name == "America/New_York"
    # same instant
    assert meeting == meeting_ny


def test_same_moment_equality_across_timezones(London, NewYork):
    meeting1 = London.datetime(2025, 6, 1, 14, 0)
    meeting2 = NewYork.datetime(2025, 6, 1, 9, 0)

    assert meeting1 == meeting2  # same instant


def test_add_time(London):
    meeting1 = London.datetime(2025, 6, 1, 14, 0)
    later = meeting1.add(hours=2, minutes=30)

    assert later.timezone_name == "Europe/London"
    assert later.year == 2025 and later.month == 6 and later.day == 1
    assert later.hour == 16 and later.minute == 30


def test_strftime_formatting(London):
    meeting1 = London.datetime(2025, 6, 1, 14, 0)

    assert meeting1.strftime("%A, %d %B %Y @ %H:%M") == "Sunday, 01 June 2025 @ 14:00"


def test_pendulum_formatting(London):
    meeting1 = London.datetime(2025, 6, 1, 14, 0)

    assert meeting1.format("dddd, D MMMM YYYY [at] HH:mm") == "Sunday, 1 June 2025 at 14:00"


def test_duration_diff_hours_minutes(London):
    start = London.datetime(2025, 6, 1, 14, 0)
    end = London.datetime(2025, 6, 1, 16, 45)

    diff = end - start
    assert diff.hours == 2
    assert diff.minutes == 45

def test_start_of_week_and_end_of_month(London):
    event = London.datetime(2025, 6, 15, 14, 0)

    sow = event.start_of("week")
    eom = event.end_of("month")

    # Pendulum start_of('week') defaults to Monday as start of week
    assert sow.year == 2025 and sow.month == 6
    assert sow.day == 9
    assert sow.hour == 0 and sow.minute == 0 and sow.second == 0

    # June has 30 days
    assert eom.day == 30


def test_naive_input_creation(London):
    """Verify that naive integers create the correct aware object."""
    ev = London.datetime(2025, 6, 1, 12, 0)
    assert ev.year == 2025
    assert ev.month == 6
    assert ev.hour == 12
    assert ev.timezone_name == "Europe/London"
    # London is UTC+1 in June
    assert ev.offset_hours == 1

def test_date_factory(NewYork):
    """Verify the .date() method defaults to midnight."""
    ev = NewYork.date_at(2025, 12, 25)
    assert ev.hour == 0
    assert ev.minute == 0
    assert ev.timezone_name == "America/New_York"

def test_timezone_conversion(London, NewYork):
    """Verify that converting between contexts shifts the wall-clock time correctly."""
    # 2:00 PM London in June (UTC+1)
    london_meeting = London.datetime(2025, 6, 1, 14, 0)
    
    # Convert to New York (UTC-4) -> Should be 9:00 AM
    ny_meeting = london_meeting.convert(NewYork)
    
    assert ny_meeting.hour == 9
    assert ny_meeting.timezone_name == "America/New_York"
    # Ensure they represent the exact same moment in absolute time
    assert london_meeting == ny_meeting


def test_context_timezone_is_stable(London):
    original = London._forced_tz
    London.timezone = "Asia/Tokyo"  # allowed, but should be irrelevant
    assert London._forced_tz == original


def test_rrule_compatibility(London):
    """Verify that Event objects work with dateutil rrules."""
    from dateutil.rrule import rrule, DAILY
    start = London.datetime(2025, 1, 1, 10, 0)
    rule = rrule(DAILY, count=3, dtstart=start)
    results = list(rule)
    assert len(results) == 3
    # Check that we can cast them back to our Event class
    casted = London.from_any_datetime(results[1])
    assert isinstance(casted, London)
    assert casted.day == 2