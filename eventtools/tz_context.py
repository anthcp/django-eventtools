from functools import lru_cache
from .tzEvent.event import Event

@lru_cache(maxsize=256)
def event_context_for(tz_name: str):
    return Event.create_context(tz_name)