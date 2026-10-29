//! FerroOS Global Descriptor Table (GDT) and Task State Segment (TSS)
//!
//! Configures 64-bit kernel code segments and a dedicated double fault interrupt
//! stack table (IST) to prevent unrecoverable triple faults on kernel stack overflow.

use core::cell::UnsafeCell;
use spin::Once;
use x86_64::structures::gdt::{Descriptor, GlobalDescriptorTable, SegmentSelector};
use x86_64::structures::tss::TaskStateSegment;
use x86_64::VirtAddr;

pub const DOUBLE_FAULT_IST_INDEX: u16 = 0;

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

static TSS: SyncUnsafeCell<TaskStateSegment> = SyncUnsafeCell::new(TaskStateSegment::new());
static GDT: SyncUnsafeCell<GlobalDescriptorTable> = SyncUnsafeCell::new(GlobalDescriptorTable::new());
static SELECTORS: SyncUnsafeCell<Option<Selectors>> = SyncUnsafeCell::new(None);

static INIT_ONCE: Once<()> = Once::new();

#[allow(dead_code)]
#[derive(Clone, Copy)]
struct Selectors {
    code_selector: SegmentSelector,
    tss_selector: SegmentSelector,
}

pub fn init_gdt() {
    INIT_ONCE.call_once(|| {
        unsafe {
            const STACK_SIZE: usize = 4096 * 5;
            static STACK: SyncUnsafeCell<[u8; STACK_SIZE]> = SyncUnsafeCell::new([0; STACK_SIZE]);

            let stack_start = VirtAddr::from_ptr(STACK.get());
            let stack_end = stack_start + (STACK_SIZE as u64);
            (*TSS.get()).interrupt_stack_table[DOUBLE_FAULT_IST_INDEX as usize] = stack_end;

            let code_selector = (*GDT.get()).append(Descriptor::kernel_code_segment());
            let tss_selector = (*GDT.get()).append(Descriptor::tss_segment(&*TSS.get()));

            *SELECTORS.get() = Some(Selectors {
                code_selector,
                tss_selector,
            });

            use x86_64::instructions::segmentation::{Segment, CS};
            use x86_64::instructions::tables::load_tss;

            (*GDT.get()).load();
            CS::set_reg(code_selector);
            load_tss(tss_selector);
        }
    });
}
