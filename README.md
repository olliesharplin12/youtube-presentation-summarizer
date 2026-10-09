# YouTube Slide Extractor & AI Summarizer

An automated Python pipeline that downloads YouTube presentation videos, extracts unique slide images (with dynamic webcam overlay masking), retrieves full video transcripts, and generates structured AI topic summaries using Google Gemini 1.5 Flash.

## Features

- **Batch Processing:** Submit single or multiple YouTube links in a single command.
- **Dynamic Slide Extraction:** Uses FFmpeg scene detection and box masking to isolate presentation slides automatically.
- **Resilient Transcripts:** Retrieves captions directly via `youtube-transcript-api`.
- **AI Summarization:** Connects to Google Gemini via `google-genai` with exponential backoff retries to gracefully handle temporary API 503/429 capacity spikes.
- **Organized Storage:** Automatically generates structured, reverse-dated output directories formatted as `YYMMDD - Video Title`.

---

## Prerequisites

1. **Python 3.8+**
2. **FFmpeg** installed and available on your system `PATH`:
   - **Windows:** `winget install ffmpeg` (or download from [ffmpeg.org](https://ffmpeg.org/))
   - **macOS:** `brew install ffmpeg`
   - **Linux:** `sudo apt install ffmpeg`
3. **Gemini API Key**:
   - Sign in to [Google AI Studio](https://aistudio.google.com/api-keys) and click Get API key to generate a key.
   - In CMD, run: `set GEMINI_API_KEY=your_actual_api_key_here`
   - Restart the Shell

---

## Installation

Install all required Python dependencies:

```bash
pip install yt-dlp google-genai youtube-transcript-api curl-cffi
