//! FerroOS Kernel Heap Allocator
//!
//! Provides dynamic memory allocation in `#![no_std]` bare-metal environment
//! using `linked_list_allocator::LockedHeap`, enabling `alloc::vec::Vec`,
//! `alloc::string::String`, and `alloc::boxed::Box`.

use core::cell::UnsafeCell;
use linked_list_allocator::LockedHeap;

pub const HEAP_START: usize = 0x_4444_4444_0000;
pub const HEAP_SIZE: usize = 512 * 1024; // 512 KiB initial kernel heap

#[global_allocator]
pub static ALLOCATOR: LockedHeap = LockedHeap::empty();

struct HeapBuffer(UnsafeCell<[u8; HEAP_SIZE]>);
unsafe impl Sync for HeapBuffer {}

static KERNEL_HEAP: HeapBuffer = HeapBuffer(UnsafeCell::new([0; HEAP_SIZE]));

/// Initialize the global allocator using the kernel heap memory region
pub fn init_heap() {
    unsafe {
        let heap_ptr = KERNEL_HEAP.0.get() as *mut u8;
        ALLOCATOR.lock().init(heap_ptr, HEAP_SIZE);
    }
}
