# recurring_events_tz/models.py
# A Django app for handling timezone-aware recurring and one-off events.
# Replaces django-eventtools with similar model structure and queryset helpers.
# Dependencies: pip install python-dateutil
# Uses zoneinfo for timezones (Python 3.9+), Django's JSONField for exdates/rdates.

import datetime
import json
from zoneinfo import ZoneInfo

from django.db import models
from django.utils import timezone as dj_timezone
from dateutil.rrule import rrulestr, rruleset
from dateutil.parser import parse as date_parse


class BaseModel(models.Model):
    """Abstract model providing common occurrence-related functionality. """

    class Meta:
        abstract = True

class BaseEvent(BaseModel):
#class Event(models.Model):
    """
    Base event model. Extend this for your custom fields (e.g., title, description).
    """
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    def all_occurrences(self, from_date=None, to_date=None, count=None):
        """
        Generator yielding (start, end, occurrence) for all occurrences of this event.
        """
        return self.occurrences.all_occurrences(from_date, to_date, count)

    def next_occurrence(self, from_date=None):
        """
        Get the next occurrence after from_date.
        """
        occs = list(self.all_occurrences(from_date=from_date, count=1))
        return occs[0] if occs else None

    def first_occurrence(self):
        """
        Get the first occurrence.
        """
        return self.next_occurrence(from_date=datetime.datetime.min.replace(tzinfo=dj_timezone.utc))

class OccurrenceQuerySet(models.QuerySet):
    def all_occurrences(self, from_date=None, to_date=None, count=None):
        """
        Generate occurrences for the queryset.
        :return: list of (start, end, occurrence) tuples
        """
        if from_date is None:
            from_date = dj_timezone.now()
        
        all_occs = []
        for occ in self:
            all_occs.extend(occ.generate_occurrences(from_date, to_date, count))
            if count and len(all_occs) >= count:
                all_occs = all_occs[:count]
                break
        
        all_occs.sort(key=lambda x: x[0])
        return all_occs

    def for_period(self, from_date, to_date, exact=False):
        """
        Filter occurrences that fall within the period.
        If exact=True, generate and filter precisely (slower for large sets).
        """
        if exact:
            # Generate all and filter (inefficient for many events)
            occs = self.all_occurrences(from_date=from_date, to_date=to_date)
            return [o[2] for o in occs]  # Return occurrence instances
        else:
            # Approximate filter based on start/end (won't catch all recurrences)
            return self.filter(
                models.Q(start__lt=to_date) & (models.Q(end__isnull=True) | models.Q(end__gt=from_date))
            )

    def sort_by_next(self, from_date=None):
        """
        Sort by next occurrence start time.
        """
        if from_date is None:
            from_date = dj_timezone.now()
        
        occs_with_next = []
        for occ in self:
            next_start = occ.next_start(from_date)
            if next_start:
                occs_with_next.append((next_start, occ))
        
        occs_with_next.sort(key=lambda x: x[0])
        return [o[1] for o in occs_with_next]

class BaseOccurrence(BaseModel):
#class Occurrence(models.Model):
    """
    Occurrence model for events. Can be one-off or recurring.
    """
    event = models.ForeignKey(BaseEvent, on_delete=models.CASCADE, related_name='occurrences')
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)  # Optional for all-day or open-ended
    rrule = models.TextField(blank=True, null=True)  # RRULE string
    timezone = models.CharField(max_length=63, default='UTC')  # e.g., 'America/New_York'
    exdates_json = models.JSONField(default=list, blank=True)  # List of ISO strings
    rdates_json = models.JSONField(default=list, blank=True)  # List of ISO strings

    objects = OccurrenceQuerySet.as_manager()

    def __str__(self):
        return f"{self.event.name} occurrence starting {self.start}"

    def save(self, *args, **kwargs):
        # Ensure timezone awareness
        if self.start.tzinfo is None:
            self.start = self.start.replace(tzinfo=self.get_tz())
        if self.end and self.end.tzinfo is None:
            self.end = self.end.replace(tzinfo=self.get_tz())
        super().save(*args, **kwargs)

    def get_tz(self):
        return ZoneInfo(self.timezone)

    def parse_dates(self, dates_json):
        parsed = []
        for d_str in dates_json:
            d = date_parse(d_str)
            if d.tzinfo is None:
                d = d.replace(tzinfo=self.get_tz())
            else:
                d = d.astimezone(self.get_tz())
            parsed.append(d)
        return parsed

    def generate_occurrences(self, from_date=None, to_date=None, count=None):
        if from_date is None:
            from_date = dj_timezone.now()
        if from_date.tzinfo is None:
            from_date = from_date.replace(tzinfo=self.get_tz())
        else:
            from_date = from_date.astimezone(self.get_tz())

        if to_date:
            if to_date.tzinfo is None:
                to_date = to_date.replace(tzinfo=self.get_tz())
            else:
                to_date = to_date.astimezone(self.get_tz())

        duration = self.end - self.start if self.end else datetime.timedelta(0)
        exdates = self.parse_dates(self.exdates_json)
        rdates = self.parse_dates(self.rdates_json)

        rset = rruleset()
        if self.rrule:
            main_rrule = rrulestr(self.rrule, dtstart=self.start)
            rset.rrule(main_rrule)
        else:
            if self.start not in exdates:
                rset.rdate(self.start)

        for rd in rdates:
            rset.rdate(rd)

        for ex in exdates:
            rset.exdate(ex)

        occurrences = []
        next_start = rset.after(from_date, inc=True)
        while next_start:
            if to_date and next_start >= to_date:
                break
            next_end = next_start + duration if duration else None
            occurrences.append((next_start, next_end, self))
            if count and len(occurrences) >= count:
                break
            next_start = rset.after(next_start, inc=False)

        return occurrences

    def next_start(self, from_date=None):
        occs = self.generate_occurrences(from_date=from_date, count=1)
        return occs[0][0] if occs else None

# Example usage in a Django view or shell:
# from recurring_events_tz.models import BaseEvent, BaseOccurrence
# from datetime import datetime
#
# event = BaseEvent.objects.create(name="Weekly Meeting")
# BaseOccurrence.objects.create(
#     event=event,
#     start=datetime(2025, 12, 16, 10, 0),
#     end=datetime(2025, 12, 16, 11, 0),
#     rrule="RRULE:FREQ=WEEKLY;COUNT=5",
#     timezone="America/New_York",
#     exdates_json=["2025-12-23T10:00:00"]
# )
#
# # Get all occurrences
# for start, end, occ in event.all_occurrences():
#     print(f"{event.name}: {start} to {end}")
#
# # Queryset examples
# occ_qs = BaseOccurrence.objects.all()
# occs_in_period = occ_qs.for_period(from_date=datetime(2025, 12, 1), to_date=datetime(2026, 1, 1))
# sorted_occs = occ_qs.sort_by_next()