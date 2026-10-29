//! FerroOS Memory Management Subsystem
//!
//! Encompasses physical frame allocation, 4-level paging, and the kernel heap allocator.

pub mod heap;

pub use heap::{init_heap, ALLOCATOR, HEAP_SIZE, HEAP_START};
