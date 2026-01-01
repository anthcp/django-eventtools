import pendulum
from datetime import datetime

class Event(pendulum.DateTime):
    _forced_tz = "UTC"

    def __new__(cls, year, month, day, hour=0, minute=0, second=0, microsecond=0, tzinfo=None, **kwargs):
        is_internal = kwargs.pop('_internal_call', False)
        if is_internal or tzinfo is not None:
            return super().__new__(cls, year, month, day, hour, minute, second, microsecond, tzinfo=tzinfo)
        raise TypeError(f"Direct instantiation disabled. Use {cls.__name__}.datetime().")

    @classmethod
    def create_context(cls, timezone_name):
        valid_tz = pendulum.timezone(timezone_name).name
        return type(f"Event_{valid_tz.replace('/', '_')}", (cls,), {"_forced_tz": valid_tz})

    @classmethod
    def datetime(cls, year, month, day, hour=0, minute=0, second=0):
        p_obj = pendulum.datetime(year, month, day, hour, minute, second, tz=cls._forced_tz)
        return cls._from_pendulum(p_obj)

    @classmethod
    def _from_pendulum(cls, p_obj):
        return cls(p_obj.year, p_obj.month, p_obj.day, 
                   p_obj.hour, p_obj.minute, p_obj.second, 
                   p_obj.microsecond, tzinfo=p_obj.tzinfo, _internal_call=True)

    def is_same_moment(self, other):
        """
        Checks if two events occur at the exact same absolute UTC time,
        regardless of their local 'wall clock' display.
        """
        if not isinstance(other, datetime):
            return False
        # Comparing UTC timestamps is the safest way to ensure "same moment"
        return self.timestamp() == other.timestamp()

    def convert(self, target_event_class):
        return target_event_class._from_pendulum(self.in_timezone(target_event_class._forced_tz))