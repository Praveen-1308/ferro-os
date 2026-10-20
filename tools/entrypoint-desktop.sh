#!/bin/bash
set -e

echo "=========================================================="
echo "  Starting FerroOS Official KDE Plasma Desktop Environment"
echo "=========================================================="

# Clean up stale X locks and sockets
rm -f /tmp/.X0-lock /tmp/.X11-unix/X0

# Set up runtime directory
export XDG_RUNTIME_DIR=/tmp/runtime-ferro
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

export DISPLAY=:0
export QT_X11_NO_MITSHM=1
export XDG_CURRENT_DESKTOP=KDE
export XDG_SESSION_DESKTOP=KDE
export KDE_FULL_SESSION=true
export QT_QPA_PLATFORM=xcb

# Disable KWin compositing crash prompts or software fallbacks
mkdir -p /home/ferro/.config
if [ ! -f /home/ferro/.config/kwinrc ]; then
cat << 'EOF' > /home/ferro/.config/kwinrc
[Compositing]
Enabled=true
Backend=OpenGL
OpenGLIsUnsafe=false
EOF
fi

# Disable screenlocker completely for container environment
cat << 'EOF' > /home/ferro/.config/kscreenlockerrc
[Daemon]
Autolock=false
LockOnResume=false
Timeout=0
EOF


# 1. Start Xvfb (Virtual Framebuffer) at 1600x900
echo "--> Launching Xvfb display :0 at 1600x900x24..."
Xvfb :0 -screen 0 1600x900x24 -ac +extension GLX +extension RENDER -noreset &
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

# 4. Start D-Bus session and launch standard KDE Plasma Desktop
echo "--> Launching genuine KDE Plasma Desktop session..."
exec dbus-run-session -- startplasma-x11
