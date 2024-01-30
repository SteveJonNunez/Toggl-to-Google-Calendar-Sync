# Toggl-to-Google-Calendar-Sync
## Usage
- Create a .env file like the following
```
GOOGLE_CALENDAR_ID = '<Put Google Calendar ID>'

TOGGL_USER_NAME = '<Put Toggl username>'
TOGGL_PASSWORD = 'Put Toggl password'
TOGGL_WORKSPACE_ID = <Put Toggl workspace ID>

REDIS_HOST = '<Put Reddis host>'
REDIS_PORT = <Put Reddis port>
REDIS_PASSWORD = 'Put Reddis password'
```

## Notes
The zoneinfo module relies on the IANA Time Zone Database being available on your system. This database is usually present on most Unix-like systems, but it might not be on Windows.
If you're on Windows, you might not have this database, and Python falls back to using the tzdata package. Ensure you have tzdata installed. You can install it using pip install tzdata.
