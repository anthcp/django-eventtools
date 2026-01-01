import pendulum
from datetime import datetime

class Event(pendulum.DateTime):
    # This class attribute holds the locked timezone
    _forced_tz = "UTC"

    def __new__(cls, *args, **kwargs):
        """
        Prevent direct instantiation via Event().
        This forces users to use the provided factory methods.
        """
        if not kwargs.get('_internal_call'):
            raise TypeError(
                f"Direct instantiation of {cls.__name__} is disabled. "
                f"Use {cls.__name__}.datetime() or {cls.__name__}.date() instead."
            )
        # Remove the secret flag before passing to the real constructor
        kwargs.pop('_internal_call')
        return super().__new__(cls, *args, **kwargs)

    @classmethod
    def create_context(cls, timezone_name):
        """
        Creates a specialized Event class locked to a specific timezone.
        """
        valid_tz = pendulum.timezone(timezone_name).name
        return type(f"Event_{valid_tz}", (cls,), {"_forced_tz": valid_tz})

    @classmethod
    def datetime(cls, year, month, day, hour=0, minute=0, second=0):
        """
        The only allowed way to create a full datetime object.
        Only accepts naive integers.
        """
        p_obj = pendulum.datetime(year, month, day, hour, minute, second, tz=cls._forced_tz)
        
        return cls(
            p_obj.year, p_obj.month, p_obj.day, 
            p_obj.hour, p_obj.minute, p_obj.second, 
            p_obj.microsecond, p_obj.tzinfo,
            _internal_call=True
        )

    @classmethod
    def date(cls, year, month, day):
        """
        The only allowed way to create a date-based object.
        Returns a datetime at 00:00:00 in the locked timezone.
        """
        return cls.datetime(year, month, day, hour=0, minute=0, second=0)

# --- Usage ---

# 1. Create your locked Event context
LondonEvent = Event.create_context("Europe/London")

# 2. Try to instantiate directly (This will fail)
try:
    bad_attempt = LondonEvent(2025, 12, 23)
except TypeError as e:
    print(f"Blocked: {e}")

# 3. Create using the forced datetime/date methods
my_dt = LondonEvent.datetime(2025, 12, 23, 14, 30)
my_date = LondonEvent.date(2025, 12, 23)

print(f"Created Time: {my_dt}")   # 2025-12-23 14:30:00+00:00
print(f"Created Date: {my_date}") # 2025-12-23 00:00:00+00:00