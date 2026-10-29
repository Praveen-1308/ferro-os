//! FerroOS Process & Task Subsystem
//!
//! Provides the Process Control Block (PCB), task execution contexts,
//! and cooperative/preemptive task scheduling.

pub mod scheduler;

pub use scheduler::{CpuContext, ProcessControlBlock, ProcessState, RoundRobinScheduler};
