from django.db import models

from eventtools.models import BaseEvent, BaseOccurrence

class MyEvent(BaseEvent):
    title = models.CharField(max_length=100)

    def __str__(self):
        return self.title


class MyOccurrence(BaseOccurrence):
    event = models.ForeignKey(MyEvent, on_delete=models.CASCADE)


class MyOtherOccurrence(BaseOccurrence):
    event = models.ForeignKey(MyEvent, on_delete=models.CASCADE)
