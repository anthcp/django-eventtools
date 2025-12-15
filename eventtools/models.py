# -*- coding: utf-8 -*-

from dateutil import rrule
from datetime import date, datetime, timedelta, time
from django.core.exceptions import ImproperlyConfigured

from django.conf import settings
from django.db import models
from django.db.models import Q, Case, When, Value
from django.core.exceptions import ValidationError

#from django.utils.timezone import make_aware, is_naive, make_naive, is_aware
from django.utils import timezone
from django.utils.timezone import make_aware, is_naive, is_aware
from timezone_field import TimeZoneField  
from django.utils.translation import gettext_lazy as _
from zoneinfo import ZoneInfo
from six import python_2_unicode_compatible


# set EVENTTOOLS_REPEAT_CHOICES = None to make this a plain textfield
REPEAT_CHOICES = getattr(settings, 'EVENTTOOLS_REPEAT_CHOICES', (
    ("RRULE:FREQ=DAILY", 'Daily'),
    ("RRULE:FREQ=WEEKLY", 'Weekly'),
    ("RRULE:FREQ=MONTHLY", 'Monthly'),
    ("RRULE:FREQ=YEARLY", 'Yearly'),
    ("RRULE:FREQ=MONTHLY;BYDAY=SU;BYSETPOS=-1", "Last Sunday of the month"),
))
REPEAT_MAX = 200

utc_tz = ZoneInfo('UTC')

def max_future_date():
    return datetime(date.today().year + 10, 1, 1, 0, 0)


def first_item(gen):
    try:
        return next(gen)
    except StopIteration:
        return None


# def default_aware(dt):
#     """Convert a naive datetime argument to a tz-aware datetime, if tz support
#        is enabled. """
#     if settings.USE_TZ and timezone.is_naive(dt):
#         # Use the current (or default) Django timezone, which is ZoneInfo in modern Django
#         return timezone.make_aware(dt, timezone.get_current_timezone())
#     return dt

def default_aware(dt, event_tz):
    if dt is None:
        return None
    if timezone.is_aware(dt):
        return dt
    return timezone.make_aware(dt, event_tz)

# def default_naive(dt):
#     """Convert an aware datetime argument to naive, if tz support
#        is enabled. """
#     if settings.USE_TZ and timezone.is_aware(dt):
#         # Explicit tz avoids pytz/zoneinfo weirdness and Django version differences
#         return timezone.make_naive(dt, timezone.get_current_timezone())
#     return dt


# def as_datetime(d, end=False):
#     """Normalise a date/datetime argument to a datetime for use in filters

#     If a date is passed, it will be converted to a datetime with the time set
#     to 0:00, or 23:59:59 if end is True."""

#     if type(d) is date:
#         date_args = tuple(d.timetuple())[:3]
#         if end:
#             time_args = (23, 59, 59)
#         else:
#             time_args = (0, 0, 0)
#         new_value = datetime(*(date_args + time_args))
#         return default_aware(new_value)
#     # otherwise assume it's a datetime
#     return default_aware(d)

def as_datetime(d, tz, end=False, *, allow_naive=False):
    """
    Normalize a date/datetime to an aware datetime in the provided tz.

    - date -> start/end of day in tz
    - aware datetime -> converted to tz
    - naive datetime -> raises unless allow_naive=True, then assumes tz
    """
    if d is None:
        return None

    if isinstance(d, date) and not isinstance(d, datetime):
        t = time(23, 59, 59) if end else time(0, 0, 0)
        dt = datetime.combine(d, t)
        return timezone.make_aware(dt, tz)

    # datetime
    if timezone.is_naive(d):
        if not allow_naive:
            raise ValueError("Naive datetime passed to as_datetime(); supply tz-aware datetime")
        d = timezone.make_aware(d, tz)

    return d.astimezone(tz)

def as_datetime_qs(d, end=False):
    """
    For QuerySet filtering only.

    Converts date/datetime to an aware datetime using Django's default timezone.
    This is an approximation layer (events may have their own tz).
    """
    if d is None:
        return None

    if isinstance(d, date) and not isinstance(d, datetime):
        if end:
            dt = datetime(d.year, d.month, d.day, 23, 59, 59)
        else:
            dt = datetime(d.year, d.month, d.day, 0, 0, 0)
        return timezone.make_aware(dt, timezone.get_default_timezone())

    # datetime
    if timezone.is_naive(d):
        return timezone.make_aware(d, timezone.get_default_timezone())
    return d

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

    from_date = as_datetime_qs(from_date)
    return qs.filter(
        q_func(end__isnull=False, end__gte=from_date) |
        q_func(start__gte=from_date) |
        (~q_func(repeat='') & (q_func(repeat_until__gte=from_date) |
         q_func(repeat_until__isnull=True)))).distinct()


class OccurrenceMixin(object):
    """Class mixin providing common occurrence-related functionality. """

    def all_occurrences(self, from_date=None, to_date=None):
        raise NotImplementedError()

    def next_occurrence(self, from_date=None, to_date=None):
        """Return next occurrence as a (start, end) tuple for this instance,
           between from_date and to_date, taking repetition into account. """
        if not from_date:
            from_date = datetime.now()
        return first_item(
            self.all_occurrences(from_date=from_date, to_date=to_date))

    def first_occurrence(self):
        """Return first occurrence as a (start, end) tuple for this instance.
        """
        return first_item(self.all_occurrences())


class BaseQuerySet(models.QuerySet, OccurrenceMixin):
    """Base QuerySet for models which have occurrences. """

    def for_period(self, from_date=None, to_date=None, exact=False):
        # subclasses should implement this
        raise NotImplementedError()

    def sort_by_next(self, from_date=None):
        """Sort the queryset by next_occurrence.

        Note that this method necessarily returns a list, not a queryset. """

        def sort_key(obj):
            occ = obj.next_occurrence(from_date=from_date)
            return occ[0] if occ else None
        return sorted([e for e in self if sort_key(e)], key=sort_key)

    def all_occurrences(self, from_date=None, to_date=None, limit=None):
        """Return a generator yielding a (start, end) tuple for all occurrence
           dates in the queryset, taking repetition into account, up to a
           maximum limit if specified. """

        # winnow out events which are definitely invalid
        qs = self.for_period(from_date, to_date)

        return combine_occurrences(
            (obj.all_occurrences(from_date, to_date) for obj in qs), limit)


class BaseModel(models.Model, OccurrenceMixin):
    """Abstract model providing common occurrence-related functionality. """

    class Meta:
        abstract = True


class EventQuerySet(BaseQuerySet):
    """QuerySet for BaseEvent subclasses. """

    def for_period(self, from_date=None, to_date=None, exact=False):
        """Filter by the given dates, returning a queryset of Occurrence
           instances with occurrences falling within the range.

           Due to uncertainty with repetitions, from_date filtering is only an
           approximation. If exact results are needed, pass exact=True - this
           will use occurrences to exclude invalid results, but may be very
           slow, especially for large querysets. """

        filtered_qs = self
        prefix = self.model.occurrence_filter_prefix()

        def wrap_q(**kwargs):
            """Prepend the related model name to the filter keys. """

            return Q(**{'%s__%s' % (prefix, k): v for k, v in kwargs.items()})

        # to_date filtering is accurate
        if to_date:
            to_date = as_datetime_qs(to_date, True)
            filtered_qs = filtered_qs.filter(
                wrap_q(start__lte=to_date)).distinct()

        if from_date:
            # but from_date isn't, due to uncertainty with repetitions, so
            # just winnow down as much as possible via queryset filtering
            filtered_qs = filter_from(filtered_qs, from_date, wrap_q)

            # filter out invalid results if requested
            if exact:
                filtered_qs = filter_invalid(filtered_qs, from_date, to_date)

        return filtered_qs


class EventManager(models.Manager.from_queryset(EventQuerySet)):
    use_for_related_fields = True

def default_event_timezone():
    return settings.TIME_ZONE

def validate_timezone(value):
    try:
        ZoneInfo(value)
    except Exception:
        raise ValidationError(f"Invalid timezone: {value}")
    
class BaseEvent(BaseModel):
    """Abstract model providing occurrence-related methods for events.
       Subclasses should have a related BaseOccurrence subclass. """
    
    tz = models.CharField(
        max_length=64,
        default=default_event_timezone,
        help_text="IANA timezone, e.g. America/New_York",
        validators=[validate_timezone],
    )

    objects = EventManager()

    def set_timezone(self, new_tz: str, *, preserve_instant=False):
        """
        Change the event timezone.

        preserve_instant=False:
            Keep wall-clock times the same (10:00 stays 10:00).
            This is the default for recurring events.

        preserve_instant=True:
            Keep the absolute instant the same (UTC preserved).
        """
        old_tz = ZoneInfo(self.tz)
        new_tz = ZoneInfo(new_tz)

        for occ in self.get_related_occurrences():
            if preserve_instant:
                # Keep the instant; wall time may change
                occ.start = occ.start.astimezone(new_tz)
                if occ.end:
                    occ.end = occ.end.astimezone(new_tz)
            else:
                # Keep wall time; instant changes
                occ.start = occ.start.replace(tzinfo=new_tz)
                if occ.end:
                    occ.end = occ.end.replace(tzinfo=new_tz)

            occ.save(update_fields=["start", "end"])

        self.tz = str(new_tz)
        self.save(update_fields=["tz"])

    @classmethod
    def get_occurrence_relation(cls):
        """Get the occurrence relation for this class - use the first if
           there's more than one. """

        # get all related occurrence fields
        relations = [rel for rel in cls._meta.get_fields()
                     if isinstance(rel, models.ManyToOneRel) and
                     issubclass(rel.related_model, BaseOccurrence)]

        # assume there's only one
        return relations[0]

    @classmethod
    def occurrence_filter_prefix(cls):
        rel = cls.get_occurrence_relation()
        return rel.name

    def get_related_occurrences(self):
        rel = self.get_occurrence_relation()
        return getattr(self, rel.get_accessor_name()).all()

    def all_occurrences(self, from_date=None, to_date=None, limit=None):
        """Return a generator yielding a (start, end) tuple for all dates
           for this event, taking repetition into account. """

        return self.get_related_occurrences().all_occurrences(
            from_date, to_date, limit=limit)

    @classmethod
    def get_occurrence_relation(cls):
        occurrence_relation_name = None

    @classmethod
    def get_occurrence_relation(cls):
        # 1) If explicitly configured, use it.
        if cls.occurrence_relation_name:
            rel = cls._meta.get_field(cls.occurrence_relation_name)

            if not isinstance(rel, models.ManyToOneRel):
                raise ImproperlyConfigured(
                    f"{cls.__name__}.occurrence_relation_name must refer to a reverse FK "
                    f"(got {type(rel).__name__})"
                )

            if not issubclass(rel.related_model, BaseOccurrence):
                raise ImproperlyConfigured(
                    f"{cls.__name__}.{cls.occurrence_relation_name} does not point to a BaseOccurrence subclass"
                )
            return rel

        # 2) Otherwise auto-detect, but fail fast if ambiguous.
        relations = [
            rel for rel in cls._meta.get_fields()
            if isinstance(rel, models.ManyToOneRel)
            and issubclass(rel.related_model, BaseOccurrence)
        ]

        if not relations:
            raise ImproperlyConfigured(
                f"{cls.__name__} has no related BaseOccurrence models"
            )

        if len(relations) > 1:
            raise ImproperlyConfigured(
                f"{cls.__name__} has multiple occurrence relations; set occurrence_relation_name. "
                f"Found: {[r.name for r in relations]}"
            )

        return relations[0]
    
    class Meta:
        abstract = True
    

class OccurrenceQuerySet(BaseQuerySet):
    """QuerySet for BaseOccurrence subclasses. """

    def for_period(self, from_date=None, to_date=None, exact=False):
        """Filter by the given dates, returning a queryset of Occurrence
           instances with occurrences falling within the range.

           Due to uncertainty with repetitions, from_date filtering is only an
           approximation. If exact results are needed, pass exact=True - this
           will use occurrences to exclude invalid results, but may be very
           slow, especially for large querysets. """

        filtered_qs = self

        # to_date filtering is accurate
        if to_date:
            to_date = as_datetime_qs(to_date, True)
            filtered_qs = filtered_qs.filter(Q(start__lte=to_date)).distinct()

        if from_date:
            # but from_date isn't, due to uncertainty with repetitions, so
            # just winnow down as much as possible via queryset filtering
            filtered_qs = filter_from(filtered_qs, from_date)

            # filter out invalid results if requested
            if exact:
                filtered_qs = filter_invalid(filtered_qs, from_date, to_date)

        return filtered_qs


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


class ChoiceTextField(models.TextField):
    """Textfield which uses a Select widget if it has choices specified. """

    def formfield(self, **kwargs):
        if self.choices:
            # this overrides the TextField's preference for a Textarea widget,
            # allowing the ModelForm to decide which field to use
            kwargs['widget'] = None
        return super(ChoiceTextField, self).formfield(**kwargs)


@python_2_unicode_compatible
class BaseOccurrence(BaseModel):
    """Abstract model providing occurrence-related methods for occurrences.

    Subclasses will usually have a ForeignKey pointing to a BaseEvent subclass
    (commonly named `event`).
    """

    start = models.DateTimeField(db_index=True, verbose_name=_("start"))
    end = models.DateTimeField(db_index=True, null=True, blank=True, verbose_name=_("end"))

    repeat = ChoiceTextField(
        choices=REPEAT_CHOICES, default="", blank=True, verbose_name=_("repeat")
    )
    repeat_until = models.DateField(null=True, blank=True, verbose_name=_("repeat_until"))

    objects = OccurrenceManager()

    class Meta:
        ordering = ("start", "end")
        abstract = True

    def __str__(self):
        return "%s" % (self.start,)

    @property
    def occurrence_data(self):
        return self

    def clean(self):
        # Existing validation
        if self.start and self.end and self.start >= self.end:
            raise ValidationError("End must be after start")

        if self.repeat_until and not self.repeat:
            raise ValidationError("Select a repeat interval, or remove the 'repeat until' date")

        if self.start and self.repeat_until and self.repeat_until < self.start.date():
            raise ValidationError("'Repeat until' cannot be before the first occurrence")

        if settings.USE_TZ:
            # Require FK + event timezone
            if not getattr(self, "event_id", None):
                raise ValidationError("Occurrence must be attached to an event when USE_TZ=True")

            event_tz = ZoneInfo(self.event.tz)

            # Enforce awareness (strict policy)
            if self.start and timezone.is_naive(self.start):
                raise ValidationError("start must be timezone-aware")
            if self.end and timezone.is_naive(self.end):
                raise ValidationError("end must be timezone-aware")

            # Normalize into event tz (keeps semantics consistent)
            if self.start:
                self.start = self.start.astimezone(event_tz)
            if self.end:
                self.end = self.end.astimezone(event_tz)
        return

    def get_repeater(self):
        """Return an rruleset for this occurrence, evaluated in the event timezone."""
        if not self.repeat:
            return None

        event_tz = ZoneInfo(self.event.tz)
        dtstart_local = self.start.astimezone(event_tz)

        ruleset = rrule.rruleset()
        rule = rrule.rrulestr(self.repeat, dtstart=dtstart_local)
        ruleset.rrule(rule)
        return ruleset

    def all_occurrences(self, from_date=None, to_date=None, limit=REPEAT_MAX):
        """Yield (start, end, occurrence_data) tuples.
        All recurrence math is performed in the event timezone (event.tz) so that
        wall-clock time stays stable across DST.
        """
        if not self.start:
            return

        event_tz = ZoneInfo(self.event.tz)
        start_local = self.start.astimezone(event_tz)
        end_local = self.end.astimezone(event_tz) if self.end else None

        # Normalize window to event timezone
        if from_date is not None:
            if timezone.is_naive(from_date):
                raise ValueError("from_date must be timezone-aware")
            from_date = from_date.astimezone(event_tz)

        if to_date is not None:
            if timezone.is_naive(to_date):
                raise ValueError("to_date must be timezone-aware")
            to_date = to_date.astimezone(event_tz)

        # Non-repeating case
        if not self.repeat:
            if (from_date is None or start_local >= from_date or (end_local and end_local >= from_date)) and \
               (to_date is None or start_local <= to_date):
                yield (start_local, end_local, self.occurrence_data)
            return

        # Repeating case
        delta = (end_local - start_local) if end_local else timedelta(0)
        repeater = self.get_repeater()

        # Start from earliest relevant moment
        if from_date is None or from_date < start_local:
            from_date = start_local

        # Apply repeat_until bound (in event timezone)
        if self.repeat_until:
            until_dt = timezone.make_aware(
                datetime.combine(self.repeat_until, datetime.max.time()),
                event_tz,
            )
            if to_date is None or until_dt < to_date:
                to_date = until_dt

        # Account for intersection semantics (event overlaps from_date if it started earlier)
        cursor = from_date - delta

        count = 0
        while limit is None or count < limit:
            occ_start = repeater.after(cursor, inc=True)
            if occ_start is None:
                return
            if to_date is not None and occ_start > to_date:
                return

            occ_end = (occ_start + delta) if end_local else None
            yield (occ_start, occ_end, self.occurrence_data)

            count += 1
            cursor = occ_start + timedelta(microseconds=1)


def all_occurrences(self, from_date=None, to_date=None, limit=REPEAT_MAX):
    if not self.start:
        return

    event_tz = ZoneInfo(self.event.tz)

    # normalize from_date/to_date into event_tz
    if from_date is not None:
        if timezone.is_naive(from_date):
            raise ValueError("from_date must be timezone-aware")
        from_date = from_date.astimezone(event_tz)

    if to_date is not None:
        if timezone.is_naive(to_date):
            raise ValueError("to_date must be timezone-aware")
        to_date = to_date.astimezone(event_tz)

    start_local = self.start.astimezone(event_tz)
    end_local = self.end.astimezone(event_tz) if self.end else None

    if not self.repeat:
        if (from_date is None or start_local >= from_date or
            (end_local and end_local >= from_date)) and \
           (to_date is None or start_local <= to_date):
            yield (start_local, end_local, self.occurrence_data)
        return

    delta = (end_local - start_local) if end_local else timedelta(0)
    repeater = self.get_repeater()  # built with dtstart in event_tz

    # start from earliest relevant point
    if from_date is None or from_date < start_local:
        from_date = start_local

    # apply repeat_until bound (in event_tz)
    if self.repeat_until:
        until_dt = timezone.make_aware(
            datetime.combine(self.repeat_until, datetime.max.time()),
            event_tz
        )
        if to_date is None or until_dt < to_date:
            to_date = until_dt

    # account for duration intersection semantics
    from_date = from_date - delta

    count = 0
    cursor = from_date

    while limit is None or count < limit:
        occ_start = repeater.after(cursor, inc=True)
        if occ_start is None:
            return
        if to_date is not None and occ_start > to_date:
            return

        occ_end = occ_start + delta if end_local else None
        yield (occ_start, occ_end, self.occurrence_data)

        count += 1
        cursor = occ_start + timedelta(microseconds=1)



    # def get_repeater(self):
    #     """Get rruleset instance representing this occurrence's repetitions.
    #     Subclasses may override this method for custom repeat behaviour.
    #     """
    #     if not self.repeat:
    #         return None

    #     # Use aware dtstart (stored as UTC)
    #     dtstart = self.start  # aware UTC
    #     ruleset = rrule.rruleset()
    #     rule = rrule.rrulestr(self.repeat, dtstart=dtstart)
    #     ruleset.rrule(rule)
    #     return ruleset

    def get_repeater(self):
        if not self.repeat:
            return None
        # Build rules in the *local* timezone so wall time stays stable across DST
        event_tz = timezone.get_current_timezone()
        dtstart_local = timezone.localtime(self.start, event_tz)
        ruleset = rrule.rruleset()
        rule = rrule.rrulestr(self.repeat, dtstart=dtstart_local)
        ruleset.rrule(rule)
        return ruleset

    def localized_occurrences(self, from_date=None, to_date=None, limit=REPEAT_MAX):
        """Yield localized (start, end, data) in the event_timezone."""
        local_tz = self.event_timezone
        for start, end, data in self.all_occurrences(from_date, to_date, limit):
            local_start = start.astimezone(local_tz)
            local_end = end.astimezone(local_tz) if end else None
            yield (local_start, local_end, data)

    @property
    def occurrence_data(self):
        return self

    class Meta:
        ordering = ('start', 'end')
        abstract = True

    def __str__(self):
        return u"%s" % (self.start)
