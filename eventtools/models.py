import datetime
from zoneinfo import ZoneInfo

from django.db import models
from django.utils import timezone as dj_timezone
from dateutil.rrule import rrulestr, rruleset
from dateutil.parser import isoparse  # prefer isoparse for ISO strings

import pendulum
from pendulum.tz.timezone import Timezone
from django.core.exceptions import ValidationError
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
    def _(self, dt: datetime.datetime):
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


class OccurrenceQuerySet(models.QuerySet):

    def tzDateConv(self, event_tz):
        return tzDateFactory(event_tz)

    def all_occurrences(self, from_date=None, to_date=None, count=None, event_tz=None):
        # Default: use an aware datetime
        if from_date is None:
            #from_date = pendulum.now("UTC")
            from_date = pendulum.instance(dj_timezone.now())
        else:    
            from_date = self.tzDateConv(event_tz).aware(from_date)

        # Enforce awareness
        if dj_timezone.is_naive(from_date):
            raise ValueError("from_date must be timezone-aware")
        # if to_date is not None and dj_timezone.is_naive(to_date):
        #     raise ValueError("to_date must be timezone-aware")
        if to_date is not None:
            to_date = self.tzDateConv(event_tz).aware(to_date)
        #     raise ValueError("to_date must be timezone-aware")

        all_occs = []

        for occ in self:
            # Ask each occurrence only for what's still needed (global count)
            remaining = None
            if count is not None:
                remaining = count - len(all_occs)
                if remaining <= 0:
                    break

            occ_occs = occ.generate_occurrences(
                from_date=from_date,
                to_date=to_date,
                count=remaining,
            )
            all_occs.extend(occ_occs)

        all_occs.sort(key=lambda x: x[0])

        if count is not None:
            all_occs = all_occs[:count]

        return all_occs


class BaseEvent(models.Model):
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=100)
    timezone = models.CharField(max_length=63, default="UTC")

    def __str__(self):
        return self.name

    def all_occurrences(self, from_date=None, to_date=None, count=None):
        return self.occurrences.all_occurrences(from_date, to_date, count, event_tz=self.timezone )

    def next_occurrence(self, from_date=None):
        occs = self.all_occurrences(from_date=from_date, count=1)
        return occs[0] if occs else None

    def first_occurrence(self):
        # avoid datetime.min (can be problematic); use "now minus a lot"
        return self.next_occurrence(from_date=dj_timezone.now() - datetime.timedelta(days=365 * 50))


class BaseOccurrence(models.Model):
    event = models.ForeignKey(BaseEvent, on_delete=models.CASCADE, related_name="occurrences")
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)
    rrule = models.TextField(blank=True, null=True)
    #timezone = models.CharField(max_length=63, default="UTC")
    exdates_json = models.JSONField(default=list, blank=True)
    rdates_json = models.JSONField(default=list, blank=True)

    objects = OccurrenceQuerySet.as_manager()

    @property
    def tzDateConv(self):
        return tzDateFactory(self.event.timezone)

    def __str__(self):
        return f"{self.event.name} occurrence starting {self.start}"


    def save(self, *args, **kwargs):
        if self.start:
            self.start = self.tzDateConv.aware(self.start)
        if self.end:
            self.end = self.tzDateConv.aware(self.end)
        super().save(*args, **kwargs)


    def parse_dates(self, dates_json):
        tz = self.tzDateConv.get_tz()
        parsed = []
        for d_str in dates_json:
            d = isoparse(d_str)  # datetime
            if d.tzinfo is None:
                d = pendulum.datetime(
                    d.year, d.month, d.day, d.hour, d.minute, d.second, d.microsecond,
                    tz=tz
                )
            else:
                d = pendulum.instance(d).in_timezone(tz)
            parsed.append(d)
        return parsed


    def generate_occurrences(self, from_date=None, to_date=None, count=None):
        tz = self.tzDateConv.get_tz()

        if from_date is None:
            from_date = dj_timezone.now()
        if dj_timezone.is_naive(from_date):
            raise ValueError("from_date must be timezone-aware")
        from_local = from_date.astimezone(tz)

        to_local = None
        if to_date is not None:
            if dj_timezone.is_naive(to_date):
                raise ValueError("to_date must be timezone-aware")
            to_local = to_date.astimezone(tz)

        start_local = self.tzDateConv.aware(self.start)
        end_local = self.tzDateConv.aware(self.end) if self.end else None
        duration = (end_local - start_local) if end_local else datetime.timedelta(0)

        exdates = set(self.parse_dates(self.exdates_json))
        rdates = self.parse_dates(self.rdates_json)

        rset = rruleset()

        if self.rrule:
            # Ensure dtstart is in occurrence timezone
            main_rrule = rrulestr(self.rrule, dtstart=start_local)
            rset.rrule(main_rrule)
        else:
            rset.rdate(start_local)

        for rd in rdates:
            rset.rdate(rd)
        for ex in exdates:
            rset.exdate(ex)

        occurrences = []
        next_start = rset.after(from_local, inc=True)
        while next_start:
            if to_local and next_start >= to_local:
                break

            next_end = (next_start + duration) if self.end else None
            occurrences.append((next_start, next_end, self))

            if count and len(occurrences) >= count:
                break

            next_start = rset.after(next_start, inc=False)

        return occurrences
    

    def clean(self):
        # 1) Validate timezone (raises ValidationError if invalid)
        tz = self.tzDateConv.get_tz()

        # 2) Normalize start/end using your factory (same logic as save)
        if self.start:
            self.start = self.tzDateConv.aware(self.start)
        if self.end:
            self.end = self.tzDateConv.aware(self.end)

        # 3) Core validations (same as old behavior)
        if self.start and self.end and self.start >= self.end:
            raise ValidationError("End must be after start")

        # 4) Validate RRULE string early (nice admin UX)
        if self.rrule:
            try:
                # dtstart must be in the correct timezone
                start_local = self.tzDateConv.aware(self.start)
                rrulestr(self.rrule, dtstart=start_local)
            except Exception as exc:
                raise ValidationError({"rrule": f"Invalid RRULE: {exc}"}) from exc

        # 5) Optional: validate exdates/rdates ISO parsing early
        # (ensures bad strings are caught before save/generate)
        try:
            self.parse_dates(self.exdates_json)
        except Exception as exc:
            raise ValidationError({"exdates_json": f"Invalid EXDATE value: {exc}"}) from exc

        try:
            self.parse_dates(self.rdates_json)
        except Exception as exc:
            raise ValidationError({"rdates_json": f"Invalid RDATE value: {exc}"}) from exccv
        return

# Test models inheriting from the base classes for tests.py    
class MyEvent(BaseEvent):
    #title = models.CharField(max_length=100)
    pass
    # def __str__(self):
    #     return self.title

class MyOccurrence(BaseOccurrence):
    # event = models.ForeignKey(
    #     MyEvent,
    #     on_delete=models.CASCADE,
    #     related_name="occurrences",
    # )
    pass

class MyOtherOccurrence(BaseOccurrence):
    #  event = models.ForeignKey(
    #      MyEvent, 
    #      on_delete=models.CASCADE
    # )
    pass
