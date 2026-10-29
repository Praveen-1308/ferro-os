//! FerroOS Interrupt Descriptor Table (IDT) and 8259 PIC Handlers
//!
//! Handles CPU hardware exceptions (breakpoint, double fault, page fault)
//! and 8259 PIC hardware interrupts (PIT timer IRQ0, PS/2 keyboard IRQ1).

use core::cell::UnsafeCell;
use core::sync::atomic::{AtomicU64, Ordering};
use pc_keyboard::{layouts, DecodedKey, HandleControl, Keyboard, ScancodeSet1};
use pic8259::ChainedPics;
use spin::Mutex;
use x86_64::instructions::port::Port;
use x86_64::structures::idt::{InterruptDescriptorTable, InterruptStackFrame, PageFaultErrorCode};

pub const PIC_1_OFFSET: u8 = 32;
pub const PIC_2_OFFSET: u8 = PIC_1_OFFSET + 8;

pub static PICS: Mutex<ChainedPics> =
    Mutex::new(unsafe { ChainedPics::new(PIC_1_OFFSET, PIC_2_OFFSET) });

pub static SYSTEM_TICKS: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone, Copy)]
#[repr(u8)]
pub enum InterruptIndex {
    Timer = PIC_1_OFFSET,
    Keyboard = PIC_1_OFFSET + 1,
}

impl InterruptIndex {
    pub fn as_u8(self) -> u8 {
        self as u8
    }

    pub fn as_usize(self) -> usize {
        usize::from(self.as_u8())
    }
}

struct SyncUnsafeCell<T>(UnsafeCell<T>);
unsafe impl<T> Sync for SyncUnsafeCell<T> {}

impl<T> SyncUnsafeCell<T> {
    const fn new(val: T) -> Self {
        SyncUnsafeCell(UnsafeCell::new(val))
    }
    fn get(&self) -> *mut T {
        self.0.get()
    }
}

static IDT: SyncUnsafeCell<InterruptDescriptorTable> =
    SyncUnsafeCell::new(InterruptDescriptorTable::new());

pub fn init_idt() {
    unsafe {
        let idt = &mut *IDT.get();
        idt.breakpoint.set_handler_fn(breakpoint_handler);

        let double_fault = idt.double_fault.set_handler_fn(double_fault_handler);
        double_fault.set_stack_index(crate::gdt::DOUBLE_FAULT_IST_INDEX);

        idt.page_fault.set_handler_fn(page_fault_handler);
        idt.general_protection_fault.set_handler_fn(general_protection_fault_handler);

        idt[InterruptIndex::Timer.as_u8()].set_handler_fn(timer_interrupt_handler);
        idt[InterruptIndex::Keyboard.as_u8()].set_handler_fn(keyboard_interrupt_handler);

        idt.load();
    }
}

extern "x86-interrupt" fn breakpoint_handler(stack_frame: InterruptStackFrame) {
    crate::serial_println!("[KERNEL EXCEPTION] BREAKPOINT\n{:#?}", stack_frame);
    crate::println!("[KERNEL EXCEPTION] BREAKPOINT\n{:#?}", stack_frame);
}

extern "x86-interrupt" fn double_fault_handler(
    stack_frame: InterruptStackFrame,
    error_code: u64,
) -> ! {
    panic!(
        "[KERNEL FATAL] DOUBLE FAULT (code {}):\n{:#?}",
        error_code, stack_frame
    );
}

extern "x86-interrupt" fn general_protection_fault_handler(
    stack_frame: InterruptStackFrame,
    error_code: u64,
) {
    panic!(
        "[KERNEL FATAL] GENERAL PROTECTION FAULT (code {}):\n{:#?}",
        error_code, stack_frame
    );
}

extern "x86-interrupt" fn page_fault_handler(
    stack_frame: InterruptStackFrame,
    error_code: PageFaultErrorCode,
) {
    use x86_64::registers::control::Cr2;

    let accessed_address = Cr2::read();
    crate::serial_println!("[KERNEL EXCEPTION] PAGE FAULT");
    crate::serial_println!("Accessed Address: {:?}", accessed_address);
    crate::serial_println!("Error Code: {:?}", error_code);
    crate::serial_println!("{:#?}", stack_frame);

    crate::println!("[KERNEL EXCEPTION] PAGE FAULT at {:?}", accessed_address);
    loop {
        x86_64::instructions::hlt();
    }
}

extern "x86-interrupt" fn timer_interrupt_handler(_stack_frame: InterruptStackFrame) {
    let ticks = SYSTEM_TICKS.fetch_add(1, Ordering::Relaxed);
    // Print a heartbeat dot every 100 ticks on serial for verification
    if ticks > 0 && ticks % 100 == 0 {
        crate::serial_print!(".");
    }

    unsafe {
        PICS.lock()
            .notify_end_of_interrupt(InterruptIndex::Timer.as_u8());
    }
}

extern "x86-interrupt" fn keyboard_interrupt_handler(_stack_frame: InterruptStackFrame) {
    static KEYBOARD: Mutex<Option<Keyboard<layouts::Us104Key, ScancodeSet1>>> = Mutex::new(None);

    let mut keyboard_guard = KEYBOARD.lock();
    if keyboard_guard.is_none() {
        *keyboard_guard = Some(Keyboard::new(
            ScancodeSet1::new(),
            layouts::Us104Key,
            HandleControl::Ignore,
        ));
    }
    let keyboard = keyboard_guard.as_mut().unwrap();

    let mut port = Port::new(0x60);
    let scancode: u8 = unsafe { port.read() };

    if let Ok(Some(key_event)) = keyboard.add_byte(scancode) {
        if let Some(key) = keyboard.process_keyevent(key_event) {
            match key {
                DecodedKey::Unicode(character) => {
                    crate::print!("{}", character);
                    crate::serial_print!("{}", character);
                }
                DecodedKey::RawKey(key) => {
                    crate::serial_print!("[Key: {:?}]", key);
                }
            }
        }
    }

    unsafe {
        PICS.lock()
            .notify_end_of_interrupt(InterruptIndex::Keyboard.as_u8());
    }
}
