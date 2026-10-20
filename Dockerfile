FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV DISPLAY=:0
ENV QT_X11_NO_MITSHM=1
ENV XDG_CURRENT_DESKTOP=KDE
ENV XDG_SESSION_DESKTOP=KDE
ENV KDE_FULL_SESSION=true

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    net-tools \
    procps \
    dbus-x11 \
    kde-plasma-desktop \
    plasma-workspace \
    kwin-x11 \
    dolphin \
    konsole \
    kate \
    kcalc \
    systemsettings \
    breeze \
    breeze-icon-theme \
    breeze-cursor-theme \
    mesa-utils \
    libgl1-mesa-dri \
    mesa-vulkan-drivers \
    vulkan-tools \
    libgbm1 \
    libdrm2 \
    glmark2-x11 \
    sudo \
    x11-xserver-utils \
    fonts-noto-core \
    fonts-noto-color-emoji \
    fonts-dejavu-core \
    maim \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN if [ -f "/usr/share/novnc/vnc.html" ]; then ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html; fi

# Create ferro user with passwordless sudo
RUN useradd -m -s /bin/bash -u 1000 ferro && \
    echo "ferro ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers && \
    echo "ferro:ferro" | chpasswd

# Copy entrypoint script
COPY tools/entrypoint-desktop.sh /usr/local/bin/entrypoint-desktop.sh
RUN chmod +x /usr/local/bin/entrypoint-desktop.sh

# Copy FerroOS core utilities (zero-copy cp, gamemode)
COPY --from=ferro-os-server:latest /usr/local/bin/ferro-core /usr/local/bin/ferro-core
RUN ln -sf /usr/local/bin/ferro-core /usr/local/bin/gamemode

USER ferro
WORKDIR /home/ferro

# Set up user directories and default KDE configuration
RUN mkdir -p /home/ferro/Desktop /home/ferro/Documents /home/ferro/Downloads /home/ferro/.config

EXPOSE 6080

CMD ["/usr/local/bin/entrypoint-desktop.sh"]
