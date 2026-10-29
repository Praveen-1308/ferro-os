//! FerroOS Round-Robin Process Scheduler
//!
//! Provides the Process Control Block (PCB), execution state transitions,
//! and cooperative/preemptive time-slice scheduling.

use spin::Mutex;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProcessState {
    Ready,
    Running,
    Blocked,
    Exited(i32),
}

#[derive(Debug, Clone, Copy, Default)]
#[repr(C)]
pub struct CpuContext {
    pub rax: u64,
    pub rbx: u64,
    pub rcx: u64,
    pub rdx: u64,
    pub rsi: u64,
    pub rdi: u64,
    pub rbp: u64,
    pub rsp: u64,
    pub r8: u64,
    pub r9: u64,
    pub r10: u64,
    pub r11: u64,
    pub r12: u64,
    pub r13: u64,
    pub r14: u64,
    pub r15: u64,
    pub rip: u64,
    pub rflags: u64,
}

pub struct ProcessControlBlock {
    pub pid: usize,
    pub name: &'static str,
    pub state: ProcessState,
    pub context: CpuContext,
    pub priority: u8,
    pub time_slices: u64,
}

const MAX_PROCESSES: usize = 16;

pub struct RoundRobinScheduler {
    processes: [Option<ProcessControlBlock>; MAX_PROCESSES],
    current_idx: usize,
    next_pid: usize,
}

impl RoundRobinScheduler {
    pub const fn new() -> Self {
        const INIT_NONE: Option<ProcessControlBlock> = None;
        Self {
            processes: [INIT_NONE; MAX_PROCESSES],
            current_idx: 0,
            next_pid: 1,
        }
    }

    pub fn spawn(&mut self, name: &'static str, entry_point: usize, stack_top: usize) -> Option<usize> {
        for slot in self.processes.iter_mut() {
            if slot.is_none() {
                let pid = self.next_pid;
                self.next_pid += 1;

                let mut context = CpuContext::default();
                context.rip = entry_point as u64;
                context.rsp = stack_top as u64;
                context.rflags = 0x202; // IF (Interrupt Flag) enabled

                *slot = Some(ProcessControlBlock {
                    pid,
                    name,
                    state: ProcessState::Ready,
                    context,
                    priority: 1,
                    time_slices: 0,
                });

                return Some(pid);
            }
        }
        None
    }

    pub fn schedule(&mut self) -> Option<&mut ProcessControlBlock> {
        let mut searched = 0;
        let mut idx = (self.current_idx + 1) % MAX_PROCESSES;

        while searched < MAX_PROCESSES {
            if let Some(ref mut proc) = self.processes[idx] {
                if proc.state == ProcessState::Ready || proc.state == ProcessState::Running {
                    proc.state = ProcessState::Running;
                    proc.time_slices += 1;
                    self.current_idx = idx;
                    return self.processes[idx].as_mut();
                }
            }
            idx = (idx + 1) % MAX_PROCESSES;
            searched += 1;
        }

        None
    }

    pub fn get_current_pid(&self) -> usize {
        if let Some(ref proc) = self.processes[self.current_idx] {
            proc.pid
        } else {
            0
        }
    }

    pub fn exit_current(&mut self, exit_code: i32) {
        if let Some(ref mut proc) = self.processes[self.current_idx] {
            proc.state = ProcessState::Exited(exit_code);
        }
    }
}

pub static SCHEDULER: Mutex<RoundRobinScheduler> = Mutex::new(RoundRobinScheduler::new());
