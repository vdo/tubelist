#!/usr/bin/env python3
import argparse
from colorama import Fore, Style, init
from tqdm import tqdm

from youtube import (
    get_authenticated_service,
    get_playlists,
    get_video_details,
    get_playlist_size,
    extract_video_id,
    create_playlist_item
)
from googleapiclient.http import BatchHttpRequest


# Initialize colorama
init()


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


def main():
    parser = argparse.ArgumentParser(
        description="Add YouTube links from a text file to an existing playlist.")
    parser.add_argument("txt_file", help="Text file containing YouTube links (one per line)")
    parser.add_argument("--min-duration", type=float, help="Minimum video duration in minutes")
    parser.add_argument("--max-duration", type=float, help="Maximum video duration in minutes")
    args = parser.parse_args()

    # Authenticate and build the YouTube service.
    youtube = get_authenticated_service()

    # Get and display available playlists
    playlists = get_playlists(youtube)
    if not playlists:
        log_error("No playlists found. Please create a playlist first.")
        return

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

    # Read and parse the input file.
    try:
        with open(args.txt_file, "r", encoding="utf-8") as f:
            links = [line.strip() for line in f if line.strip()]
    except Exception as e:
        log_error(f"Failed to read input file: {str(e)}")
        return

    total_links = len(links)
    log_info(f"\nProcessing {total_links} links...")

    # Extract valid video IDs from the links and check their availability/duration
    video_ids = []
    skipped_count = 0
    error_count = 0
    
    # Create progress bar for video validation
    validation_pbar = tqdm(
        total=total_links,
        desc="Validating videos",
        bar_format="{l_bar}%s{bar}%s{r_bar}" % (Fore.BLUE, Style.RESET_ALL)
    )

    for link in links:
        vid = extract_video_id(link)
        if not vid:
            log_warning(f"Could not extract video ID from: {link}")
            validation_pbar.update(1)
            continue

        exists, duration = get_video_details(youtube, vid)
        if not exists:
            log_warning(f"Video {vid} is unavailable or private")
            skipped_count += 1
            validation_pbar.update(1)
            continue

        duration_minutes = duration / 60
        if args.min_duration and duration_minutes < args.min_duration:
            log_warning(f"Video {vid} is too short ({duration_minutes:.1f}m < {args.min_duration}m)")
            skipped_count += 1
            validation_pbar.update(1)
            continue

        if args.max_duration and duration_minutes > args.max_duration:
            log_warning(f"Video {vid} is too long ({duration_minutes:.1f}m > {args.max_duration}m)")
            skipped_count += 1
            validation_pbar.update(1)
            continue

        video_ids.append(vid)

        # Check if adding this video would exceed the 5000 limit
        if current_size + len(video_ids) > 5000:
            log_warning(f"Can only add {5000 - current_size} more videos to reach YouTube's 5000 video limit")
            video_ids = video_ids[:5000 - current_size]
            validation_pbar.update(1)
            break

        validation_pbar.update(1)

    validation_pbar.close()

    if not video_ids:
        log_error("No valid YouTube videos found. Exiting.")
        if skipped_count > 0:
            log_warning(f"Skipped {skipped_count} videos due to availability/duration constraints")
        return

    log_success(f"\nFound {len(video_ids)} valid video(s)")
    if skipped_count > 0:
        log_warning(f"Skipped {skipped_count} videos due to availability/duration constraints")

    # Create progress bar for adding videos
    total_valid_videos = len(video_ids)
    add_pbar = tqdm(
        total=total_valid_videos,
        desc="Adding to playlist",
        bar_format="{l_bar}%s{bar}%s{r_bar}" % (Fore.GREEN, Style.RESET_ALL)
    )

    error_count = 0
    # Process video IDs in smaller batches to avoid rate limits
    batch_size = 50
    for i in range(0, len(video_ids), batch_size):
        current_batch = video_ids[i:i + batch_size]
        log_info(f"Processing batch {i // batch_size + 1}: {len(current_batch)} video(s)")
        
        for vid in current_batch:
            response = create_playlist_item(youtube, playlist_id, vid)
            add_pbar.update(1)
            
            if response is None:
                error_count += 1
            else:
                log_success(f"Added video {vid} to the playlist")

    add_pbar.close()

    if error_count > 0:
        log_warning(f"\nCompleted with {error_count} errors. Some videos may not have been added.")
    else:
        log_success("\nAll videos were successfully added to the playlist!")


if __name__ == "__main__":
    main()
