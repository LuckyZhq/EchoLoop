import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echoloop import media
from echoloop.config import LIBRARY_DIR


def main():
    parser = argparse.ArgumentParser(description="Remove stray timing lines from stored English subtitle text.")
    parser.add_argument("video_id")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    path = LIBRARY_DIR / args.video_id / "data.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = []
    for cue in data["cues"]:
        if media._TS_LINE.search(cue["text"]):
            cleaned = media._clean_text(cue["text"])
            changed.append((cue["text"], cleaned))
            cue["text"] = cleaned
            cue.pop("marks", None)
            cue.pop("notes", None)
    for before, after in changed[:5]:
        print(f"- {before[:90]}\n+ {after[:90]}")
    print(f"{len(changed)} of {len(data['cues'])} cues affected")
    if args.apply and changed:
        backup = path.with_name("data.before-timestamp-clean.json")
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"written; backup at {backup}")


main()
