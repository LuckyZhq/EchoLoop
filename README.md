# IELTS Study

Learn English for the IELTS from real videos and articles, in your own language.

Paste a YouTube, Bilibili or TED link and IELTS Study gives you bilingual subtitles with the translation written
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
- **Word review** – saved words come back as fill-in-the-blank cards from the sentence you met them in, with the
  original audio, scheduled with a simplified SM-2 (like Anki).
- **Close reading** – paste an English article for sentence-by-sentence translation and marked key words.
- **Study plan** – four stages from beginner to band 7+, daily goals that fill in as you study, streaks, progress charts,
  and a daily new-word quota that follows your exam date.

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
| `IELTS_LIBRARY` | where videos, articles and your progress are kept (default `library/`) |

## Your data

Everything stays in the project folder:

- `library/` – videos, subtitles, dictation results, saved words, your level and study log; `library/kept/` holds
  the sentences (text and a short audio clip) kept from deleted videos
- `articles/` – pasted articles
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
