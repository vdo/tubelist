# tubelist

## Description
A Python script to bulk add YouTube videos to a playlist. The script allows you to select from your existing playlists and add multiple videos from a text file.

## Setup
1. Create and activate a Python virtual environment:
```bash
python3 -m venv myenv
source myenv/bin/activate
```

2. Install the required dependencies:
```bash
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib colorama tqdm
```

3. Set up YouTube API credentials:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the YouTube Data API v3
   - Create OAuth 2.0 credentials
   - Download the credentials and save them as `client_secrets.json` in the project directory

## Usage
1. Create a text file containing YouTube video URLs (one per line)
2. Run the script with optional duration filters:
```bash
# Basic usage
python main.py your_links.txt

# With duration filters (in seconds)
python main.py your_links.txt --min-duration 60 --max-duration 3600
```
3. The script will:
   - Show a list of your YouTube playlists with their current video count
   - Let you choose which playlist to use
   - Verify each video's availability and duration
   - Add valid videos to the selected playlist

## Features
- Interactive playlist selection
- Bulk video addition
- Video validation:
  - Checks if videos exist and are available
  - Optional minimum and maximum duration filters
  - Respects YouTube's 5000 videos per playlist limit
- Handles various YouTube URL formats
- Processes videos in batches to respect API limits
- Error handling for invalid URLs
- Detailed progress reporting

## Requirements
- Python 3.6+
- Google API Python Client
- Google Auth Library
- OAuth2 Client
- colorama
- tqdm
- A Google account with YouTube access

## Limitations
- Maximum 5000 videos per playlist (YouTube limitation)
- Private videos cannot be added
- Videos must be fully processed on YouTube to be added