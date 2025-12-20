import datetime
from django.db import models
from django.utils import timezone as dj_timezone

from.query import EventQuerySet, OccurrenceMixin


class BaseModel(models.Model, OccurrenceMixin):
    """Abstract model providing common occurrence-related functionality. """

    class Meta:
        abstract = True


class EventManager(models.Manager.from_queryset(EventQuerySet)):
    use_for_related_fields = True


class BaseEvent(BaseModel):
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=100)
    timezone = models.CharField(max_length=63, default="UTC")

    objects = EventManager()

    @classmethod
    def get_occurrence_relation(cls):
        """Get the occurrence relation for this class - use the first if
        there's more than one. """
        # get all related occurrence fields
        relations = [rel for rel in cls._meta.get_fields()
                    if isinstance(rel, models.ManyToOneRel) and
                    hasattr(rel.related_model, '_is_occurrence')]
        # assume there's only one
        return relations[0]
    
    @classmethod
    def occurrence_filter_prefix(cls):
        rel = cls.get_occurrence_relation()
        return rel.name
    
    def get_related_occurrences(self):
        rel = self.get_occurrence_relation()
        return getattr(self, rel.get_accessor_name()).all()

    def __str__(self):
        return self.name

    # def all_occurrences(self, from_date=None, to_date=None, count=None):
    #     return self.occurrences.all_occurrences(from_date, to_date, count, event_tz=self.timezone )
    def all_occurrences(self, from_date=None, to_date=None, limit=None):
        """Return a generator yielding a (start, end) tuple for all dates
           for this event, taking repetition into account. """
        return self.get_related_occurrences().all_occurrences(
            from_date, to_date, limit=limit)

    def next_occurrence(self, from_date=None):
        occs = self.all_occurrences(from_date=from_date, count=1)
        return occs[0] if occs else None

    def first_occurrence(self):
        # avoid datetime.min (can be problematic); use "now minus a lot"
        return self.next_occurrence(from_date=dj_timezone.now() - datetime.timedelta(days=365 * 50))
    
    class Meta:
        abstract = False
