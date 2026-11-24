"""IELTS Study — paste a video link, practise IELTS listening and vocabulary with bilingual subtitles."""


def main() -> None:
    import os
    import sys

    from .server import main as serve, stop

    if "--stop" in sys.argv:
        raise SystemExit(stop())
    serve(open_browser="--no-browser" not in sys.argv and not (os.environ.get("IELTS_NO_BROWSER") or os.environ.get("WHATSUB_NO_BROWSER")),
          restart="--restart" in sys.argv)
