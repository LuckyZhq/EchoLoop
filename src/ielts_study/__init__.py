"""IELTS Study — paste a video link, practise IELTS listening and vocabulary with bilingual subtitles."""


def main() -> None:
    import os
    import sys

    from .server import main as serve, stop

    if "--stop" in sys.argv:
        raise SystemExit(stop())
    if "--translate-ui" in sys.argv:  # generate an interface language table with the configured API
        from .ui_translate import main as translate_ui

        i = sys.argv.index("--translate-ui")
        raise SystemExit(translate_ui(sys.argv[i + 1] if i + 1 < len(sys.argv) else "all"))
    serve(open_browser="--no-browser" not in sys.argv and not (os.environ.get("IELTS_NO_BROWSER") or os.environ.get("WHATSUB_NO_BROWSER")),
          restart="--restart" in sys.argv)
