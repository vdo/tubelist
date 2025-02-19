#!/usr/bin/env python3
import os
import pickle
import re
from typing import List, Tuple, Optional

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import BatchHttpRequest

# If modifying these scopes, delete your previously saved token.pickle.
SCOPES = ['https://www.googleapis.com/auth/youtube']

API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'


def get_authenticated_service():
    """
    Authenticate the user and return a YouTube service object.
    The credentials are stored in token.pickle for later use.
    """
    creds = None
    # Token file stores the user's access and refresh tokens.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If no valid credentials, go through the login flow.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=8080)
        # Save the credentials for future use.
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return build(API_SERVICE_NAME, API_VERSION, credentials=creds)


def extract_video_id(url: str) -> Optional[str]:
    """
    Extracts the video ID from a YouTube URL.
    Supports URLs in various formats.
    Returns the video ID as a string if found, otherwise None.
    """
    # This regex looks for the video id pattern in typical YouTube URLs.
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11})"
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None


def get_playlists(youtube) -> List[Tuple[str, str]]:
    """
    Get all playlists for the authenticated user.
    Returns a list of tuples containing (playlist_id, title).
    """
    request = youtube.playlists().list(
        part="snippet",
        mine=True,
        maxResults=50
    )
    response = request.execute()
    
    playlists = []
    for item in response.get('items', []):
        playlists.append((item['id'], item['snippet']['title']))
    return playlists


def get_video_details(youtube, video_id: str) -> Tuple[bool, int]:
    """
    Get video details including existence and duration.
    Returns tuple (exists, duration_seconds) or (False, 0) if video is unavailable.
    """
    try:
        response = youtube.videos().list(
            part="contentDetails,status",
            id=video_id
        ).execute()

        if not response['items']:
            return False, 0

        video = response['items'][0]
        
        # Check if video is available
        if video['status']['uploadStatus'] != 'processed' or \
           video.get('status', {}).get('privacyStatus') == 'private':
            return False, 0

        # Convert duration from ISO 8601 format to seconds
        duration = video['contentDetails']['duration']
        duration_seconds = sum(
            int(value) * multiplier 
            for value, multiplier in zip(
                map(lambda x: int(''.join(filter(str.isdigit, x or '0'))),
                duration.replace('PT','').replace('H',':').replace('M',':').replace('S','').split(':')),
                [3600, 60, 1]
            )
        )
        
        return True, duration_seconds
    except Exception as e:
        return False, 0


def get_playlist_size(youtube, playlist_id: str) -> int:
    """
    Get the current number of videos in a playlist.
    """
    try:
        request = youtube.playlistItems().list(
            part="id",
            maxResults=1,
            playlistId=playlist_id
        )
        response = request.execute()
        return int(response['pageInfo']['totalResults'])
    except Exception:
        return 0


def create_batch_request(youtube, playlist_id: str, video_id: str) -> BatchHttpRequest:
    """
    Create a batch request to add a video to a playlist.
    """
    return youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id
                }
            }
        }
    )
