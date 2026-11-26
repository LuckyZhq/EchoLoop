#!/bin/zsh
# Builds the desktop launcher: ~/Desktop/EchoLoop.app
# Double-clicking the app starts EchoLoop in the background (no Terminal window) and opens the page.
# Rebuild after moving the project folder:  zsh assets/build_app.sh
set -e
HERE="${0:A:h}"
PROJECT="${HERE:h}"
APP="${1:-$HOME/Desktop/EchoLoop.app}"

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$HERE/EchoLoop.icns" "$APP/Contents/Resources/EchoLoop.icns"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>EchoLoop</string>
  <key>CFBundleDisplayName</key><string>EchoLoop</string>
  <key>CFBundleIdentifier</key><string>local.echoloop.launcher</string>
  <key>CFBundleExecutable</key><string>EchoLoop</string>
  <key>CFBundleIconFile</key><string>EchoLoop</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/EchoLoop" <<SCRIPT
#!/bin/zsh
APP_DIR="$PROJECT"
SCRIPT
cat >> "$APP/Contents/MacOS/EchoLoop" <<'SCRIPT'
URL="http://127.0.0.1:${ECHOLOOP_PORT:-${IELTS_PORT:-8765}}/"
LOG="$APP_DIR/data/server.log"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

running() { curl -s -I --max-time 2 "$URL" 2>/dev/null | grep -qiE '^server: (echoloop|ielts-study)'; }
# Up to date = the server runs the code that is on disk now (older builds have no /api/version).
fresh() { curl -s --max-time 2 "${URL}api/version" 2>/dev/null | grep -q '"stale": false'; }
alert() { osascript -e "display alert \"EchoLoop\" message \"$1\" as critical" >/dev/null 2>&1; }

# Already running the current code: just open the page. An older server is restarted by `echoloop` below.
if running && fresh; then open "$URL"; exit 0; fi

[[ -d "$APP_DIR" ]] || { alert "找不到项目文件夹：$APP_DIR。移动过文件夹的话，在新位置运行 zsh assets/build_app.sh 重新生成启动器。"; exit 1; }
command -v uv >/dev/null || { alert "找不到 uv，请先安装 uv。"; exit 1; }

mkdir -p "$APP_DIR/data"
[[ -f "$LOG" && $(stat -f %z "$LOG") -gt 2000000 ]] && mv -f "$LOG" "$LOG.old"
cd "$APP_DIR"
# Start in the background, detached from this launcher, and wait for the page to answer.
PYTHONUNBUFFERED=1 ECHOLOOP_NO_BROWSER=1 nohup uv run echoloop >> "$LOG" 2>&1 < /dev/null &!
for i in {1..120}; do
  if running && fresh; then open "$URL"; exit 0; fi
  sleep 0.5
done
alert "启动超时（60 秒）。日志在：$LOG"
exit 1
SCRIPT
chmod +x "$APP/Contents/MacOS/EchoLoop"
touch "$APP"   # make Finder pick up the new icon
echo "built $APP"
