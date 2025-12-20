from django.db import models
from django.utils import timezone as dj_timezone
from django.core.exceptions import ValidationError
from dateutil.rrule import rrulestr, rruleset

import pendulum
from .utils import as_datetime, tzDateFactory


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