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

# With duration filters (in minutes)
python main.py your_links.txt --min-duration 1 --max-duration 30
```
3. The script will:
   - Show a list of your YouTube playlists with their current video count
   - Let you choose which playlist to use
   - Verify each video's availability and duration
   - Add valid videos to the selected playlist
