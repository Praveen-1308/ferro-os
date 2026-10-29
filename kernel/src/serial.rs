//! FerroOS Bare-Metal Serial Port Driver (UART 16550, COM1 0x3F8)
//!
//! Provides headless logging and debugging output to QEMU / host terminal via COM1.

use core::fmt;
use spin::Mutex;
use uart_16550::SerialPort;

pub static SERIAL1: Mutex<SerialPort> = Mutex::new(unsafe { SerialPort::new(0x3F8) });

pub fn init_serial() {
    SERIAL1.lock().init();
}

#[doc(hidden)]
pub fn _serial_print(args: fmt::Arguments) {
    use core::fmt::Write;
    use x86_64::instructions::interrupts;

    interrupts::without_interrupts(|| {
        SERIAL1
            .lock()
            .write_fmt(args)
            .expect("Printing to serial port COM1 failed");
    });
}

#[macro_export]
macro_rules! serial_print {
    ($($arg:tt)*) => {
        $crate::serial::_serial_print(format_args!($($arg)*));
    };
}

#[macro_export]
macro_rules! serial_println {
    () => ($crate::serial_print!("\n"));
    ($($arg:tt)*) => ($crate::serial_print!("{}\n", format_args!($($arg)*)));
}
