from dateutil import rrule
from datetime import date, datetime, timedelta
from django.core.exceptions import ValidationError
from django.utils.timezone import make_aware, is_naive, make_naive, is_aware
from django.conf import settings

import pendulum
from functools import singledispatchmethod

class tzDateFactory:
    """
    Create timezone-aware Pendulum datetimes using a fixed timezone.
    """

    def __init__(self, timezone: str):
        self.timezone = timezone

    def get_tz(self):
        """
        Return a valid Pendulum timezone or raise ValidationError.
        """
        try:
            return pendulum.timezone(self.timezone)
        except Exception:
            raise ValidationError(
                {"timezone": f"Invalid timezone: {self.timezone}"}
            )

    @singledispatchmethod
    def aware(self, arg):
        raise TypeError("aware() unsupported type")

    @aware.register
    def _(self, dt: datetime):
        """
        Accept a datetime.
        - Naive: interpret as local time in self.timezone
        - Aware: convert into self.timezone
        """
        tz = self.get_tz()
        if dt.tzinfo is None:
            return pendulum.datetime(
                dt.year, dt.month, dt.day,
                dt.hour, dt.minute, dt.second,
                dt.microsecond,
                tz=tz,
            )
        return pendulum.instance(dt).in_timezone(tz)

    @aware.register
    def _(self, arg: tuple):
        """
        Accept (y, m, d[, hh, mm, ss]) as a tuple.
        """
        y, m, d, *rest = arg
        hh, mm, ss = (rest + [0, 0, 0])[:3]

        tz = self.get_tz()

        try:
            return pendulum.datetime(y, m, d, hh, mm, ss, tz=tz)
        except Exception as exc:
            raise ValidationError(
                f"Invalid datetime components: "
                f"{y=}, {m=}, {d=}, {hh=}, {mm=}, {ss=} ({exc})"
            ) from exc
        return




def max_future_date():
    return datetime(date.today().year + 10, 1, 1, 0, 0)


def first_item(gen):
    try:
        return next(gen)
    except StopIteration:
        return None


def default_aware(dt):
    """Convert a naive datetime argument to a tz-aware datetime, if tz support
       is enabled. """

    if settings.USE_TZ and is_naive(dt):
        return make_aware(dt)

    # if timezone support disabled, assume only naive datetimes are used
    return dt


def default_naive(dt):
    """Convert an aware datetime argument to naive, if tz support
       is enabled. """

    if settings.USE_TZ and is_aware(dt):
        return make_naive(dt)

    # if timezone support disabled, assume only naive datetimes are used
    return dt


def as_datetime(d, end=False):
    """Normalise a date/datetime argument to a datetime for use in filters

    If a date is passed, it will be converted to a datetime with the time set
    to 0:00, or 23:59:59 if end is True."""

    if type(d) is date:
        date_args = tuple(d.timetuple())[:3]
        if end:
            time_args = (23, 59, 59)
        else:
            time_args = (0, 0, 0)
        new_value = datetime(*(date_args + time_args))
        return default_aware(new_value)
    # otherwise assume it's a datetime
    return default_aware(d)