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


from .event import BaseEvent
from .occurrence import BaseOccurrence
from .query import OccurrenceMixin








