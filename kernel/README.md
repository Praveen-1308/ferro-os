# FerroOS Bare-Metal Microkernel (Track 2)

`ferro-kernel` is an experimental `#![no_std]` 64-bit microkernel written entirely in Rust from scratch for x86_64 architectures.

This represents **Track 2** of the FerroOS Master Plan: building a pure-Rust bare-metal kernel in parallel with the production-ready FerroOS Linux distribution (Track 1).

---

## Architectural Highlights

- **`#![no_std]` & `#![no_main]`**: Zero runtime or OS dependencies. Pure freestanding x86-64 executable.
- **VGA Text Driver (`0xB8000`)**: Memory-mapped 80x25 terminal with automatic scrolling, colors, and `print!`/`println!` formatting macros.
- **UART 16550 Serial Driver (`0x3F8`)**: Headless logging via COM1 for virtualized environments and automated CI testing.
- **Global Descriptor Table (GDT) & TSS**: 64-bit kernel code segments with dedicated Interrupt Stack Table (IST) preventing triple-fault CPU resets on stack overflow.
- **Interrupt Descriptor Table (IDT)**: Handlers for hardware exceptions (breakpoint, double fault, page fault, GPF).
- **Dual 8259 PIC**: Hardware IRQ routing for PIT timer (IRQ0) and PS/2 keyboard (IRQ1).
- **Dynamic Memory Allocation**: Integrated `linked_list_allocator::LockedHeap` enabling `alloc::vec::Vec`, `alloc::string::String`, and `alloc::boxed::Box`.
- **Linux x86_64 ABI Syscall Compatibility**: Dispatches standard syscalls (`sys_write`, `sys_read`, `sys_getpid`, `sys_exit`, `sys_uname`, `sys_brk`) allowing `ferro-core` binaries to run directly against the microkernel.
- **Task Scheduler**: Round-robin cooperative/preemptive scheduler and Process Control Block (PCB).

---

## Building and Running

### Prerequisites
- Rust Nightly toolchain: `rustup toolchain install nightly`
- Bare-metal target: `rustup target add x86_64-unknown-none`
- QEMU (optional, for emulation): `brew install qemu` or `apt-get install qemu-system-x86`

### Commands
```bash
# Check syntax and types
make check

# Build release ELF kernel (55 KB)
make release

# Run in QEMU with serial console
make run

# Run headless (serial only)
make run-headless
```
