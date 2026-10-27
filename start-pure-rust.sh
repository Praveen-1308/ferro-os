#!/usr/bin/env bash
# start-pure-rust.sh - 1-Click Pure-Rust (<3MB) FerroOS Launcher for macOS
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Resize Terminal window to a calibrated 10-inch frame on 13-inch Mac screen
if command -v osascript >/dev/null 2>&1; then
    osascript -e '
    tell application "Terminal"
        if (count of windows) > 0 then
            set bounds of front window to {150, 90, 1110, 690}
        end if
    end tell' 2>/dev/null || true
fi

clear

# 2. Display pure-Rust FerroOS Welcome Banner
cat << 'EOF'
  _______                    ____   _____ 
 |  ____|                   / __ \ / ____|
 | |__ ___ _ __ _ __ ___   | |  | | (___  
 |  __/ _ \ '__| '__/ _ \  | |  | |\___ \ 
 | | |  __/ |  | | | (_) | | |__| |____) |
 |_|  \___|_|  |_|  \___/   \____/|_____/ 

 🦀 FerroOS Pure-Rust OS (2.8 MB Autonomous Edition)
 100% Memory-Safe Rust Userland • Zero C Daemons • 10-Inch Window
================================================================================
 Quick Commands You Can Type:
   • uname -a         -> View OS kernel identity
   • free             -> View memory footprint (~14 MB idle!)
   • ps               -> View processes running
   • df               -> View disk usage
   • uptime           -> View system uptime
   • help             -> View all built-in commands
   • exit             -> Return to your Mac
================================================================================
EOF

# 3. Launch the pure-Rust shell directly
exec "$SCRIPT_DIR/target/release/ferro-core" sh
