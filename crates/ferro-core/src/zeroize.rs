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
