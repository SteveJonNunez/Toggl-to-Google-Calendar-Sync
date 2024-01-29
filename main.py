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
TOGGL_WORKSPACE_ID = os.getenv('TOGGL_WORKSPACE_ID')

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
google_service = googleapiclient.discovery.build('calendar', 'v3', credentials=credentials)

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

    event = google_service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
    print(f"Inserted Google Calendar event {event['id']}")
    return event
    
def update_google_calendar_record(eventId, summary, description, startDateTime, endDateTime):
    print(f"Updating Google Calendar event {eventId}: summary={summary}, description={description}, startDateTime={startDateTime}, endDateTime={endDateTime}")

    event = google_service.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=eventId).execute()
    
    event['summary'] = summary
    event['description'] = description
    event['start']['dateTime'] = startDateTime
    event['end']['dateTime'] = endDateTime

    updated_event = google_service.events().update(calendarId=GOOGLE_CALENDAR_ID, eventId=event['id'], body=event).execute()
    return updated_event

def get_google_id_sync_record(togglId):
    key = f'{redis_key_toggl_to_google}:{togglId}'
    google_calendar_event_id = redis_object.get(f'{redis_key_toggl_to_google}:{togglId}')

    if google_calendar_event_id != None:
        return google_calendar_event_id
    else:
        print(f'Google sync record does not exist for key: {key}')
        return ""

def insert_sync_record(togglId, googleId):
    redis_object.set(f'{redis_key_toggl_to_google}:{togglId}', googleId)
        
def update_last_sync_time():
    redis_object.set(redis_key_toggl_last_sync_time, get_current_timestamp())
            
def delete_google_event(googleEventId):
    print(f"Deleting Google Calendar event {googleEventId}")
    google_service.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=googleEventId).execute()
    
def delete_sync_record_with_google_id(togglId):
    redis_object.delete(f'{redis_key_toggl_to_google}:{togglId}')
    
def sync_toggl_to_google_calendar():
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
        
        googleEventId = get_google_id_sync_record(togglId)
        if (len(googleEventId) > 0 and serverDeletedAt is not None and len(serverDeletedAt) > 0):
            delete_google_event(googleEventId)
            delete_sync_record_with_google_id(googleEventId)
        elif (len(googleEventId) > 0):
            update_google_calendar_record(googleEventId, summary, clientName, startTime, endTime)
        else:
            insertedGoogleEvent = insert_google_calendar_record(summary, clientName, startTime, endTime)
            insert_sync_record(togglId, insertedGoogleEvent['id'])
    update_last_sync_time()
    
def get_all_toggl_day_events():
    data = requests.get(f'https://api.track.toggl.com/api/v9/me/time_entries?start_date=2024-01-29&end_date=2024-01-30&meta=true', headers={'content-type': 'application/json', 'Authorization' : f'Basic {b64encode(bytes(f'{TOGGL_USER_NAME}:{TOGGL_PASSWORD}', 'utf-8')).decode('ascii')}'})
    for record in data.json():
        togglId = record.get("id", "")
        clientName = record.get("client_name", "")
        projectName = record.get("project_name", "")
        description = record.get("description", "")
        startTime = record.get("start", "")
        endTime = record.get("stop", "")
        serverDeletedAt = record.get("server_deleted_at", "")
        workspace_id = record.get("workspace_id", "")
        
        print(f'{togglId}, {clientName}, {projectName}, {description}, {startTime}, {endTime}, {serverDeletedAt}, {workspace_id}, ')

#####################################################################
get_all_toggl_day_events()