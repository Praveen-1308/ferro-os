.PHONY: all initramfs iso clean run

all: iso

initramfs:
	@chmod +x build-initramfs.sh
	./build-initramfs.sh

iso: initramfs
	@chmod +x build-iso.sh
	./build-iso.sh

run:
	@if command -v qemu-system-x86_64 >/dev/null 2>&1; then \
		qemu-system-x86_64 -cdrom build/ferro-os-3.0.0.iso -m 512M -serial mon:stdio; \
	else \
		echo "QEMU not found. Install via 'brew install qemu' or 'apt-get install qemu-system-x86'."; \
	fi

clean:
	rm -rf build/
