from django.db import models
from django.utils import timezone as dj_timezone
from django.db.models import Q, Case, When, Value
from django.core.exceptions import ValidationError
from dateutil.parser import isoparse  # prefer isoparse for ISO strings
from django.utils.translation import gettext_lazy as _
from dateutil.rrule import rrulestr, rruleset

import pendulum
from .utils import as_datetime, tzDateFactory
from .models import ChoiceTextField, REPEAT_CHOICES
from .event import BaseEvent
from .query import OccurrenceQuerySet

class BaseOccurrence(models.Model):
    event = models.ForeignKey(BaseEvent, on_delete=models.CASCADE, related_name="occurrences")
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)
    rrule = models.TextField(blank=True, null=True)
    #timezone = models.CharField(max_length=63, default="UTC")
    exdates_json = models.JSONField(default=list, blank=True)
    rdates_json = models.JSONField(default=list, blank=True)
    repeat_until = models.DateField(null=True, blank=True, verbose_name=_('repeat_until'))

    repeat = ChoiceTextField(
        choices=REPEAT_CHOICES, default='', blank=True,
        verbose_name=_('repeat'))
    
    objects = OccurrenceQuerySet.as_manager()

    @property
    def tzDateConv(self):
        return tzDateFactory(self.event.timezone)

    def __str__(self):
        return f"{self.event.name} occurrence starting {self.start}"


    def save(self, *args, **kwargs):
        # dates are converted just before save to standard tz format
        if self.start:
            self.start = self.tzDateConv.aware(self.start)
        if self.end:
            self.end = self.tzDateConv.aware(self.end)
        if self.repeat_until:
            self.repeat_until = self.tzDateConv.aware(self.repeat_until)    
        super().save(*args, **kwargs)
        return


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
        if self.repeat_until:
            self.repeat_until = self.tzDateConv.aware(self.repeat_until)

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
        
        if self.repeat_until and not self.repeat:
            msg = u"Select a repeat interval, or remove the " \
                  u"'repeat until' date"
            raise ValidationError(msg)

        if self.start and self.repeat_until and \
           self.repeat_until < self.start:
            msg = u"'Repeat until' cannot be before the first occurrence"
            raise ValidationError(msg)
        
        return

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
