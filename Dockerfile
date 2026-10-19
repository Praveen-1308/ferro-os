FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV DISPLAY=:0

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    net-tools \
    procps \
    dbus-x11 \
    xfce4-session \
    xfwm4 \
    xfdesktop4 \
    xfce4-panel \
    xfce4-settings \
    xfce4-terminal \
    thunar \
    mousepad \
    galculator \
    xfce4-taskmanager \
    adwaita-icon-theme \
    fonts-dejavu-core \
    python3 \
    python3-tk \
    sudo \
    x11-xserver-utils \
    && rm -rf /var/lib/apt/lists/*

RUN if [ -f "/usr/share/novnc/vnc.html" ]; then ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html; fi

# Create ferro user with passwordless sudo
RUN useradd -m -s /bin/bash -u 1000 ferro && \
    echo "ferro ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Copy setup scripts and entrypoint
COPY tools/entrypoint-desktop.sh /usr/local/bin/entrypoint-desktop.sh
RUN chmod +x /usr/local/bin/entrypoint-desktop.sh

COPY tools/desktop-setup/ /etc/ferro-desktop/
RUN chmod +x /etc/ferro-desktop/install.sh && bash /etc/ferro-desktop/install.sh

USER ferro
WORKDIR /home/ferro

EXPOSE 6080

CMD ["/usr/local/bin/entrypoint-desktop.sh"]
