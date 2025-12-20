from dateutil import rrule
from datetime import date, datetime, timedelta
from django.core.exceptions import ValidationError
from django.utils.timezone import make_aware, is_naive, make_naive, is_aware
from django.db.models import Q, Case, When, Value
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

# start of occurrence related functions

def combine_occurrences(generators, limit):
    """Merge the occurrences in two or more generators, in date order.

       Returns a generator. """

    count = 0
    grouped = []
    for gen in generators:
        try:
            next_date = next(gen)
        except StopIteration:
            pass
        else:
            grouped.append({'generator': gen, 'next': next_date})

    while limit is None or count < limit:
        # all generators must have finished if there are no groups
        if not len(grouped):
            return

        # work out which generator will yield the earliest date (based on
        # start - end is ignored)
        next_group = None
        for group in grouped:
            if not next_group or group['next'][0] < next_group['next'][0]:
                next_group = group

        # yield the next (start, end) pair, with occurrence data
        yield next_group['next']
        count += 1

        # update the group's next item, so we don't keep yielding the same date
        try:
            next_group['next'] = next(next_group['generator'])
        except StopIteration:
            # remove the group if there's none left
            grouped.remove(next_group)


def filter_invalid(approx_qs, from_date, to_date):
    """Filter out any results from the queryset which do not have an occurrence
       within the given range. """

    # work out what to exclude based on occurrences
    exclude_pks = []
    for obj in approx_qs:
        if not obj.next_occurrence(from_date=from_date, to_date=to_date):
            exclude_pks.append(obj.pk)

    # and then apply the filtering to the queryset itself
    return approx_qs.exclude(pk__in=exclude_pks)


def filter_from(qs, from_date, q_func=Q):
    """Filter a queryset by from_date. May still contain false positives due to
       uncertainty with repetitions. """

    from_date = as_datetime(from_date)
    return qs.filter(
        q_func(end__isnull=False, end__gte=from_date) |
        q_func(start__gte=from_date) |
        (~q_func(repeat='') & (q_func(repeat_until__gte=from_date) |
         q_func(repeat_until__isnull=True)))).distinct()
