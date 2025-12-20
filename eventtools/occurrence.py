import datetime
from django.db import models
from django.utils import timezone as dj_timezone
from django.db.models import Q, Case, When, Value
from django.core.exceptions import ValidationError
from dateutil.parser import isoparse  # prefer isoparse for ISO strings
from django.utils.translation import gettext_lazy as _
from dateutil.rrule import rrulestr, rruleset
from django.conf import settings
from dateutil import rrule

import pendulum
from .utils import as_datetime, tzDateFactory
#from .models import REPEAT_CHOICES
from .event import BaseEvent
from .query import OccurrenceQuerySet

# set EVENTTOOLS_REPEAT_CHOICES = None to make this a plain textfield
REPEAT_CHOICES = getattr(settings, 'EVENTTOOLS_REPEAT_CHOICES', (
    ("RRULE:FREQ=DAILY", 'Daily'),
    ("RRULE:FREQ=WEEKLY", 'Weekly'),
    ("RRULE:FREQ=MONTHLY", 'Monthly'),
    ("RRULE:FREQ=YEARLY", 'Yearly'),
))
REPEAT_MAX = 200

class ChoiceTextField(models.TextField):
    """Textfield which uses a Select widget if it has choices specified. """
    def formfield(self, **kwargs):
        if self.choices:
            # this overrides the TextField's preference for a Textarea widget,
            # allowing the ModelForm to decide which field to use
            kwargs['widget'] = None
        return super(ChoiceTextField, self).formfield(**kwargs)

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

class OccurrenceManager(models.Manager.from_queryset(OccurrenceQuerySet)):
    use_for_related_fields = True

    def migrate_integer_repeat(self):
        self.update(repeat=Case(
            When(repeat=rrule.YEARLY,
                 then=Value("RRULE:FREQ=YEARLY")),
            When(repeat=rrule.MONTHLY,
                 then=Value("RRULE:FREQ=MONTHLY")),
            When(repeat=rrule.WEEKLY,
                 then=Value("RRULE:FREQ=WEEKLY")),
            When(repeat=rrule.DAILY,
                 then=Value("RRULE:FREQ=DAILY")),
            default=Value(""),
        ))
