# IELTS Study

Learn English for the IELTS from real videos and articles, in your own language.

Paste a YouTube, Bilibili, TED or podcast link and IELTS Study gives you bilingual subtitles with the translation written
under each phrase, the spoken word highlighted, key phrases and IELTS-level words marked for *your* level,
sentence-by-sentence dictation, and spaced-repetition review of the words you save. It runs on your own computer:
no account, no uploads.

[简体中文说明](README.zh-CN.md)

## What you can do

- **Video listening** – subtitles split into words and phrases with the translation underneath, the word being spoken
  lit up, sentence loop, auto-pause, 0.6×–1.5× speed. Videos without English subtitles are transcribed locally with Whisper.
- **Dictation** – type what you hear; answers are compared word by word (contractions, numbers and UK/US spellings
  count as equal). Sentences below 90 % go to *Mistakes*, where you redo them in place with the original audio.
  Deleting a video keeps its mistakes and the sentences your saved words came from, with a short clip of each.
- **Level test** – read three short passages, click the words you don't know, answer a short spot-check.
  You get an estimated vocabulary size and a rough IELTS band; from then on only the words between your level and your
  target are marked.
- **Word books** – pick a list (the 3,000 most common words, IELTS, TOEFL; for Chinese learners also CET-4, CET-6
  and the postgraduate exam) and new words arrive in Word review every day: one click skips a word you know, the
  others are learned with an example sentence from your own videos and articles, or one written by your API.
  Words more frequent than your tested vocabulary size are skipped. The lists come from ECDICT's exam tags.
- **Word review** – saved words come back as fill-in-the-blank cards from the sentence you met them in, with the
  original audio, scheduled with a simplified SM-2 (like Anki).
- **Close reading** – graded passages by level (CET-4, CET-6 for Chinese learners; IELTS 5.5, 6.5, 7+), each translated
  sentence by sentence with key words marked. The built-in passages are original texts modelled on each exam's topics,
  length and difficulty; your API can write more at any level, on a topic you choose. Or paste your own article.
- **Speaking** – *Shadowing*: hear a sentence (the original audio from your videos, or the neural voice for passage
  sentences), say it, and see word by word what was recognised, with your pace against the original. *Mock test*:
  IELTS-style Part 1, 2 (with a one-minute preparation timer and cue card) and 3 questions, read out by the examiner
  voice; your answer is recorded, transcribed, and measured (words per minute, pauses, fillers, unclear words). With an
  API, it estimates the four speaking bands and gives corrections, better phrasing and a sample answer. Recordings are
  recognised on your computer.
- **Writing** – Task 2 essays, Task 1 charts (bar, line, table) and General Training letters, with a timer, word count
  and auto-saved drafts, or paste your own question. Your API marks it against the four writing criteria, corrects it
  sentence by sentence (highlighted in your text), suggests better words and rewrites it at Band 8 keeping your ideas.
  Every marked essay is kept, so you can compare over time. The questions are original, in the style of the test.
- **Study plan** – four stages from beginner to band 7+, daily goals that fill in as you study, streaks, progress charts,
  and a daily new-word quota that follows your exam date.

## Where videos and podcasts can come from

| Source | Works | Notes |
|---|---|---|
| YouTube | yes | uses the video's English subtitles when it has them |
| Bilibili | yes | members-only videos (most 番剧) give only a short preview without signing in; the library marks them |
| TED | yes | English subtitles included |
| Apple Podcasts | yes, episode links | the latest 200 episodes of a show; covers almost every public podcast (BBC 6 Minute English, TED Talks Daily, All Ears English…) |
| 小宇宙 (Xiaoyuzhou) | yes, episode links | |
| Spreaker, Internet Archive | yes | |
| Direct audio links (.mp3, .m4a) | yes | e.g. the download link of a podcast episode |
| Vimeo | no | now requires signing in |
| Spotify, Netflix and other DRM services | no | protected, cannot be downloaded |

Podcasts have no subtitles, so they are transcribed locally with Whisper (see Speech recognition).
Any other site [yt-dlp supports](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) may work too.

## Languages

Interface and translations in **16 languages**: 简体中文, 繁體中文 (Taiwan), English (English-only explanations),
Español, Português, Français, Deutsch, 日本語, 한국어, Tiếng Việt, Bahasa Indonesia, ไทย, Türkçe, Русский, العربية
(right-to-left) and हिन्दी. Pick yours on the home page.

| | Chinese learners | Other languages |
|---|---|---|
| Subtitle translation | API, or offline (Argos) | API with phrase-by-phrase translation (any language), or offline Argos (model downloaded on first use) |
| Word meanings | offline English–Chinese dictionary (ECDICT) | API, cached per language; English definitions offline |
| Word-by-word glosses | yes | phrase-by-phrase translation instead |

An API is optional but gives the best translations: any OpenAI-compatible provider works (DeepSeek, OpenAI, Gemini,
Grok, Qwen, Kimi, GLM, Doubao or your own endpoint). Only subtitle text is sent, and only to the provider you choose.

## Install

You need [uv](https://docs.astral.sh/uv/) (it installs the right Python and all dependencies) and git.

**macOS / Linux**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/<you>/IELTS-study.git
cd IELTS-study
uv run ielts-study
```

**Windows** (PowerShell)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
git clone https://github.com/<you>/IELTS-study.git
cd IELTS-study
uv run ielts-study
```

Your browser opens <http://127.0.0.1:8765>. The first start installs dependencies and downloads the offline dictionary
(ECDICT, about 66 MB, checksum-verified), so it takes a few minutes; later starts take seconds.

Afterwards you can start it by double-clicking `scripts/IELTS-Study.bat` (Windows) or running `scripts/start.sh`
(macOS / Linux). On a Mac, `zsh assets/build_app.sh` puts an IELTS-study app on your desktop.

### Read-aloud voice

Words and sentences are read aloud by a neural voice model, [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M), run on your
computer: British (female or male) for IELTS, American for CET. Its model (about 165 MB) is downloaded from Hugging
Face the first time something is read aloud (hf-mirror.com is tried if Hugging Face can't be reached; an interrupted
download continues where it stopped); until then, and for the Australian accent, your system's voice is used.
Choose the voice and accent in Settings → Playback.

### Speech recognition

Used when a video has no human-made English subtitles, and for your speaking-practice recordings. Choose the method
and model size in Settings → Speech recognition.

| Computer | Engine | "Auto" model |
|---|---|---|
| Mac with Apple Silicon | [mlx-whisper](https://github.com/ml-explore/mlx-examples) (GPU) | large-v3-turbo (≈1.6 GB) |
| Windows / Linux with an NVIDIA GPU | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CUDA) | large-v3-turbo |
| Any other computer | faster-whisper (CPU) | small.en (≈0.5 GB) |

So the first video doesn't wait for a 1.6 GB download, "Auto" starts with the small model (≈0.5 GB) and fetches the
large one in the background; new imports use it as soon as it is there. You can also pick base, small, medium or
large yourself.

**Cloud recognition** (optional): any OpenAI-compatible `/audio/transcriptions` endpoint with word timestamps, such as
OpenAI `whisper-1` or Groq `whisper-large-v3-turbo`, with your own API key. It gives computers without a graphics card
large-model accuracy; the audio is sent as small MP3 pieces, and if the service can't be reached the local model is
used. `IELTS_WHISPER` still overrides the local model.

### Phone access

Settings → Phone access lets a phone on the same Wi-Fi open the app (review, dictation, reading). After a restart the
server listens on the local network, and a QR code carries an access key: phones without it are refused, and API keys,
backups and settings can only be changed on the computer. Browsers only allow the microphone on HTTPS pages, so
speaking practice stays on the computer.

### Backups

Settings → Backup downloads a zip of your learning record (saved words, review history, mistakes, dictation scores,
articles, speaking and writing history, kept clips; videos optional, API keys never) and restores one: files it
replaces are first copied to `data/backups/`. It can also back up once a day into a folder you choose, such as an
iCloud Drive, OneDrive, Dropbox or Nutstore folder, keeping the latest copies.

## Commands

```bash
uv run ielts-study                 # start (opens the browser)
uv run ielts-study --no-browser    # start without opening the browser
uv run ielts-study --stop          # stop the server running in the background
uv run ielts-study --restart       # restart with the latest code
uv run ielts-study --translate-ui es   # generate / complete an interface language with your API ("all" for every language)
```

The pages show a "restart" banner when the code on disk is newer than the running server.

| Environment variable | Meaning |
|---|---|
| `IELTS_PORT` | port (default 8765) |
| `IELTS_WHISPER` | local speech-recognition model (overrides Settings) |
| `IELTS_LIBRARY` | where videos and your progress are kept (default `library/`) |
| `IELTS_ARTICLES` | where reading articles are kept (default `articles/`) |

## Your data

Everything stays in the project folder:

- `library/` – videos, subtitles, dictation results, saved words, your level and study log; `library/kept/` holds
  the sentences (text and a short audio clip) kept from deleted videos
- `articles/` – pasted articles and the graded passages you have opened or had written
- `library/speaking/`, `library/writing/` – speaking recordings and scores, marked essays
- `data/` – the dictionary, its index, the voice model, and your settings: API (`settings.json`), speech recognition
  (`asr.json`), phone access (`network.json`), backup folder (`backup.json`). Keys stay here and are never backed up

None of these folders are tracked by git.

## Development

```bash
uv run pytest
```

Interface translations live in `src/ielts_study/i18n/<language>.json`. English is written by hand; the other languages
were generated from it by an LLM, so corrections from native speakers are very welcome — edit the JSON file directly.
After adding interface text, run `uv run ielts-study --translate-ui all` to fill the new strings (missing strings show
in English until then).

## Notes

- Downloading videos is for personal study. Respect each site's terms of service and copyright.
- The IELTS band shown after the level test is a rough estimate from vocabulary size only, not an official score.
- Third-party data and libraries: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License

[MIT](LICENSE). Third-party data and libraries keep their own licenses ([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
