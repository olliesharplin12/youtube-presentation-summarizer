import argparse
import glob
import os
import re
import subprocess
import sys
import yt_dlp
import time
from google.genai import types

try:
    from google import genai
except ImportError:
    genai = None

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None


# TODO
TODO = [
    "Download high res video for image parsing, but save video in 720p for storage optimization",
    "Store directly into OneDrive",
    "Improve AI retry logic and model usage steps",
    "Add ability to re-run summary generation without redownloading videos"
]


GEMINI_MODEL = "gemini-3.6-flash"
# GEMINI_MODEL = "gemini-3.5-flash-lite"

IMAGE_NAME_PREFIX = "z_slide"
IMAGE_OUTPUT_FORMAT = ".jpg"
IMAGE_NAME_FORMAT = f"{IMAGE_NAME_PREFIX}_%03d{IMAGE_OUTPUT_FORMAT}"


def sanitize_filename(name: str) -> str:
    """Remove characters that are invalid in directory or file names."""
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


def extract_snippet_text(item) -> str:
    """Extract text safely whether item is a dict or an object attribute."""
    if isinstance(item, dict):
        return item.get("text", "")
    if hasattr(item, "text"):
        return item.text
    return str(item)


def fetch_transcript_api(video_id: str) -> tuple[bool, str]:
    """Fetch transcript directly using youtube_transcript_api."""
    if not YouTubeTranscriptApi:
        print("[!] 'YouTubeTranscriptApi' module not installed.")
        return False, "'YouTubeTranscriptApi' module not installed."

    youtube_transcript_API = YouTubeTranscriptApi()

    print(f"[+] Attempting transcript fetch via youtube_transcript_api (ID: {video_id})...")
    try:
        # Standard fetch for English variants
        transcript_data = youtube_transcript_API.fetch(
            video_id, languages=["en", "en-US", "en-GB"]
        )
        return True, " ".join(extract_snippet_text(item) for item in transcript_data)
    except Exception as e:
        print(f"[-] Error fetching transcript via YouTubeTranscriptApi: {e}")
        return False, f"Error fetching transcript via YouTubeTranscriptApi: {e}"


def generate_ai_summary(transcript_text: str, video_title: str) -> tuple[bool, str]:
    """Send transcript to Gemini API to generate a structured topic summary."""
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print("[!] GEMINI_API_KEY environment variable not set. Skipping AI summary.")
        return False, "AI Summary skipped: GEMINI_API_KEY environment variable missing."

    if not genai:
        print("[!] 'google-genai' package not installed. Skipping AI summary.")
        return False, "AI Summary skipped: google-genai library missing."

    print(f"[+] Sending transcript to {GEMINI_MODEL} for summarization...")
    client = genai.Client(api_key=api_key)

    prompt = f"""
        You are an expert technical editor. Below is the transcript of the video titled: "{video_title}".

        Please generate a comprehensive, structured summary in Markdown format to accompany slide screenshots extracted from the video.

        The intended use case for this output is to read it alongside the slide deck which the presenter in the video is showning and talking to.
        Please provide sufficient detail so all discussion points can be understood with key metrics provided as well.

        Transcript:
        {transcript_text}
    """

    # Retry configuration for handling 503 / 429 server spikes
    max_attempts = 10
    base_delay = 2  # Initial wait in seconds

    for attempt in range(1, max_attempts + 1):
        try:
            # Explicit config disables automatic function calling warnings
            config = types.GenerateContentConfig(
                temperature=0.2,
            )

            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=config,
            )
            return True, response.text

        except Exception as e:
            error_msg = str(e)
            if "RESOURCE_EXHAUSTED" in error_msg:
                pass
            elif "503" in error_msg or "UNAVAILABLE" in error_msg or "429" in error_msg:
                if attempt < max_attempts:
                    sleep_time = base_delay * attempt
                    print(
                        f"[!] Gemini API busy (503/429). Retrying in {sleep_time}s (Attempt {attempt+1}/{max_attempts})..."
                    )
                    time.sleep(sleep_time)
                    continue

            print(f"[-] Error calling Gemini API: {e}")
            return False, f"AI Summary failed due to error: {e}"

    return False, "AI Summary failed: Exceeded maximum API retries."


def process_video(url: str, output_dir: str) -> None:
    print("\n" + "=" * 60)
    print(f"Processing URL: {url}")
    print("=" * 60)

    # 1. Extract metadata
    ydl_meta_opts = {
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_meta_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            print(f"[-] Error extracting metadata for {url}: {e}")
            return f"Error extracting metadata for {url}: {e}"

    video_id = info.get("id")
    if not video_id:
        return "Missing video ID"
    
    upload_date = info.get("upload_date", "")
    yymmdd = upload_date[2:] if len(upload_date) == 8 else "000000"

    raw_title = info.get("title", "Untitled_Video")
    clean_title = sanitize_filename(raw_title)

    folder_name = os.path.join(output_dir, f"{yymmdd} - {clean_title}")
    os.makedirs(folder_name, exist_ok=True)
    print(f"[+] Output directory: {folder_name}")

    # 2. Primary transcript retrieval: YoutTubeTranscriptApi
    success, transcript_text = fetch_transcript_api(video_id)
    if not success:
        return transcript_text

    transcript_file = os.path.join(folder_name, "transcript.txt")
    with open(transcript_file, "w", encoding="utf-8") as f:
        f.write(transcript_text)
    print(f"[+] Saved transcript: {transcript_file}")

    # 3. Generate AI Summary from Transcript
    success, summary_content = generate_ai_summary(transcript_text, raw_title)
    if not success:
        return summary_content
    
    summary_file = os.path.join(folder_name, "summary.md")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(summary_content)
    print(f"[+] Saved AI Summary: {summary_file}")

    # 4. Download video and subtitles (subtitles maintained for fallback)
    ydl_download_opts = {
        "outtmpl": os.path.join(folder_name, "%(title)s.%(ext)s"),
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "merge_output_format": "webm/mp4",
        "quiet": False,
    }

    with yt_dlp.YoutubeDL(ydl_download_opts) as ydl:
        try:
            download_info = ydl.extract_info(url, download=True)
            video_file = ydl.prepare_filename(download_info)
        except Exception as e:
            print(f"[-] Error downloading video: {e}")
            return f"Error downloading video: {e}"

    print(f"[+] Download complete: {video_file}")

    # 5. Extract screenshots with FFmpeg
    output_pattern = os.path.join(folder_name, IMAGE_NAME_FORMAT)

    ffmpeg_cmd = [
        "ffmpeg",
        "-i",
        video_file,
        "-vf",
        "fps=1/5,drawbox=x=iw*0.65:y=0:w=iw*0.35:h=ih*0.5:color=black:t=fill,select='not(n)+gt(scene\\,0.05)'",
        "-fps_mode",
        "vfr",
        output_pattern,
    ]

    print("[+] Extracting screenshots with FFmpeg...")
    try:
        subprocess.run(ffmpeg_cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[-] FFmpeg error: {e}")
        return f"FFmpeg error: {e}"

    print(f"[+] Finished processing: {folder_name}\n")
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Download YouTube videos, extract slide screenshots, and generate AI topic summaries."
    )
    parser.add_argument("urls", nargs="+", help="One or more YouTube video URLs.")
    parser.add_argument(
        "-o",
        "--output-dir",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "output"),
        help="Directory to store results in (default: 'output' folder inside the repository).",
    )

    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    if len(TODO) > 0:
        print("\n---------- TODOs: ----------")
        for item in TODO:
            print(f"- {item}")
        print("----------------------------\n")
        time.sleep(2 * len(TODO))

    has_errors = False
    results = []
    for url in args.urls:
        error = process_video(url, args.output_dir)
        results.append((url, error))
        if error is not None:
            has_errors = True

    print("\n---------- RESULTS ----------\n")
    if not has_errors:
        print("All videos processed successfully.")
    else:
        for result in results:
            url, error = result
            if error is not None:
                print(f"ERROR {url}:  {error}")


if __name__ == "__main__":
    main()
