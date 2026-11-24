# Third-party notices

IELTS Study uses the following data and software. Each keeps its own license.

## Data

| Name | Used for | License |
|---|---|---|
| [ECDICT](https://github.com/skywind3000/ECDICT) | English–Chinese dictionary, English definitions (from WordNet), word frequency and exam word lists. Downloaded on first run, not included in this repository | MIT |
| [OpenAI Whisper](https://github.com/openai/whisper) models | Speech recognition (downloaded on first use) | MIT |
| IELTS-style speaking questions and writing tasks | Practice prompts in `speaking_questions.json` and `writing_tasks.json`: original, written in the style of the test, not copied from past papers; chart data is invented | (this project) |
| [spaCy en_core_web_sm](https://github.com/explosion/spacy-models) | Sentence and word analysis | MIT |
| [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) ([ONNX export](https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX)) | Neural read-aloud voices (downloaded on first use) | Apache-2.0 |

## Software

| Name | Used for | License |
|---|---|---|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Downloading videos and subtitles | Unlicense |
| [mlx-whisper](https://github.com/ml-explore/mlx-examples) | Speech recognition on Apple Silicon | MIT |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) / [CTranslate2](https://github.com/OpenNMT/CTranslate2) | Speech recognition on other computers | MIT |
| [Argos Translate](https://github.com/argosopentech/argos-translate) | Offline subtitle translation | MIT |
| [spaCy](https://github.com/explosion/spaCy) | Natural language processing | MIT |
| [OpenCC](https://github.com/BYVoid/OpenCC) (opencc-python-reimplemented) | Simplified ↔ Traditional Chinese (Taiwan wording) | Apache-2.0 |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | Bundled FFmpeg for audio and video | BSD-2-Clause (FFmpeg itself: LGPL/GPL) |
| [Deno](https://github.com/denoland/deno) | JavaScript runtime used by yt-dlp for some sites | MIT |
| [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) / [ONNX Runtime](https://github.com/microsoft/onnxruntime) | Running the read-aloud model | MIT |
| [segno](https://github.com/heuer/segno) | QR code for opening the app on a phone | BSD-3-Clause |
| [espeak-ng](https://github.com/espeak-ng/espeak-ng) (via espeakng-loader) / [phonemizer](https://github.com/bootphon/phonemizer) | Turning English text into British or American pronunciation for the voice model | GPL-3.0 |

Interface translations other than English and Chinese were generated with a large language model (DeepSeek).
