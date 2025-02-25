#!/usr/bin/env python3
import os
import pickle
import re
from typing import List, Tuple, Optional, Dict

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete your previously saved token.pickle.
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']

API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'


class QuotaExceededException(Exception):
    """Exception raised when YouTube API quota is exceeded."""
    pass


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
    # Check if URL contains a YouTube domain
    youtube_domains = ('youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com')
    if not any(domain in url.lower() for domain in youtube_domains):
        return None

    # This regex looks for the video id pattern in typical YouTube URLs.
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11})"
    match = re.search(pattern, url)
    return match.group(1) if match else None


def get_playlists(youtube) -> List[Tuple[str, str]]:
    """
    Get all playlists for the authenticated user.
    Returns a list of tuples containing (playlist_id, title).
    """
    try:
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
    except HttpError as e:
        if "quota" in str(e).lower():
            raise QuotaExceededException(str(e))
        raise


def get_video_details(youtube, video_ids: List[str]) -> Dict[str, Tuple[bool, int]]:
    """
    Get video details including existence and duration for multiple videos.
    Returns a dictionary mapping video_id to tuple (exists, duration_seconds).
    Uses a single API call for up to 50 videos.
    """
    results = {}
    # Process in batches of 50 (API limit)
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        try:
            request = youtube.videos().list(
                part="contentDetails,status",
                id=",".join(batch)
            )
            response = request.execute()
            
            # Create a mapping of found videos
            found_videos = {
                item['id']: (
                    item['status']['uploadStatus'] == 'processed',
                    parse_duration(item['contentDetails']['duration'])
                )
                for item in response.get('items', [])
                if item['status']['uploadStatus'] == 'processed'
            }
            
            # Add results, marking missing videos as unavailable
            for vid in batch:
                results[vid] = found_videos.get(vid, (False, 0))
                
        except HttpError as e:
            if "quota" in str(e).lower():
                raise QuotaExceededException(str(e))
            # If request fails for other reasons, mark all videos in batch as unavailable
            for vid in batch:
                results[vid] = (False, 0)
    
    return results


def parse_duration(duration: str) -> int:
    """
    Parse ISO 8601 duration format to seconds.
    Example: PT1H2M10S -> 3730 seconds
    """
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
    if not match:
        return 0
    
    hours, minutes, seconds = match.groups()
    total = 0
    if hours:
        total += int(hours) * 3600
    if minutes:
        total += int(minutes) * 60
    if seconds:
        total += int(seconds)
    
    return total


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
    except HttpError as e:
        if "quota" in str(e).lower():
            raise QuotaExceededException(str(e))
        return 0


def create_playlist_item(youtube, playlist_id: str, video_id: str):
    """
    Add a video to a playlist.
    Returns the response if successful, None if failed.
    Raises QuotaExceededException if the quota is exceeded.
    """
    try:
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
        ).execute()
    except HttpError as e:
        error_str = str(e)
        if "quota" in error_str.lower():
            print(f"Error adding video {video_id}: {error_str}")
            raise QuotaExceededException(error_str)
        print(f"Error adding video {video_id}: {error_str}")
        return None
    except Exception as e:
        print(f"Error adding video {video_id}: {str(e)}")
        return None
