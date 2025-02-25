#!/usr/bin/env python3
import argparse
import json
import os
import time
from datetime import datetime, timedelta
from colorama import Fore, Style, init
from tqdm import tqdm

from youtube import (
    get_authenticated_service,
    get_playlists,
    get_video_details,
    get_playlist_size,
    extract_video_id,
    create_playlist_item,
    video_exists_in_playlist,
    get_playlist_video_ids,
    QuotaExceededException
)
from googleapiclient.http import BatchHttpRequest


# Initialize colorama
init()

# Constants
TEMP_FILE = "remaining_videos.json"
QUOTA_RESET_HOURS = 24


def log_info(message):
    """Print an info message in cyan"""
    print(f"{Fore.CYAN}{message}{Style.RESET_ALL}")


def log_success(message):
    """Print a success message in green"""
    print(f"{Fore.GREEN}{message}{Style.RESET_ALL}")


def log_warning(message):
    """Print a warning message in yellow"""
    print(f"{Fore.YELLOW}Warning: {message}{Style.RESET_ALL}")


def log_error(message):
    """Print an error message in red"""
    print(f"{Fore.RED}Error: {message}{Style.RESET_ALL}")


def save_remaining_videos(videos, playlist_id, current_index=0, quota_exceeded=False):
    """Save remaining videos to a temporary file"""
    timestamp = datetime.now().isoformat()
    if quota_exceeded:
        timestamp += " quota_exceeded"
        
    data = {
        "playlist_id": playlist_id,
        "videos": videos[current_index:],
        "timestamp": timestamp
    }
    with open(TEMP_FILE, 'w') as f:
        json.dump(data, f)
    log_info(f"Saved {len(videos) - current_index} remaining videos to {TEMP_FILE}")


def load_remaining_videos():
    """Load remaining videos from temporary file if it exists"""
    if not os.path.exists(TEMP_FILE):
        return None, None, None
    
    with open(TEMP_FILE, 'r') as f:
        data = json.load(f)
    
    log_info(f"Loaded {len(data['videos'])} remaining videos from {TEMP_FILE}")
    return data["playlist_id"], data["videos"], data.get("timestamp")


def load_pending_validation():
    """Load videos that still need validation from a temporary file"""
    pending_file = "pending_validation.json"
    if not os.path.exists(pending_file):
        return None, None
    
    with open(pending_file, 'r') as f:
        data = json.load(f)
    
    log_info(f"Loaded {len(data['videos'])} videos that need validation from {pending_file}")
    return data["videos"], data.get("timestamp")


def wait_for_quota_reset(timestamp=None, non_blocking=False):
    """
    Wait until the quota resets (24 hours from the timestamp).
    If non_blocking is True, will save state and exit with instructions instead of waiting.
    """
    if timestamp:
        # Extract the timestamp part if it contains quota_exceeded
        if " quota_exceeded" in timestamp:
            timestamp = timestamp.split(" quota_exceeded")[0]
        reset_time = datetime.fromisoformat(timestamp) + timedelta(hours=QUOTA_RESET_HOURS)
    else:
        reset_time = datetime.now() + timedelta(hours=QUOTA_RESET_HOURS)
    
    wait_seconds = (reset_time - datetime.now()).total_seconds()
    if wait_seconds <= 0:
        return
    
    log_warning(f"YouTube API quota exceeded. Waiting until {reset_time.strftime('%Y-%m-%d %H:%M:%S')} before resuming")
    
    # If non-blocking mode is requested, just exit with instructions
    if non_blocking:
        log_info("The script has saved its state and will exit now.")
        log_info(f"Please run the script again after {reset_time.strftime('%Y-%m-%d %H:%M:%S')} to continue.")
        exit(0)
    
    # Display a countdown timer
    try:
        while wait_seconds > 0:
            hours, remainder = divmod(int(wait_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            print(f"\rWaiting for quota reset: {time_str} remaining", end="", flush=True)
            
            # If wait is very long (more than 1 hour), ask user if they want to exit
            if hours > 0 and wait_seconds % 300 == 0:  # Check every 5 minutes
                print("\r" + " " * 50 + "\r", end="")  # Clear the line
                exit_choice = input(f"{Fore.YELLOW}Long wait detected. Would you like to exit and resume later? (y/n): {Style.RESET_ALL}")
                if exit_choice.lower() == 'y':
                    log_info("The script has saved its state and will exit now.")
                    log_info(f"Please run the script again after {reset_time.strftime('%Y-%m-%d %H:%M:%S')} to continue.")
                    exit(0)
            
            time.sleep(1)
            wait_seconds -= 1
        print("\r" + " " * 50 + "\r", end="")  # Clear the line
        log_success("Quota reset time reached. Resuming operation...")
    except KeyboardInterrupt:
        print("\r" + " " * 50 + "\r", end="")  # Clear the line
        log_warning("Wait interrupted. You can restart the script later to continue processing")
        exit(0)


def process_videos(youtube, valid_video_ids, playlist_id, start_index=0, non_blocking=False):
    """Process videos and handle quota limits"""
    # Create progress bar for adding videos
    total_valid_videos = len(valid_video_ids)
    add_pbar = tqdm(
        total=total_valid_videos,
        desc="Adding to playlist",
        bar_format="{l_bar}%s{bar}%s{r_bar}" % (Fore.GREEN, Style.RESET_ALL),
        initial=start_index
    )

    error_count = 0
    duplicate_count = 0
    quota_exceeded = False
    
    # Get all existing video IDs in the playlist to avoid duplicates
    try:
        log_info("Fetching existing videos in the playlist to avoid duplicates...")
        existing_video_ids = get_playlist_video_ids(youtube, playlist_id)
        log_info(f"Found {len(existing_video_ids)} existing videos in the playlist")
    except QuotaExceededException:
        log_error("YouTube API quota exceeded while fetching existing videos.")
        save_remaining_videos(valid_video_ids, playlist_id, 0, quota_exceeded=True)
        wait_for_quota_reset(non_blocking=non_blocking)
        # Re-authenticate and try again
        youtube = get_authenticated_service()
        existing_video_ids = get_playlist_video_ids(youtube, playlist_id)
    except Exception as e:
        log_warning(f"Could not fetch existing videos: {str(e)}")
        log_warning("Will check for duplicates individually (less efficient)")
        existing_video_ids = set()
    
    # Process video IDs in smaller batches to avoid rate limits
    batch_size = 50
    i = start_index
    
    while i < len(valid_video_ids):
        if quota_exceeded:
            # Save remaining videos and wait for quota reset
            save_remaining_videos(valid_video_ids, playlist_id, i, quota_exceeded=True)
            wait_for_quota_reset(non_blocking=non_blocking)
            quota_exceeded = False
            youtube = get_authenticated_service()  # Re-authenticate after waiting
            
            # Refresh the list of existing videos after quota reset
            try:
                existing_video_ids = get_playlist_video_ids(youtube, playlist_id)
            except Exception:
                # If we can't refresh, continue with what we have
                pass
        
        end_idx = min(i + batch_size, len(valid_video_ids))
        current_batch = valid_video_ids[i:end_idx]
        log_info(f"Processing batch {i // batch_size + 1}: {len(current_batch)} video(s)")
        
        for j, vid in enumerate(current_batch):
            try:
                # Check if video already exists in the playlist
                if vid in existing_video_ids:
                    log_warning(f"Video {vid} already exists in the playlist - skipping")
                    duplicate_count += 1
                    add_pbar.update(1)
                    continue
                elif not existing_video_ids and video_exists_in_playlist(youtube, playlist_id, vid):
                    # Fallback to individual check if bulk check failed
                    log_warning(f"Video {vid} already exists in the playlist - skipping")
                    duplicate_count += 1
                    add_pbar.update(1)
                    continue
                
                response = create_playlist_item(youtube, playlist_id, vid)
                add_pbar.update(1)
                
                if response is None:
                    error_count += 1
                else:
                    # Add to our local cache of existing videos
                    existing_video_ids.add(vid)
                    log_success(f"Added video {vid} to the playlist")
            
            except QuotaExceededException:
                quota_exceeded = True
                # Save progress at the current position
                current_position = i + j
                save_remaining_videos(valid_video_ids, playlist_id, current_position, quota_exceeded=True)
                add_pbar.close()
                log_warning("YouTube API quota exceeded. Waiting for quota reset...")
                wait_for_quota_reset(non_blocking=non_blocking)
                
                # Re-authenticate and create a new progress bar
                youtube = get_authenticated_service()
                add_pbar = tqdm(
                    total=total_valid_videos,
                    desc="Adding to playlist",
                    bar_format="{l_bar}%s{bar}%s{r_bar}" % (Fore.GREEN, Style.RESET_ALL),
                    initial=current_position
                )
                
                # Continue from where we left off
                i = current_position
                break
        
        if not quota_exceeded:
            i = end_idx  # Move to the next batch if no quota issues

    add_pbar.close()
    
    # Clean up temp file if all videos were processed
    if os.path.exists(TEMP_FILE):
        os.remove(TEMP_FILE)
        log_info(f"Removed temporary file {TEMP_FILE}")

    if error_count > 0:
        log_warning(f"\nCompleted with {error_count} errors. Some videos may not have been added.")
    if duplicate_count > 0:
        log_info(f"\nSkipped {duplicate_count} videos that were already in the playlist.")
    
    if error_count == 0 and duplicate_count < total_valid_videos:
        log_success("\nAll new videos were successfully added to the playlist!")
    elif duplicate_count == total_valid_videos:
        log_warning("\nAll videos were already in the playlist. Nothing to add.")


def main():
    parser = argparse.ArgumentParser(
        description="Add YouTube links from a text file to an existing playlist.")
    parser.add_argument("txt_file", help="Text file containing YouTube links (one per line)")
    parser.add_argument("--min-duration", type=float, help="Minimum video duration in minutes")
    parser.add_argument("--max-duration", type=float, help="Maximum video duration in minutes")
    parser.add_argument("--non-blocking", action="store_true", help="Exit instead of waiting when quota is exceeded")
    args = parser.parse_args()

    # Check if we have remaining videos from a previous run
    saved_playlist_id, saved_videos, timestamp = load_remaining_videos()
    
    # Check if we need to wait for quota reset before starting
    if timestamp and "quota" in timestamp.lower():
        log_warning("Previous run encountered a quota limit. Waiting for quota reset...")
        wait_for_quota_reset(timestamp, non_blocking=args.non_blocking)
    
    # Check if we have videos pending validation
    pending_validation, pending_timestamp = load_pending_validation()
    if pending_validation and os.path.exists("pending_validation.json"):
        log_info(f"Found {len(pending_validation)} videos that need validation")
        if pending_timestamp and "quota" in pending_timestamp.lower():
            log_warning("Previous validation encountered a quota limit. Waiting for quota reset...")
            wait_for_quota_reset(pending_timestamp, non_blocking=args.non_blocking)
        
        # Ask user if they want to continue with validation
        continue_validation = input(f"{Fore.CYAN}Do you want to continue validating these videos? (y/n): {Style.RESET_ALL}").lower() == 'y'
        if continue_validation:
            # We'll use these videos later in the script
            pass
        else:
            # Remove the temporary file if user doesn't want to continue
            os.remove("pending_validation.json")
            log_info("Removed pending validation file")
            pending_validation = None
    
    if saved_videos:
        log_info(f"Found {len(saved_videos)} videos from a previous run")
        resume = input(f"{Fore.CYAN}Do you want to resume adding these videos to the playlist? (y/n): {Style.RESET_ALL}").lower() == 'y'
        
        if resume:
            # Authenticate and build the YouTube service
            youtube = get_authenticated_service()
            log_info(f"Resuming with playlist ID: {saved_playlist_id}")
            
            try:
                # Test the API with a lightweight call to check if quota is available
                get_playlist_size(youtube, saved_playlist_id)
                process_videos(youtube, saved_videos, saved_playlist_id, non_blocking=args.non_blocking)
                return
            except QuotaExceededException as e:
                log_error("YouTube API quota is currently exceeded.")
                save_remaining_videos(saved_videos, saved_playlist_id, 0, quota_exceeded=True)
                wait_for_quota_reset(non_blocking=args.non_blocking)
                # Re-authenticate and try again
                youtube = get_authenticated_service()
                process_videos(youtube, saved_videos, saved_playlist_id, non_blocking=args.non_blocking)
                return
        else:
            # Remove the temporary file if user doesn't want to resume
            os.remove(TEMP_FILE)
            log_info(f"Removed temporary file {TEMP_FILE}")
    
    parser = argparse.ArgumentParser(
        description="Add YouTube links from a text file to an existing playlist.")
    parser.add_argument("txt_file", help="Text file containing YouTube links (one per line)")
    parser.add_argument("--min-duration", type=float, help="Minimum video duration in minutes")
    parser.add_argument("--max-duration", type=float, help="Maximum video duration in minutes")
    parser.add_argument("--non-blocking", action="store_true", help="Exit instead of waiting when quota is exceeded")
    args = parser.parse_args()

    # Authenticate and build the YouTube service.
    youtube = get_authenticated_service()

    # Check if quota is available before proceeding
    try:
        # Get and display available playlists
        playlists = get_playlists(youtube)
        if not playlists:
            log_error("No playlists found. Please create a playlist first.")
            return
    except QuotaExceededException as e:
        log_error("YouTube API quota is currently exceeded.")
        log_warning("Please try again after 24 hours or wait for quota reset.")
        # Save an empty state with timestamp to enable waiting
        data = {
            "playlist_id": "",
            "videos": [],
            "timestamp": datetime.now().isoformat() + " quota_exceeded"
        }
        with open(TEMP_FILE, 'w') as f:
            json.dump(data, f)
        wait_for_quota_reset(non_blocking=args.non_blocking)
        # After waiting, restart the script
        log_info("Restarting the script after quota reset...")
        return main()  # Recursive call to restart

    log_info("\nAvailable playlists:")
    for i, (playlist_id, title) in enumerate(playlists, 1):
        size = get_playlist_size(youtube, playlist_id)
        print(f"{Fore.CYAN}{i}. {title}{Style.RESET_ALL} (ID: {playlist_id}, Videos: {size})")

    # Get user choice
    while True:
        try:
            choice = int(input(f"\n{Fore.CYAN}Enter the number of the playlist to use (1-{len(playlists)}): {Style.RESET_ALL}"))
            if 1 <= choice <= len(playlists):
                playlist_id = playlists[choice-1][0]
                current_size = get_playlist_size(youtube, playlist_id)
                if current_size >= 5000:
                    log_error("Selected playlist already has 5000 videos (YouTube's limit)")
                    return
                log_success(f"\nSelected playlist: {playlists[choice-1][1]}")
                break
            else:
                log_error(f"Invalid choice. Please enter a number between 1 and {len(playlists)}")
        except ValueError:
            log_error("Please enter a valid number")

    # Get all video IDs first and remove duplicates
    video_ids = []
    seen_urls = set()
    skipped_count = 0
    
    log_info("Reading and validating video URLs...")
    with open(args.txt_file, 'r') as f:
        for line in f:
            url = line.strip()
            if not url or url in seen_urls:
                continue
                
            vid = extract_video_id(url)
            if vid:
                video_ids.append(vid)
                seen_urls.add(url)

    if pending_validation:
        video_ids = pending_validation + video_ids

    if not video_ids:
        log_error("No valid YouTube URLs found in the file. Exiting.")
        return

    log_info(f"Found {len(video_ids)} unique video URLs to process")

    # Create progress bar for validation
    validation_pbar = tqdm(
        total=len(video_ids),
        desc="Validating videos",
        bar_format="{l_bar}%s{bar}%s{r_bar}" % (Fore.BLUE, Style.RESET_ALL)
    )

    # Get video details in batches
    valid_video_ids = []
    try:
        # First, get all existing videos in the playlist to avoid duplicates
        try:
            log_info("Fetching existing videos in the playlist to avoid duplicates...")
            existing_video_ids = get_playlist_video_ids(youtube, playlist_id)
            log_info(f"Found {len(existing_video_ids)} existing videos in the playlist")
        except QuotaExceededException:
            raise  # Re-raise to be caught by the outer try-except
        except Exception as e:
            log_warning(f"Could not fetch existing videos: {str(e)}")
            log_warning("Will validate all videos and check for duplicates later")
            existing_video_ids = set()
        
        # Track duplicates found during validation
        duplicate_count = 0
        
        video_details = get_video_details(youtube, video_ids)
        
        for vid in video_ids:
            exists, duration = video_details[vid]
            validation_pbar.update(1)

            # Skip if the video is already in the playlist
            if existing_video_ids and vid in existing_video_ids:
                log_warning(f"Video {vid} already exists in the playlist - skipping")
                duplicate_count += 1
                continue

            if not exists:
                log_warning(f"Video {vid} is unavailable or private")
                skipped_count += 1
                continue

            duration_minutes = duration / 60
            if args.min_duration and duration_minutes < args.min_duration:
                log_warning(f"Video {vid} is too short ({duration_minutes:.1f}m < {args.min_duration}m)")
                skipped_count += 1
                continue

            if args.max_duration and duration_minutes > args.max_duration:
                log_warning(f"Video {vid} is too long ({duration_minutes:.1f}m > {args.max_duration}m)")
                skipped_count += 1
                continue

            valid_video_ids.append(vid)

            # Check if adding this video would exceed the 5000 limit
            if current_size + len(valid_video_ids) > 5000:
                log_warning(f"Can only add {5000 - current_size} more videos to reach YouTube's 5000 video limit")
                valid_video_ids = valid_video_ids[:5000 - current_size]
                break
        
        # Clean up pending validation file if it exists and we've successfully validated
        if os.path.exists("pending_validation.json"):
            os.remove("pending_validation.json")
            log_info("Removed pending validation file after successful validation")
            
    except QuotaExceededException:
        log_error("YouTube API quota exceeded during video validation.")
        # Save the videos we've already validated
        if valid_video_ids:
            save_remaining_videos(valid_video_ids, playlist_id, 0, quota_exceeded=True)
            log_info(f"Saved {len(valid_video_ids)} validated videos for later processing")
        # Also save the remaining videos that need validation
        remaining_to_validate = [vid for vid in video_ids if vid not in valid_video_ids]
        if remaining_to_validate:
            # Create a separate file for videos that still need validation
            with open("pending_validation.json", 'w') as f:
                json.dump({
                    "videos": remaining_to_validate,
                    "timestamp": datetime.now().isoformat() + " quota_exceeded"
                }, f)
            log_info(f"Saved {len(remaining_to_validate)} videos that still need validation")
        
        wait_for_quota_reset(non_blocking=args.non_blocking)
        log_info("Restarting after quota reset...")
        return main()  # Restart from the beginning
    finally:
        validation_pbar.close()

    if not valid_video_ids:
        log_error("No valid YouTube videos found. Exiting.")
        if skipped_count > 0:
            log_warning(f"Skipped {skipped_count} videos due to availability/duration constraints")
        if duplicate_count > 0:
            log_info(f"Skipped {duplicate_count} videos that were already in the playlist")
        return

    log_success(f"\nFound {len(valid_video_ids)} valid video(s) to add")
    if skipped_count > 0:
        log_warning(f"Skipped {skipped_count} videos due to availability/duration constraints")
    if duplicate_count > 0:
        log_info(f"Skipped {duplicate_count} videos that were already in the playlist")

    # Process the videos with quota handling
    process_videos(youtube, valid_video_ids, playlist_id, non_blocking=args.non_blocking)


if __name__ == "__main__":
    main()
