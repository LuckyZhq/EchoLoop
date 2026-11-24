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

Used only when a video has no human-made English subtitles. The model is downloaded on first use.

| Computer | Engine | Default model |
|---|---|---|
| Mac with Apple Silicon | [mlx-whisper](https://github.com/ml-explore/mlx-examples) (GPU) | large-v3-turbo (≈1.6 GB) |
| Windows / Linux with an NVIDIA GPU | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CUDA) | large-v3-turbo |
| Any other computer | faster-whisper (CPU) | small.en (≈0.5 GB) |

Set `IELTS_WHISPER` to choose another model.

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
| `IELTS_WHISPER` | speech-recognition model |
| `IELTS_LIBRARY` | where videos and your progress are kept (default `library/`) |
| `IELTS_ARTICLES` | where reading articles are kept (default `articles/`) |

## Your data

Everything stays in the project folder:

- `library/` – videos, subtitles, dictation results, saved words, your level and study log; `library/kept/` holds
  the sentences (text and a short audio clip) kept from deleted videos
- `articles/` – pasted articles and the graded passages you have opened or had written
- `data/` – the dictionary, its index and your API settings (the API key is stored with owner-only permissions)

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
