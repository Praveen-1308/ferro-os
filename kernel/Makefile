.PHONY: all build check release run run-headless clean

TARGET = x86_64-unknown-none
KERNEL_BIN = target/$(TARGET)/release/ferro-kernel

all: release

check:
	cargo +nightly check --target $(TARGET)

build:
	cargo +nightly build --target $(TARGET)

release:
	cargo +nightly build --release --target $(TARGET)

run: release
	@if command -v qemu-system-x86_64 >/dev/null 2>&1; then \
		qemu-system-x86_64 -kernel $(KERNEL_BIN) -serial stdio -m 512M; \
	else \
		echo "QEMU not installed. Install via 'brew install qemu' or 'apt-get install qemu-system-x86'."; \
	fi

run-headless: release
	@if command -v qemu-system-x86_64 >/dev/null 2>&1; then \
		qemu-system-x86_64 -kernel $(KERNEL_BIN) -serial stdio -display none -m 512M; \
	else \
		echo "QEMU not installed."; \
	fi

clean:
	cargo clean
