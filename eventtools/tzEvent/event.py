import pendulum
import datetime as _dt
from datetime import datetime as py_datetime
from zoneinfo import ZoneInfo

class Event(pendulum.DateTime):
    _forced_tz = "UTC"
    _forced_tzinfo = ZoneInfo("UTC")

    def __new__(cls, *args, **kwargs):
        # No guard: let Pendulum and internal ops construct freely
        return super().__new__(cls, *args, **kwargs)


    @classmethod
    def create_context(cls, timezone_name):
        name = pendulum.timezone(timezone_name).name
        return type(
            f"Event_{name.replace('/', '_')}",
            (cls,),
            {"_forced_tz": name},
        )

    @classmethod
    def datetime(cls, year, month, day, hour=0, minute=0, second=0):
        # Use Pendulum to construct in the forced tz
        p = pendulum.datetime(year, month, day, hour, minute, second, tz=cls._forced_tz)
        # Let Pendulum’s machinery handle construction; no custom __new__ needed
        return cls.instance(p)

    @classmethod
    def now(cls):
        return cls.from_any_datetime(pendulum.now(cls._forced_tz))
    

    @classmethod
    def from_isoformat(cls, s: str, *, assume_tz: str | None = None):
        """
        Parse ISO string. If it has no offset/tz, assume assume_tz or forced_tz.
        """
        p = pendulum.parse(s, strict=False)
        if p.tzinfo is None:
            p = p.replace(tzinfo=pendulum.timezone(assume_tz or cls._forced_tz))
        return cls.from_any_datetime(p)

    # ---------- Semantics helpers ----------

    def is_same_moment(self, other) -> bool:
        """
        True if same absolute instant (including microseconds).
        """
        if isinstance(other, py_datetime):
            other_p = pendulum.instance(other) if other.tzinfo else pendulum.datetime(
                other.year, other.month, other.day,
                other.hour, other.minute, other.second, other.microsecond,
                tz=self._forced_tz
            )
        elif isinstance(other, pendulum.DateTime):
            other_p = other
        else:
            return False

        # Equality on aware datetimes compares the instant (not the display tz)
        return self.in_timezone("UTC") == other_p.in_timezone("UTC")

    def convert(self, target_event_class):
        """
        Rebind this instant into another Event context class (normalize to its forced tz).
        """
        return target_event_class.from_any_datetime(self.in_timezone(target_event_class._forced_tz))

    @classmethod
    def date_at(cls, year, month, day):
        """
        Create an Event at midnight in the event's forced timezone.
        """
        p_obj = pendulum.datetime(year, month, day, 0, 0, 0, tz=cls._forced_tz)
        return cls.from_any_datetime(p_obj)
    
  
    @classmethod
    def from_any_datetime(cls, obj):
        import datetime as dt
        if isinstance(obj, dt.datetime) and not isinstance(obj, pendulum.DateTime):
            obj = pendulum.instance(obj)
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=pendulum.timezone(cls._forced_tz))
        obj = obj.in_timezone(cls._forced_tz)
        return cls.instance(obj)

