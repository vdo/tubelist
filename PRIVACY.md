# Privacy Policy for Tubelist

## Overview
Tubelist is a command-line tool that helps users manage their YouTube playlists. This privacy policy explains how the application handles user data and credentials.

## Data Collection and Storage

### Local Storage
The application stores the following data locally on your computer:

1. **OAuth 2.0 Credentials** (`client_secrets.json`):
   - Stored in the application directory
   - Contains your YouTube API credentials
   - Never transmitted to any third party
   - You should never share this file

2. **Access Tokens** (`token.pickle`):
   - Stored in the application directory
   - Contains your YouTube access tokens
   - Used to authenticate with YouTube API
   - Never transmitted to any third party
   - You should never share this file

### YouTube Data Access
The application requires the following YouTube permissions:

- Access to view and manage your YouTube playlists
- Ability to read video metadata (duration, availability)

## Data Usage

### How We Use Your Data
1. **Authentication**: Access tokens are used solely for authenticating with the YouTube API
2. **Playlist Management**: Video IDs and playlist data are used only for the requested operations
3. **Local Operations**: All data processing happens locally on your machine, no one will see the parsed text files.

## Security

### Best Practices
1. Keep your `client_secrets.json` and `token.pickle` files secure
2. Don't share these files with others
3. Store them in a directory with appropriate permissions
4. The `.gitignore` file is configured to prevent accidentally committing these files

### Data Removal
To remove all stored data:
1. Delete `token.pickle` to remove stored access tokens
2. Delete `client_secrets.json` to remove API credentials
