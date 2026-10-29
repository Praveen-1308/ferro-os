#![no_std]
#![no_main]
#![feature(abi_x86_interrupt)]

extern crate alloc;

pub mod gdt;
pub mod interrupts;
pub mod memory;
pub mod process;
pub mod serial;
pub mod syscall;
pub mod vga;

use alloc::boxed::Box;
use alloc::string::String;
use alloc::vec::Vec;
use core::panic::PanicInfo;

#[no_mangle]
pub extern "C" fn _start() -> ! {
    // 1. Initialize Serial Port for headless QEMU logging
    serial::init_serial();
    serial_println!("==================================================");
    serial_println!("FerroOS Bare-Metal #![no_std] Microkernel Starting");
    serial_println!("==================================================");

    // 2. Initialize VGA Text Mode
    vga::WRITER.lock().clear_screen();
    println!(" _______ ____ _____ ");
    println!("| ____| / __ \\ / ____|");
    println!("| |__ ___ _ __ _ __ ___ | | | | (___ ");
    println!("| __/ _ \\ '__| '__/ _ \\ | | | |\\___ \\ ");
    println!("| | | __/ | | | | (_) | | |__| |____) |");
    println!("|_| \\___|_| |_| \\___/ \\____/|_____/ ");
    println!("");
    println!("FerroOS Bare-Metal Kernel v0.1.0 (x86_64-unknown-none)");

    // 3. Initialize Global Descriptor Table (GDT) and Task State Segment (TSS)
    gdt::init_gdt();
    serial_println!("[+] GDT & TSS initialized with double-fault IST stack");

    // 4. Initialize Interrupt Descriptor Table (IDT)
    interrupts::init_idt();
    serial_println!("[+] IDT configured with hardware exceptions");

    // 5. Initialize 8259 Programmable Interrupt Controller (PIC)
    unsafe {
        interrupts::PICS.lock().initialize();
    }
    serial_println!("[+] 8259 PIC initialized (IRQ 0-15 mapped)");

    // 6. Initialize Kernel Heap Allocator
    memory::init_heap();
    serial_println!("[+] Kernel Heap Allocator online (512 KiB)");

    // 7. Verify Dynamic Memory Allocation in bare-metal
    let heap_value = Box::new(42);
    let mut vec = Vec::new();
    for i in 0..10 {
        vec.push(i * 2);
    }
    let kernel_msg = String::from("Pure-Rust #![no_std] bare-metal dynamic allocation verified!");
    serial_println!("[+] Box: {}, Vec len: {}, Msg: '{}'", *heap_value, vec.len(), kernel_msg);
    println!("[OK] Heap test: Box({}), Vec({:?})", *heap_value, &vec[..4]);

    // 8. Verify Linux x86_64 ABI Syscall Dispatcher
    let test_msg = "[OK] Linux x86_64 ABI syscall dispatch verified (sys_write)\n";
    syscall::dispatch_syscall(
        syscall::table::SYS_WRITE,
        1, // stdout
        test_msg.as_ptr() as usize,
        test_msg.len(),
    );

    // 9. Display system ready status
    println!("");
    println!("System Status:");
    println!("  - Architecture: x86_64 bare-metal (long mode)");
    println!("  - Mode: #![no_std], zero OS dependencies");
    println!("  - Syscall ABI: Linux x86_64 ABI compliant");
    println!("  - Hardware Interrupts: Active (Timer & Keyboard)");
    println!("");
    println!("FerroOS Kernel is active and listening for hardware interrupts.");

    serial_println!("[+] Enabling hardware interrupts...");
    x86_64::instructions::interrupts::enable();

    // 10. Enter idle halt loop
    loop {
        x86_64::instructions::hlt();
    }
}

/// Custom Panic Handler for bare-metal `#![no_std]` environment
#[panic_handler]
fn panic(info: &PanicInfo) -> ! {
    vga::WRITER.lock().set_color(vga::Color::LightRed, vga::Color::Black);
    println!("\n[!] KERNEL PANIC: {}", info);
    serial_println!("\n[!] KERNEL PANIC: {}", info);

    loop {
        x86_64::instructions::hlt();
    }
}
