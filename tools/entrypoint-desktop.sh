#!/bin/bash
set -e

echo "=========================================================="
echo "  Starting FerroOS Modern Desktop Environment"
echo "=========================================================="

# Clean up stale X locks
rm -f /tmp/.X0-lock /tmp/.X11-unix/X0

# 1. Start Xvfb (Virtual Framebuffer)
echo "--> Launching Xvfb display :0 at 1280x800x24..."
Xvfb :0 -screen 0 1280x800x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!

# Wait for X display to be ready
sleep 1
for i in $(seq 1 30); do
    if xset q >/dev/null 2>&1; then
        echo "--> Xvfb display :0 is ready."
        break
    fi
    sleep 0.2
done

# 2. Start x11vnc server
echo "--> Launching x11vnc on port 5900..."
x11vnc -display :0 -nopw -listen 127.0.0.1 -forever -shared -rfbport 5900 -quiet &

# 3. Start noVNC websockify bridge on port 6080
echo "--> Launching noVNC Web Gateway on port 6080..."
websockify --web /usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900 &

# 4. Start XFCE4 Modern Desktop Session
echo "--> Launching XFCE4 Modern Desktop Session..."
export DISPLAY=:0
exec dbus-launch --exit-with-session startxfce4
