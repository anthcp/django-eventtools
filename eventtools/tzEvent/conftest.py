import pytest
import pendulum
from .event import Event  # Assuming the class is in your_module.py

@pytest.fixture
def London():
    return Event.create_context("Europe/London")

@pytest.fixture
def NewYork():
    return Event.create_context("America/New_York")