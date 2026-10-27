FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    qemu-system-x86 \
    novnc \
    websockify \
    procps \
    curl \
    && rm -rf /var/lib/apt/lists/*
RUN if [ -f "/usr/share/novnc/vnc.html" ]; then ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html; fi
EXPOSE 6080
WORKDIR /os
COPY start.sh /start.sh
RUN chmod +x /start.sh
CMD ["/start.sh"]
