import datetime
from django.db import models
from django.utils import timezone as dj_timezone
from django.core.exceptions import ValidationError
from dateutil.rrule import rrulestr, rruleset

import pendulum
from .utils import as_datetime, tzDateFactory, combine_occurrences, filter_invalid, filter_from, first_item, combine_occurrences


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
            to_date = as_datetime(to_date, True)
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