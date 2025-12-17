import datetime
from zoneinfo import ZoneInfo

from django.db import models
from django.utils import timezone as dj_timezone
from dateutil.rrule import rrulestr, rruleset
from dateutil.parser import isoparse  # prefer isoparse for ISO strings

class OccurrenceQuerySet(models.QuerySet):
    def all_occurrences(self, from_date=None, to_date=None, count=None):
        if from_date is None:
            from_date = dj_timezone.now()
        if dj_timezone.is_naive(from_date):
            raise ValueError("from_date must be timezone-aware")

        if to_date is not None and dj_timezone.is_naive(to_date):
            raise ValueError("to_date must be timezone-aware")

        all_occs = []
        for occ in self:
            all_occs.extend(occ.generate_occurrences(from_date, to_date, count))
        all_occs.sort(key=lambda x: x[0])

        if count:
            all_occs = all_occs[:count]

        return all_occs


class BaseEvent(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    def all_occurrences(self, from_date=None, to_date=None, count=None):
        return self.occurrences.all_occurrences(from_date, to_date, count)

    def next_occurrence(self, from_date=None):
        occs = self.all_occurrences(from_date=from_date, count=1)
        return occs[0] if occs else None

    def first_occurrence(self):
        # avoid datetime.min (can be problematic); use "now minus a lot"
        return self.next_occurrence(from_date=dj_timezone.now() - datetime.timedelta(days=365 * 50))


class BaseOccurrence(models.Model):
    #event = models.ForeignKey(BaseEvent, on_delete=models.CASCADE, related_name="occurrences")
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)
    rrule = models.TextField(blank=True, null=True)
    timezone = models.CharField(max_length=63, default="UTC")
    exdates_json = models.JSONField(default=list, blank=True)
    rdates_json = models.JSONField(default=list, blank=True)

    objects = OccurrenceQuerySet.as_manager()

    def __str__(self):
        return f"{self.event.name} occurrence starting {self.start}"

    def get_tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def _ensure_aware_in_tz(self, dt: datetime.datetime) -> datetime.datetime:
        """
        Ensure dt is timezone-aware and represented in the occurrence timezone.
        """
        tz = self.get_tz()
        if dj_timezone.is_naive(dt):
            dt = dj_timezone.make_aware(dt, tz)
        return dt.astimezone(tz)

    def save(self, *args, **kwargs):
        # Normalize start/end into the occurrence timezone
        if self.start:
            self.start = self._ensure_aware_in_tz(self.start)
        if self.end:
            self.end = self._ensure_aware_in_tz(self.end)
        super().save(*args, **kwargs)

    def parse_dates(self, dates_json):
        tz = self.get_tz()
        parsed = []
        for d_str in dates_json:
            d = isoparse(d_str)  # strict ISO
            if dj_timezone.is_naive(d):
                d = dj_timezone.make_aware(d, tz)
            parsed.append(d.astimezone(tz))
        return parsed

    def generate_occurrences(self, from_date=None, to_date=None, count=None):
        tz = self.get_tz()

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

        start_local = self._ensure_aware_in_tz(self.start)
        end_local = self._ensure_aware_in_tz(self.end) if self.end else None
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

# Test models inheriting from the base classes for tests.py    
class MyEvent(BaseEvent):
    title = models.CharField(max_length=100)

    def __str__(self):
        return self.title

class MyOccurrence(BaseOccurrence):
    event = models.ForeignKey(
        MyEvent,
        on_delete=models.CASCADE,
        related_name="occurrences",
    )

class MyOtherOccurrence(BaseOccurrence):
     event = models.ForeignKey(
         MyEvent, 
         on_delete=models.CASCADE
    )
