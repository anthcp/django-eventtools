import pendulum
from datetime import datetime

class Event(pendulum.DateTime):
    _forced_tz = "UTC"

    def __new__(cls, year, month, day, hour=0, minute=0, second=0, microsecond=0, tzinfo=None, **kwargs):
        # 1. Extract our custom flag and ensure it doesn't go to the parent
        is_internal = kwargs.pop('_internal_call', False)
        
        # 2. Safety check: Only allow if it's an internal factory call or already has tzinfo
        if is_internal or tzinfo is not None:
            # We explicitly pass only the arguments the parent expects
            return super().__new__(cls, year, month, day, hour, minute, second, microsecond, tzinfo=tzinfo)
        
        # 3. Block manual naive instantiation
        raise TypeError(
            f"Direct instantiation is disabled. Use {cls.__name__}.datetime() or .date()."
        )

    @classmethod
    def create_context(cls, timezone_name):
        """Creates a specific Event class locked to a timezone."""
        valid_tz = pendulum.timezone(timezone_name).name
        class_name = f"Event_{valid_tz.replace('/', '_')}"
        return type(class_name, (cls,), {"_forced_tz": valid_tz})

    @classmethod
    def datetime(cls, year, month, day, hour=0, minute=0, second=0):
        """Factory for new naive inputs."""
        p_obj = pendulum.datetime(year, month, day, hour, minute, second, tz=cls._forced_tz)
        # Use our internal helper to instantiate
        return cls._from_pendulum(p_obj)

    @classmethod
    def date(cls, year, month, day):
        """Creates an Event object at midnight in the locked timezone."""
        return cls.datetime(year, month, day, hour=0, minute=0, second=0)

    @classmethod
    def _from_pendulum(cls, p_obj):
        """Casts a Pendulum object into this Event subclass."""
        # Note the _internal_call=True here
        return cls(
            p_obj.year, p_obj.month, p_obj.day, 
            p_obj.hour, p_obj.minute, p_obj.second, 
            p_obj.microsecond, tzinfo=p_obj.tzinfo,
            _internal_call=True
        )

    def convert(self, target_event_class):
        """Shifts this moment into a different Event Context."""
        if not issubclass(target_event_class, Event):
            raise ValueError("Target must be an Event context class.")
        
        converted_p = self.in_timezone(target_event_class._forced_tz)
        return target_event_class._from_pendulum(converted_p)

    def __repr__(self):
        return f"<{self.__class__.__name__} [{self.to_datetime_string()}]>"