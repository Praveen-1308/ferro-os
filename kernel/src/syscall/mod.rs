//! FerroOS Syscall Subsystem (Linux x86_64 ABI Compatible)
//!
//! Implements the kernel-side syscall dispatcher allowing standard x86_64 binaries
//! (such as `ferro-core` compiled with musl) to execute syscalls directly against
//! the bare-metal microkernel.

pub mod table;

use core::slice;
use table::*;

/// Linux-compatible utsname struct for `sys_uname` (65 bytes per field)
#[repr(C)]
pub struct UtsName {
    pub sysname: [u8; 65],
    pub nodename: [u8; 65],
    pub release: [u8; 65],
    pub version: [u8; 65],
    pub machine: [u8; 65],
    pub domainname: [u8; 65],
}

fn copy_cstr(dest: &mut [u8], src: &str) {
    let bytes = src.as_bytes();
    let len = bytes.len().min(dest.len() - 1);
    dest[..len].copy_from_slice(&bytes[..len]);
    dest[len] = 0;
}

/// Central dispatch point for CPU `syscall` instructions
pub fn dispatch_syscall(number: usize, arg1: usize, arg2: usize, arg3: usize) -> isize {
    match number {
        SYS_READ => sys_read(arg1 as i32, arg2 as *mut u8, arg3),
        SYS_WRITE => sys_write(arg1 as i32, arg2 as *const u8, arg3),
        SYS_GETPID => sys_getpid(),
        SYS_EXIT => sys_exit(arg1 as i32),
        SYS_UNAME => sys_uname(arg2 as *mut UtsName),
        SYS_BRK => sys_brk(arg1),
        _ => {
            crate::serial_println!("[KERNEL SYSCALL] Unhandled syscall #{}", number);
            -38 // -ENOSYS
        }
    }
}

fn sys_write(fd: i32, buf: *const u8, count: usize) -> isize {
    if buf.is_null() || count == 0 {
        return 0;
    }

    // Standard stdout (1) and stderr (2)
    if fd == 1 || fd == 2 {
        let bytes = unsafe { slice::from_raw_parts(buf, count) };
        if let Ok(s) = core::str::from_utf8(bytes) {
            crate::print!("{}", s);
            crate::serial_print!("{}", s);
        } else {
            for &b in bytes {
                crate::vga::WRITER.lock().write_byte(b);
            }
        }
        return count as isize;
    }

    -9 // -EBADF
}

fn sys_read(fd: i32, _buf: *mut u8, _count: usize) -> isize {
    if fd == 0 {
        // Non-blocking stdin placeholder
        return 0;
    }
    -9 // -EBADF
}

fn sys_getpid() -> isize {
    crate::process::scheduler::SCHEDULER.lock().get_current_pid() as isize
}

fn sys_exit(code: i32) -> ! {
    crate::serial_println!("[KERNEL PROCESS EXIT] Process exited with code {}", code);
    crate::process::scheduler::SCHEDULER.lock().exit_current(code);

    // Halt until next scheduled task or idle loop
    loop {
        x86_64::instructions::hlt();
    }
}

fn sys_uname(buf: *mut UtsName) -> isize {
    if buf.is_null() {
        return -14; // -EFAULT
    }

    unsafe {
        let uts = &mut *buf;
        copy_cstr(&mut uts.sysname, "FerroOS");
        copy_cstr(&mut uts.nodename, "ferro-node");
        copy_cstr(&mut uts.release, "3.0.0-ferro-baremetal");
        copy_cstr(&mut uts.version, "#1 SMP Rust 2026 x86_64");
        copy_cstr(&mut uts.machine, "x86_64");
        copy_cstr(&mut uts.domainname, "localdomain");
    }

    0
}

fn sys_brk(addr: usize) -> isize {
    // Return heap end boundary
    if addr == 0 {
        (crate::memory::HEAP_START + crate::memory::HEAP_SIZE) as isize
    } else {
        addr as isize
    }
}
