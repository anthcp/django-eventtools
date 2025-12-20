import datetime
from django.db import models
from django.utils import timezone as dj_timezone


class BaseEvent(models.Model):
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=100)
    timezone = models.CharField(max_length=63, default="UTC")

    #objects = EventManager()

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
