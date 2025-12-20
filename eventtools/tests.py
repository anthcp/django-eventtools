import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase

from django.conf import settings
from django.core.exceptions import ValidationError
from .event import BaseEvent
from .occurrence import BaseOccurrence

class RecurringEventsTZTests(TestCase):
    def setUp(self):
        self.tz_utc = ZoneInfo("UTC")
        self.tz_ny = ZoneInfo("America/New_York")
    # old test setup
        self.christmas = BaseEvent.objects.create(title='Christmas')
        BaseOccurrence.objects.create(
            event=self.christmas,
            start=(2000, 12, 25, 7, 0),
            end=(2000, 12, 25, 22, 0),
            repeat="RRULE:FREQ=YEARLY")

        self.weekends = BaseEvent.objects.create(title='Weekends 9-10am')
        # Saturday
        BaseOccurrence.objects.create(
            event=self.weekends,
            start=(2015, 1, 3, 9, 0),
            end=(2015, 1, 3, 10, 0),
            repeat="RRULE:FREQ=WEEKLY")
        # Sunday
        BaseOccurrence.objects.create(
            event=self.weekends,
            start=(2015, 1, 4, 9, 0),
            end=(2015, 1, 4, 10, 0),
            repeat="RRULE:FREQ=WEEKLY")

        self.daily = BaseEvent.objects.create(title='Daily 7am')
        BaseOccurrence.objects.create(
            event=self.daily,
            start=(2015, 1, 1, 7, 0),
            end=None,
            repeat="RRULE:FREQ=DAILY")

        self.past = BaseEvent.objects.create(title='Past event')
        BaseOccurrence.objects.create(
            event=self.past,
            start=(2014, 1, 1, 7, 0),
            end=(2014, 1, 1, 8, 0))

        self.future = BaseEvent.objects.create(title='Future event')
        BaseOccurrence.objects.create(
            event=self.future,
            start=(2016, 1, 1, 7, 0),
            end=(2016, 1, 1, 8, 0))

        self.monthly = BaseEvent.objects.create(title='Monthly until Dec 2017')
        BaseOccurrence.objects.create(
            event=self.monthly,
            start=(2016, 1, 1, 7, 0),
            end=(2016, 1, 1, 8, 0),
            repeat="RRULE:FREQ=MONTHLY",
            repeat_until=(2017, 12, 31))

        # fake "today" so tests always work
        self.today = datetime.datetime(2015, 6, 1)
        self.first_of_year = datetime.datetime(2015, 1, 1)
        self.last_of_year = datetime.datetime(2015, 12, 31)


    def test_one_off_occurrence(self):
        timezone = "UTC"
        event = BaseEvent(name="One-off", title="One-off", timezone=timezone,)
        event.save()

        occ = BaseOccurrence(
            event=event,
            start=(2025, 12, 16, 10, 0), # can use a tuple
            end=(2025, 12, 16, 11, 0),
        )
        print(f"\nCreated occurrence: {occ.start} to {occ.end}, tz={event.timezone}")
        occ.save()

        occs = event.all_occurrences(
            from_date=(2025, 12, 1),
            to_date=(2026, 1, 1),
        )
        print(f"Occurrences found: {len(occs)}")
        
        self.assertEqual(len(occs), 1)
        start, end, occ_obj = occs[0]

        self.assertEqual(start, occ.start)
        self.assertEqual(end, occ.end)
        self.assertEqual(occ_obj.pk, occ.pk)
        self.assertIsNotNone(start.tzinfo)

    def test_weekly_recurrence_count(self):
        event = BaseEvent(name="Weekly", title="Weekly", timezone="UTC",)
        event.save()

        occ = BaseOccurrence(
            event=event,
            start=(2025, 12, 16, 10, 0),
            end=(2025, 12, 16, 11, 0),
            rrule="RRULE:FREQ=WEEKLY;COUNT=3",
            #timezone="UTC",
        )
        occ.save()

        occs = event.all_occurrences(
            from_date=(2025, 12, 1),
            to_date=(2026, 2, 1),
        )

        self.assertEqual(len(occs), 3)

        s0, s1, s2 = [o[0] for o in occs]
        self.assertEqual(s1 - s0, datetime.timedelta(days=7))
        self.assertEqual(s2 - s1, datetime.timedelta(days=7))

        for start, end, _ in occs:
            self.assertEqual(end - start, datetime.timedelta(hours=1))

    def test_next_and_first_occurrence(self):
        timezone = "UTC"
        event = BaseEvent(name="Daily", title="Daily", timezone=timezone,)
        event.save()

        occ = BaseOccurrence(
            event=event,
            start=(2025, 12, 16, 10, 0),
            end=(2025, 12, 16, 11, 0),
            rrule="RRULE:FREQ=DAILY;COUNT=5",
            #timezone="UTC",
        )
        occ.save()

        first = event.first_occurrence()
        self.assertIsNotNone(first)

        first_start, first_end, _ = first
        self.assertEqual(first_start, datetime.datetime(2025, 12, 16, 10, 0, tzinfo=ZoneInfo(timezone)))
        self.assertEqual(first_end - first_start, datetime.timedelta(hours=1))

        nxt = event.next_occurrence(
            from_date=(2025, 12, 18, 0, 0)
        )
        self.assertIsNotNone(nxt)

        next_start, _, _ = nxt
        self.assertEqual(next_start,datetime.datetime(2025, 12, 18, 10, 0, tzinfo=ZoneInfo(timezone)))

    def test_exdates_excluded(self):
        event = BaseEvent(name="Exclude", title="Exclude", timezone="UTC",)
        event.save()

        occ = BaseOccurrence(
            event=event,
            start=(2025, 12, 16, 10, 0),
            end=(2025, 12, 16, 11, 0),
            rrule="RRULE:FREQ=WEEKLY;COUNT=3",
            #timezone="UTC",
            exdates_json=["2025-12-23T10:00:00+00:00"],
        )
        occ.save()

        occs = event.all_occurrences(
            from_date=(2025, 12, 1),
            to_date=(2026, 1, 31),
        )

        starts = [o[0] for o in occs]

        self.assertEqual(len(starts), 2)
        self.assertNotIn((2025, 12, 23, 10, 0), starts)

    def test_rdates_included(self):
        timezone = "UTC"
        event = BaseEvent(name="Include", title="Include", timezone=timezone ,)
        event.save()

        occ = BaseOccurrence(
            event=event,
            start=(2025, 12, 16, 10, 0),
            end=(2025, 12, 16, 11, 0),
            rrule="RRULE:FREQ=WEEKLY;COUNT=2",
            #timezone="UTC",
            rdates_json=["2025-12-20T10:00:00+00:00"],
        )
        occ.save()

        occs = event.all_occurrences(
            from_date=(2025, 12, 1),
            to_date=(2026, 1, 10),
        )

        starts = [o[0] for o in occs]

        self.assertEqual(len(starts), 3)
        self.assertIn(datetime.datetime(2025, 12, 16, 10, 0, tzinfo=ZoneInfo(timezone)), starts)
        self.assertIn(datetime.datetime(2025, 12, 20, 10, 0, tzinfo=ZoneInfo(timezone)), starts)
        self.assertIn(datetime.datetime(2025, 12, 23, 10, 0, tzinfo=ZoneInfo(timezone)), starts)

    def test_save_localizes_naive_start_end(self):
        event = BaseEvent.objects.create(name="T", title="T", timezone="America/New_York",)
        occ = BaseOccurrence(
            event=event,
            #timezone="America/New_York",
            start=(2025, 12, 16, 10, 0, 0),  # naive
            end=(2025, 12, 16, 11, 0, 0),    # naive
        )
        occ.save()
        self.assertIsNotNone(occ.start.tzinfo)
        self.assertEqual(getattr(occ.start.tzinfo, "key", None) or occ.start.tzinfo.zone, "America/New_York")
        self.assertEqual(occ.start.hour, 10)
        self.assertEqual(occ.end.hour, 11)

# old tests
    def test_occurrence_validation(self):
        timezone = "UTC"
        event = BaseEvent(name="Validate", title="Validate", timezone=timezone ,)
        with self.assertRaises(ValidationError):
            BaseOccurrence(
                event=event,
                start=(2016, 1, 1, 7, 0),
                end=(2016, 1, 1, 6, 0),
            ).clean()

        with self.assertRaises(ValidationError):
            BaseOccurrence(
                event=event,
                start=datetime.datetime(2016, 1, 1, 7, 0),
                repeat_until=datetime.datetime(2017, 12, 31),
            ).clean()

        with self.assertRaises(ValidationError):
            BaseOccurrence(
                event=event,
                start=datetime.datetime(2016, 1, 1, 7, 0),
                repeat="RRULE:FREQ=MONTHLY",
                repeat_until=datetime.datetime(2015, 12, 31),
            ).clean()

    # def test_single_occurrence(self):
    #     timezone = "UTC"
    #     occ = self.christmas.get_related_occurrences().get()
    #     # using date() arguments
    #     dates = list(occ.all_occurrences(
    #         from_date=date(2015, 12, 1),
    #         to_date=date(2015, 12, 31),))
    #     self.assertEqual(len(dates), 1)

    #     # check it works as expected when from/to equal the occurrence date
    #     dates = list(occ.all_occurrences(
    #         from_date=date(2015, 12, 25),
    #         to_date=date(2015, 12, 25), ))
    #     self.assertEqual(len(dates), 1)

    #     # using datetime() arguments
    #     dates = list(occ.all_occurrences(
    #         from_date=datetime(2015, 12, 25, 6, 0, 0),
    #         to_date=datetime(2015, 12, 25, 23, 0, 0), ))
    #     self.assertEqual(len(dates), 1)

    #     # using tz-aware datetime() arguments, if appropriate
    #     if settings.USE_TZ:
    #         tz = get_default_timezone()
    #         dates = list(occ.all_occurrences(
    #             from_date=datetime(2015, 12, 25, 6, 0, 0, 0, tz),
    #             to_date=datetime(2015, 12, 25, 23, 0, 0, 0, tz), ))
    #         self.assertEqual(len(dates), 1)

    #     # date range intersecting with occurrence time
    #     dates = list(occ.all_occurrences(
    #         from_date=datetime(2015, 12, 25, 10, 0, 0),
    #         to_date=datetime(2015, 12, 25, 23, 0, 0), ))
    #     self.assertEqual(len(dates), 1)
    #     dates = list(occ.all_occurrences(
    #         from_date=datetime(2015, 12, 25, 6, 0, 0),
    #         to_date=datetime(2015, 12, 25, 10, 0, 0), ))
    #     self.assertEqual(len(dates), 1)

    #     # date range within occurrence time
    #     dates = list(occ.all_occurrences(
    #         from_date=datetime(2015, 12, 25, 12, 0, 0),
    #         to_date=datetime(2015, 12, 25, 13, 0, 0), ))
    #     self.assertEqual(len(dates), 1)

    #     # date range outside occurrence time
    #     dates = list(occ.all_occurrences(
    #         from_date=datetime(2015, 12, 24, 12, 0, 0),
    #         to_date=datetime(2015, 12, 26, 13, 0, 0), ))
    #     self.assertEqual(len(dates), 1)

    #     # date range before occurrence time
    #     dates = list(occ.all_occurrences(
    #         from_date=datetime(2015, 12, 24, 12, 0, 0),
    #         to_date=datetime(2015, 12, 24, 13, 0, 0), ))
    #     self.assertEqual(len(dates), 0)

    #     # date range after occurrence time
    #     dates = list(occ.all_occurrences(
    #         from_date=datetime(2015, 12, 25, 23, 0, 0),
    #         to_date=datetime(2015, 12, 25, 23, 30, 0), ))
    #     self.assertEqual(len(dates), 0)

    #     # check next_occurence method for non-repeating occurrences
    #     occ = self.past.get_related_occurrences().get() \
    #               .next_occurrence(from_date=self.today)
    #     self.assertEqual(occ, None)

    #     occ = self.future.get_related_occurrences().get() \
    #               .next_occurrence(from_date=self.today)
    #     self.assertEqual(occ[0].timetuple()[:5],
    #                      datetime(2016, 1, 1, 7, 0).timetuple()[:5])

    #     # and for repeating
    #     occ = self.daily.get_related_occurrences().get() \
    #               .next_occurrence(from_date=self.today)
    #     self.assertEqual(occ[0].date(), self.today)

    #     # test next_occurrence for querysets
    #     occ = self.daily.get_related_occurrences().all() \
    #               .next_occurrence(from_date=self.today)
    #     self.assertEqual(occ[0].date(), self.today)       