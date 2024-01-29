from google.oauth2 import service_account
import googleapiclient.discovery
import requests
import requests
from base64 import b64encode
from datetime import datetime, timedelta, timezone
import redis
import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_CALENDAR_ID = os.getenv('GOOGLE_CALENDAR_ID')

TOGGL_USER_NAME = os.getenv('TOGGL_USER_NAME')
TOGGL_PASSWORD = os.getenv('TOGGL_PASSWORD')

REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = os.getenv('REDIS_PORT')
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD')

redis_object = redis.Redis(
  host=REDIS_HOST,
  port=REDIS_PORT,
  password=REDIS_PASSWORD,
  decode_responses=True)

redis_key_toggl_last_sync_time = 'toggl_last_sync_time'
redis_key_toggl_to_google = 'toggl_to_google'


SCOPES = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/calendar.events']
SERVICE_ACCOUNT_FILE = 'google_calendar_service_account_file.json'
credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
googleService = googleapiclient.discovery.build('calendar', 'v3', credentials=credentials)

def get_current_timestamp():
    return int(datetime.timestamp(datetime.now()))

def get_last_week_timestamp():
    now = datetime.now()
    one_week_ago = now - timedelta(days=7)
    timestamp_one_week_ago = int(datetime.timestamp(one_week_ago))
    return timestamp_one_week_ago

def get_last_sync_time():
    last_sync_time = redis_object.get(redis_key_toggl_last_sync_time)
    
    if last_sync_time != None:
        return int(last_sync_time)
    else:
        return get_last_week_timestamp()

def insert_google_calendar_record(summary, description, startDateTime, endDateTime):
    event = {
    'summary': f'{summary}',
    'description': f'{description}',
    'start': {
        'dateTime': f'{startDateTime}',
        'timeZone': 'America/New_York',
    },
    'end': {
        'dateTime': f'{endDateTime}',
        'timeZone': 'America/New_York',
    }
    }

    event = googleService.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
    print(f"Inserted Google Calendar event {event['id']}")
    return event
    
def updateGoogleCalendarRecord(eventId, summary, description, startDateTime, endDateTime):
    print(f"Updating Google Calendar event {eventId}: summary={summary}, description={description}, startDateTime={startDateTime}, endDateTime={endDateTime}")

    event = googleService.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=eventId).execute()
    
    event['summary'] = summary
    event['description'] = description
    event['start']['dateTime'] = startDateTime
    event['end']['dateTime'] = endDateTime

    updated_event = googleService.events().update(calendarId=GOOGLE_CALENDAR_ID, eventId=event['id'], body=event).execute()
    return updated_event

def getGoogleIdSyncRecord(togglId):
    key = f'{redis_key_toggl_to_google}:{togglId}'
    google_calendar_event_id = redis_object.get(f'{redis_key_toggl_to_google}:{togglId}')

    if google_calendar_event_id != None:
        return google_calendar_event_id
    else:
        print(f'Google sync record does not exist for key: {key}')
        return ""

def insertSyncRecord(togglId, googleId):
    redis_object.set(f'{redis_key_toggl_to_google}:{togglId}', googleId)
        
def updateLastSyncTime():
    redis_object.set(redis_key_toggl_last_sync_time, get_current_timestamp())
            
def deleteGoogleEvent(googleEventId):
    print(f"Deleting Google Calendar event {googleEventId}")
    googleService.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=googleEventId).execute()
    
def deleteSyncRecordWithGoogleId(togglId):
    redis_object.delete(f'{redis_key_toggl_to_google}:{togglId}')


#####################################################################
data = requests.get(f'https://api.track.toggl.com/api/v9/me/time_entries?since={get_last_sync_time()}&meta=true', headers={'content-type': 'application/json', 'Authorization' : f'Basic {b64encode(bytes(f'{TOGGL_USER_NAME}:{TOGGL_PASSWORD}', 'utf-8')).decode('ascii')}'})
for record in data.json():
    togglId = record.get("id", "")
    clientName = record.get("client_name", "")
    projectName = record.get("project_name", "")
    description = record.get("description", "")
    startTime = record.get("start", "")
    endTime = record.get("stop", "")
    serverDeletedAt = record.get("server_deleted_at", "")
    
    if(len(description) > 0):
        summary = description + '-' + projectName
    else:
        summary = projectName
    
    googleEventId = getGoogleIdSyncRecord(togglId)
    if (len(googleEventId) > 0 and serverDeletedAt is not None and len(serverDeletedAt) > 0):
        deleteGoogleEvent(googleEventId)
        deleteSyncRecordWithGoogleId(googleEventId)
    elif (len(googleEventId) > 0):
        updateGoogleCalendarRecord(googleEventId, summary, clientName, startTime, endTime)
    else:
        insertedGoogleEvent = insert_google_calendar_record(summary, clientName, startTime, endTime)
        insertSyncRecord(togglId, insertedGoogleEvent['id'])
updateLastSyncTime()