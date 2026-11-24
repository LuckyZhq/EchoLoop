#!/bin/zsh
# Builds the desktop launcher: ~/Desktop/IELTS-study.app
# Double-clicking the app starts IELTS-study in the background (no Terminal window) and opens the page.
# Rebuild after moving the project folder:  zsh assets/build_app.sh
set -e
HERE="${0:A:h}"
PROJECT="${HERE:h}"
APP="${1:-$HOME/Desktop/IELTS-study.app}"

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$HERE/IELTS-study.icns" "$APP/Contents/Resources/IELTS-study.icns"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>IELTS-study</string>
  <key>CFBundleDisplayName</key><string>IELTS-study</string>
  <key>CFBundleIdentifier</key><string>local.ielts-study.launcher</string>
  <key>CFBundleExecutable</key><string>IELTS-study</string>
  <key>CFBundleIconFile</key><string>IELTS-study</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/IELTS-study" <<SCRIPT
#!/bin/zsh
APP_DIR="$PROJECT"
SCRIPT
cat >> "$APP/Contents/MacOS/IELTS-study" <<'SCRIPT'
URL="http://127.0.0.1:${IELTS_PORT:-8765}/"
LOG="$APP_DIR/data/server.log"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

running() { curl -s -I --max-time 2 "$URL" 2>/dev/null | grep -qi '^server: ielts-study'; }
alert() { osascript -e "display alert \"IELTS-study\" message \"$1\" as critical" >/dev/null 2>&1; }

# Already running: just open the page.
if running; then open "$URL"; exit 0; fi

[[ -d "$APP_DIR" ]] || { alert "找不到项目文件夹：$APP_DIR。移动过文件夹的话，在新位置运行 zsh assets/build_app.sh 重新生成启动器。"; exit 1; }
command -v uv >/dev/null || { alert "找不到 uv，请先安装 uv。"; exit 1; }

mkdir -p "$APP_DIR/data"
[[ -f "$LOG" && $(stat -f %z "$LOG") -gt 2000000 ]] && mv -f "$LOG" "$LOG.old"
cd "$APP_DIR"
# Start in the background, detached from this launcher, and wait for the page to answer.
PYTHONUNBUFFERED=1 IELTS_NO_BROWSER=1 nohup uv run ielts-study >> "$LOG" 2>&1 < /dev/null &!
for i in {1..120}; do
  if running; then open "$URL"; exit 0; fi
  sleep 0.5
done
alert "启动超时（60 秒）。日志在：$LOG"
exit 1
SCRIPT
chmod +x "$APP/Contents/MacOS/IELTS-study"
touch "$APP"   # make Finder pick up the new icon
echo "built $APP"
