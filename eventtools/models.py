import datetime
from zoneinfo import ZoneInfo

from django.db import models
from django.utils import timezone as dj_timezone
from dateutil.rrule import rrulestr, rruleset
from dateutil.parser import isoparse  # prefer isoparse for ISO strings
from django.conf import settings
import pendulum
from pendulum.tz.timezone import Timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

#from .utils import tzDateFactory
from .event import BaseEvent


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



