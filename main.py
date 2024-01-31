from google.oauth2 import service_account
import googleapiclient.discovery
import requests
import requests
from base64 import b64encode
from datetime import datetime, timedelta, timezone
import redis
import os
from dotenv import load_dotenv
import json
from zoneinfo import ZoneInfo

load_dotenv()

GOOGLE_CALENDAR_ID = os.getenv('GOOGLE_CALENDAR_ID')

TOGGL_USER_NAME = os.getenv('TOGGL_USER_NAME')
TOGGL_PASSWORD = os.getenv('TOGGL_PASSWORD')
TOGGL_WORKSPACE_ID = os.getenv('TOGGL_WORKSPACE_ID')

REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = os.getenv('REDIS_PORT')
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD')

TIME_FORMAT="%H:%M:%S"
DATE_TIME_FORMAT="%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME_ZONE = ZoneInfo('America/New_York')
UTC_TIME_ZONE = ZoneInfo('UTC')

TEMPLATE_DIRECTORY_PATH="templates/"

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

def add_edt_time_to_date(day_datetime, edt_time):
    edt_datetime = datetime.strptime(edt_time, TIME_FORMAT).time()
    day_datetime = day_datetime.replace(hour=edt_datetime.hour, minute=edt_datetime.minute, second=edt_datetime.second, microsecond=0, tzinfo=LOCAL_TIME_ZONE)
    return day_datetime

def convert_edt_datetime_to_utc_datetime(edt_datetime):
    return edt_datetime.astimezone(UTC_TIME_ZONE)

def get_string_from_datetime(datetime_object):
    return datetime_object.strftime(DATE_TIME_FORMAT)
    
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
    try:
        google_service.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=googleEventId).execute()
    except Exception as e:
        print(f'An exception occurred: {e}') 
    
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
        elif (serverDeletedAt is None or len(serverDeletedAt) <= 0):
            insertedGoogleEvent = insert_google_calendar_record(summary, clientName, startTime, endTime)
            insert_sync_record(togglId, insertedGoogleEvent['id'])
        else:
            print(f'Failed to delete. serverDeletedAt is not None= {serverDeletedAt is not None} and len(serverDeletedAt) > 0 = {len(serverDeletedAt) > 0} ')
    update_last_sync_time()
    
def get_all_toggl_events_for_today(day_delta=0):
    start_date = (datetime.now() + timedelta(days=day_delta))
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=LOCAL_TIME_ZONE)
    start_date = convert_edt_datetime_to_utc_datetime(start_date)
    start_date_string = start_date.strftime(DATE_TIME_FORMAT)
    end_date_string = (start_date + timedelta(days=1)).strftime(DATE_TIME_FORMAT)
    
    data = requests.get(f'https://api.track.toggl.com/api/v9/me/time_entries?start_date={start_date_string}&end_date={end_date_string}&meta=true', headers={'content-type': 'application/json', 'Authorization' : f'Basic {b64encode(bytes(f'{TOGGL_USER_NAME}:{TOGGL_PASSWORD}', 'utf-8')).decode('ascii')}'})
    return data

def delete_toggl_events_for_today(day_delta=0):
    data_to_be_deleted = get_all_toggl_events_for_today(day_delta)
    
    for record in data_to_be_deleted.json():
        toggl_event_id = record.get("id", "")
        delete_response = requests.delete(f'https://api.track.toggl.com/api/v9/workspaces/{record.get("workspace_id", "")}/time_entries/{toggl_event_id}', headers={'content-type': 'application/json', 'Authorization' : f'Basic {b64encode(bytes(f'{TOGGL_USER_NAME}:{TOGGL_PASSWORD}', 'utf-8')).decode('ascii')}'})
        delete_response_status_code = delete_response.status_code
        if (delete_response_status_code != 200):
            print(f'Error deleting Toggl event id:{toggl_event_id}, status code:{delete_response_status_code}')
        else:
            print(f'Delete toggl event id:{toggl_event_id}, status code:{delete_response_status_code}')
            
def insert_toggl_events(json_string, day_delta=0):
    parsed_json_array = json.loads(json_string)
    day = datetime.now() + timedelta(days=day_delta)
    for record in parsed_json_array:
        record["start"] = get_string_from_datetime(convert_edt_datetime_to_utc_datetime(add_edt_time_to_date(day, record["start"])))
        record["stop"] = get_string_from_datetime(convert_edt_datetime_to_utc_datetime(add_edt_time_to_date(day, record["stop"])))
        insert_response = requests.post(f'https://api.track.toggl.com/api/v9/workspaces/{TOGGL_WORKSPACE_ID}/time_entries', json=record, headers={'content-type': 'application/json', 'Authorization' : f'Basic {b64encode(bytes(f'{TOGGL_USER_NAME}:{TOGGL_PASSWORD}', 'utf-8')).decode('ascii')}'})
        insert_response_status_code = insert_response.status_code
        if (insert_response_status_code != 200):
            print(f'Error inserting Toggl event with status code:{insert_response_status_code}')
        else:
            print(f'Inserted Toggl event; id={insert_response}, start={insert_response}')
            
def save_string_to_file(string, json_file_name):
    file_path = f'{TEMPLATE_DIRECTORY_PATH}{json_file_name}'
    with open(file_path, 'w') as file:
        file.write(string)
        
def get_string_from_file(json_file_name):
    file_path = f'{TEMPLATE_DIRECTORY_PATH}{json_file_name}'
    with open(file_path, 'r') as file:
        return file.read()
    
def create_template_for_today(file_name, day_delta=0):
    events = get_all_toggl_events_for_today(day_delta)
    data = []
    utc_format = "%Y-%m-%dT%H:%M:%S%z"
    local_tz = ZoneInfo('America/New_York')

    for event in events.json():
        blah = {}
        blah['created_with'] = 'Toggl-to-Google-Calendar-Sync'
        blah['project_id'] = event.get("project_id", "")
        blah['description'] = event.get("description", "")
        utc_dt = datetime.strptime(event.get("start", ""), utc_format)
        local_dt = utc_dt.astimezone(local_tz)
        local_time = local_dt.strftime("%H:%M:%S")
        blah['start'] = local_time
        utc_dt = datetime.strptime(event.get("stop", ""), utc_format)
        local_dt = utc_dt.astimezone(local_tz)
        local_time = local_dt.strftime("%H:%M:%S")
        blah['stop'] = local_time
        blah['workspace_id'] = event.get("workspace_id", "")
        data.append(blah)
    
    json_string = json.dumps(data)
    save_string_to_file(json_string, file_name)
        
#####################################################################

# insert_toggl_events(get_string_from_file('weekday_commute_to_work.json'))
sync_toggl_to_google_calendar()