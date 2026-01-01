from event import Event

London = Event.create_context("Europe/London")
NewYork = Event.create_context("America/New_York")

# This will now succeed without the keyword argument error
meeting = London.datetime(2025, 6, 1, 14, 0)
print(f"London: {meeting}")

# Conversion works too
meeting_ny = meeting.convert(NewYork)
print(f"NY:     {meeting_ny}")

London = Event.create_context("Europe/London")
NewYork = Event.create_context("America/New_York")

meeting1 = London.datetime(2025, 6, 1, 14, 0)
meeting2 = NewYork.datetime(2025, 6, 1, 9, 0)

# Comparison: These are the SAME moment (True)
print(meeting1 == meeting2) 

# Math: Add 2 hours and 30 minutes
later = meeting1.add(hours=2, minutes=30)
print(f"Later: {later}")

# Standard Python way
print(meeting1.strftime("%A, %d %B %Y @ %H:%M"))

# Pendulum way (more intuitive)
print(meeting1.format("dddd, D MMMM YYYY [at] HH:mm"))
# Output: Sunday, 01 June 2025 at 14:00

start = London.datetime(2025, 6, 1, 14, 0)
end = London.datetime(2025, 6, 1, 16, 45)

diff = end - start
print(f"Duration: {diff.hours} hours and {diff.minutes} minutes")
# Output: Duration: 2 hours and 45 minutes

past_event = London.datetime(2023, 1, 1)
# "2 years ago" (depending on current date)
print(past_event.diff_for_humans())

event = London.datetime(2025, 6, 15, 14, 0)

# What was the start of this week?
print(event.start_of('week'))

# What is the last day of this month?
print(event.end_of('month').day) # 30