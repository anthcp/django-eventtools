import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase
from .models import MyEvent, MyOccurrence

from django.conf import settings


class RecurringEventsTZTests(TestCase):
    def setUp(self):
        self.tz_utc = ZoneInfo("UTC")
        self.tz_ny = ZoneInfo("America/New_York")

    # def aware(self, y, m, d, hh=0, mm=0, ss=0, tz=None):
    #     tz = tz or self.tz_utc
    #     return datetime.datetime(y, m, d, hh, mm, ss, tzinfo=tz)

    def test_one_off_occurrence(self):
        event = MyEvent(name="One-off", title="One-off", timezone="UTC",)
        event.save()

        occ = MyOccurrence(
            event=event,
            start=(2025, 12, 16, 10, 0), # can use a tuple
            end=(2025, 12, 16, 11, 0),
            #timezone="UTC",
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
        event = MyEvent(name="Weekly", title="Weekly", timezone="UTC",)
        event.save()

        occ = MyOccurrence(
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
        event = MyEvent(name="Daily", title="Daily", timezone=timezone,)
        event.save()

        occ = MyOccurrence(
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
        event = MyEvent(name="Exclude", title="Exclude", timezone="UTC",)
        event.save()

        occ = MyOccurrence(
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
        event = MyEvent(name="Include", title="Include", timezone=timezone ,)
        event.save()

        occ = MyOccurrence(
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

    # def test_dst_wall_time_stability(self):
    #     """
    #     Weekly 10:00 America/New_York should stay 10:00 local across DST.
    #     """
    #     event = MyEvent(name="DST", title="DST")
    #     event
    def test_save_localizes_naive_start_end(self):
        event = MyEvent.objects.create(name="T", title="T", timezone="America/New_York",)
        occ = MyOccurrence(
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