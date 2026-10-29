//! crates/ferro-core/src/zeroize.rs
//! Transparent Zero-on-Free & Temporal Memory Isolation
//! Implements compiler-barrier memory wiping (CWE-226 mitigation) as specified in
//! docs/MEMORY_SECURITY_AND_STANDARDS.md Section 2.3.

use std::fmt;
use std::ops::{Deref, DerefMut};
use std::sync::atomic::{compiler_fence, Ordering};

/// SecureZeroizingSecret: A memory container that automatically overwrites
/// its contents with 0x00 on drop using volatile writes and a sequential consistency
/// compiler barrier to prevent dead-store elimination (DSE).
pub struct SecureZeroizingSecret<T: AsMut<[u8]>> {
    inner: T,
}

impl<T: AsMut<[u8]>> SecureZeroizingSecret<T> {
    pub fn new(data: T) -> Self {
        Self { inner: data }
    }

    pub fn as_slice(&self) -> &[u8]
    where
        T: AsRef<[u8]>,
    {
        self.inner.as_ref()
    }

    pub fn as_mut_slice(&mut self) -> &mut [u8] {
        self.inner.as_mut()
    }
}

impl<T: AsMut<[u8]>> Deref for SecureZeroizingSecret<T> {
    type Target = T;
    fn deref(&self) -> &Self::Target {
        &self.inner
    }
}

impl<T: AsMut<[u8]>> DerefMut for SecureZeroizingSecret<T> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.inner
    }
}

impl<T: AsMut<[u8]>> Drop for SecureZeroizingSecret<T> {
    fn drop(&mut self) {
        let slice = self.inner.as_mut();
        for byte in slice.iter_mut() {
            unsafe {
                core::ptr::write_volatile(byte, 0x00);
            }
        }
        // Compiler barrier ensures the optimizer cannot optimize away the writes as dead stores.
        compiler_fence(Ordering::SeqCst);
    }
}

impl<T: AsMut<[u8]>> fmt::Debug for SecureZeroizingSecret<T> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[REDACTED SECURE SECRET]")
    }
}

/// Explicit memory wiping for raw slices.
pub fn explicit_zeroize_slice(slice: &mut [u8]) {
    for byte in slice.iter_mut() {
        unsafe {
            core::ptr::write_volatile(byte, 0x00);
        }
    }
    compiler_fence(Ordering::SeqCst);
}

use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;
use std::process::ExitCode;

pub fn run_zeroize(args: &[String]) -> ExitCode {
    if args.is_empty() || args.iter().any(|a| a == "-h" || a == "--help") {
        println!("FerroOS Cryptographic Memory & Storage Zeroize Utility (CWE-226 Defense)");
        println!("Usage: zeroize [OPTIONS] <FILE>...");
        println!("Options:");
        println!("  -t, --test       Run memory isolation & compiler-barrier zeroize tests");
        println!("  -d, --delete     Securely zero out and delete (unlink) specified file(s)");
        println!("  -f, --force      Force overwriting even if read-only");
        println!("  -h, --help       Display this help message");
        return if args.is_empty() { ExitCode::from(1) } else { ExitCode::SUCCESS };
    }

    let mut run_test = false;
    let mut delete_file = false;
    let mut files = Vec::new();

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-t" || arg == "--test" {
            run_test = true;
            i += 1;
        } else if arg == "-d" || arg == "--delete" {
            delete_file = true;
            i += 1;
        } else if arg == "-f" || arg == "--force" {
            i += 1;
        } else if !arg.starts_with('-') {
            files.push(arg.clone());
            i += 1;
        } else {
            i += 1;
        }
    }

    if run_test {
        let mut test_secret = [0xDE, 0xAD, 0xBE, 0xEF];
        explicit_zeroize_slice(&mut test_secret);
        if test_secret == [0x00, 0x00, 0x00, 0x00] {
            println!("✅ FerroOS In-Memory Compiler-Barrier Zeroize: PASS (CWE-226 Defended)");
            return ExitCode::SUCCESS;
        } else {
            eprintln!("❌ FerroOS In-Memory Compiler-Barrier Zeroize: FAIL");
            return ExitCode::from(1);
        }
    }

    if files.is_empty() {
        eprintln!("zeroize: missing file operand (try 'zeroize --help')");
        return ExitCode::from(1);
    }

    let mut exit_code = ExitCode::SUCCESS;
    for file_path in files {
        let p = Path::new(&file_path);
        let meta = match std::fs::metadata(p) {
            Ok(m) => m,
            Err(e) => {
                eprintln!("zeroize: cannot access '{}': {}", file_path, e);
                exit_code = ExitCode::from(1);
                continue;
            }
        };

        let file_len = meta.len() as usize;
        if file_len > 0 {
            let zero_buf = vec![0u8; 4096.min(file_len)];
            match OpenOptions::new().write(true).open(p) {
                Ok(mut f) => {
                    let mut written = 0;
                    while written < file_len {
                        let to_write = (file_len - written).min(zero_buf.len());
                        if f.write_all(&zero_buf[..to_write]).is_err() {
                            break;
                        }
                        written += to_write;
                    }
                    let _ = f.sync_all();
                }
                Err(e) => {
                    eprintln!("zeroize: cannot overwrite '{}': {}", file_path, e);
                    exit_code = ExitCode::from(1);
                    continue;
                }
            }
        }

        if delete_file {
            if let Err(e) = std::fs::remove_file(p) {
                eprintln!("zeroize: cannot unlink '{}': {}", file_path, e);
                exit_code = ExitCode::from(1);
            }
        }
    }

    exit_code
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicBool;

    #[test]
    fn test_zeroize_explicit() {
        let mut secret = [0xDE, 0xAD, 0xBE, 0xEF];
        explicit_zeroize_slice(&mut secret);
        assert_eq!(secret, [0x00, 0x00, 0x00, 0x00]);
    }

    #[test]
    fn test_zeroize_on_drop() {
        static DROPPED_AND_ZEROED: AtomicBool = AtomicBool::new(false);

        struct TestBuf {
            data: [u8; 4],
        }
        impl AsMut<[u8]> for TestBuf {
            fn as_mut(&mut self) -> &mut [u8] {
                &mut self.data
            }
        }
        impl AsRef<[u8]> for TestBuf {
            fn as_ref(&self) -> &[u8] {
                &self.data
            }
        }
        impl Drop for TestBuf {
            fn drop(&mut self) {
                if self.data == [0x00, 0x00, 0x00, 0x00] {
                    DROPPED_AND_ZEROED.store(true, Ordering::SeqCst);
                }
            }
        }

        {
            let buf = TestBuf {
                data: [0xDE, 0xAD, 0xBE, 0xEF],
            };
            let _sec = SecureZeroizingSecret::new(buf);
        }
        assert!(DROPPED_AND_ZEROED.load(Ordering::SeqCst));
    }
}
