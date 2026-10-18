FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    qemu-system-x86 \
    novnc \
    websockify \
    net-tools \
    procps \
    && rm -rf /var/lib/apt/lists/*

RUN if [ -f "/usr/share/novnc/vnc.html" ]; then ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html; fi

WORKDIR /ferro
COPY build_out/vmlinuz /ferro/vmlinuz
COPY build_out/initramfs.cpio.gz /ferro/initramfs.cpio.gz

EXPOSE 6080

CMD ["sh", "-c", "qemu-system-x86_64 -kernel /ferro/vmlinuz -initrd /ferro/initramfs.cpio.gz -append 'console=ttyS0 quiet vga=792' -vga std -vnc 0.0.0.0:0 -m 512M -no-reboot & sleep 1 && websockify --web /usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900"]
