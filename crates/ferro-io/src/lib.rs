//! ferro-io: High-Performance Pure-Rust POSIX I/O Interposition and io_uring Acceleration Library
//!
#![allow(clippy::all)]
//! Provides transparent acceleration for standard POSIX I/O:
//!  - Lock-free atomic file descriptor classification cache (65,536 slots).
//!  - Thread-local io_uring instances with kernel SQPOLL submission polling.
//!  - Asynchronous pread, pwrite, fsync, and fdatasync acceleration.
//!  - Zero-latency TCP loopback socket tuning (TCP_NODELAY, TCP_QUICKACK, 4MB buffers).
//!  - AT_SECURE and SUID privilege boundary enforcement.

use libc::{
    c_int, c_uint, c_void, off_t, size_t, sockaddr, socklen_t, ssize_t, AF_INET, AF_INET6, EINVAL,
    ENOSYS, EOPNOTSUPP, IPPROTO_TCP, RTLD_NEXT, SOL_SOCKET, SO_RCVBUF, SO_SNDBUF, S_IFMT, S_IFREG,
    TCP_NODELAY,
};
use std::cell::RefCell;
use std::sync::atomic::{AtomicBool, AtomicI32, AtomicPtr, AtomicU8, Ordering};

#[cfg(target_os = "linux")]
#[inline(always)]
unsafe fn set_errno(err: c_int) {
    *libc::__errno_location() = err;
}

#[cfg(target_os = "macos")]
#[inline(always)]
unsafe fn set_errno(err: c_int) {
    *libc::__error() = err;
}

#[cfg(not(any(target_os = "linux", target_os = "macos")))]
#[inline(always)]
unsafe fn set_errno(_err: c_int) {}

const SSIZE_MAX: usize = isize::MAX as usize;

// Constants for io_uring
const IORING_OP_FSYNC: u8 = 3;
const IORING_OP_READ: u8 = 22;
const IORING_OP_WRITE: u8 = 23;
const IORING_FSYNC_DATASYNC: u32 = 1;
const IORING_SETUP_SQPOLL: u32 = 1 << 1;
const IORING_SETUP_SINGLE_ISSUER: u32 = 1 << 12;
const FERRO_URING_ENTRIES: u32 = 256;
const MIN_URING_IO_BYTES: size_t = 4096;

// Cache bounds (128K FDs for extreme network & database concurrency)
const MAX_CACHED_FDS: usize = 131072;
// 0 = Unknown, 1 = Bypass (socket/pipe/TTY), 2 = Regular File Eligible
static FD_TYPE_CACHE: [AtomicU8; MAX_CACHED_FDS] = {
    const INIT: AtomicU8 = AtomicU8::new(0);
    [INIT; MAX_CACHED_FDS]
};

static INITIALIZED: AtomicBool = AtomicBool::new(false);
static INITIALIZING: AtomicBool = AtomicBool::new(false);
static INIT_PID: AtomicI32 = AtomicI32::new(0);
static IS_SECURE: AtomicI32 = AtomicI32::new(-1);

// C-compatible io_uring structures
#[repr(C)]
struct IoUringSqe {
    opcode: u8,
    flags: u8,
    ioprio: u16,
    fd: i32,
    off: u64,
    addr: u64,
    len: u32,
    rw_flags: u32,
    user_data: u64,
    buf_index: u16,
    personality: u16,
    splice_fd_in: i32,
    addr3_or_pad: [u64; 2],
}

#[repr(C)]
struct IoUringCqe {
    user_data: u64,
    res: i32,
    flags: u32,
}

#[repr(C)]
struct IoSqringOffsets {
    head: u32,
    tail: u32,
    ring_mask: u32,
    ring_entries: u32,
    flags: u32,
    dropped: u32,
    array: u32,
    resv1: u32,
    user_addr: u64,
}

#[repr(C)]
struct IoCqringOffsets {
    head: u32,
    tail: u32,
    ring_mask: u32,
    ring_entries: u32,
    overflow: u32,
    cqes: u32,
    flags: u32,
    resv1: u32,
    user_addr: u64,
}

#[repr(C)]
struct IoUringParams {
    sq_entries: u32,
    cq_entries: u32,
    flags: u32,
    sq_thread_cpu: u32,
    sq_thread_idle: u32,
    features: u32,
    wq_fd: u32,
    resv: [u32; 3],
    sq_off: IoSqringOffsets,
    cq_off: IoCqringOffsets,
}

#[repr(C)]
struct IoUringSq {
    khead: *mut c_uint,
    ktail: *mut c_uint,
    kring_mask: *mut c_uint,
    kring_entries: *mut c_uint,
    kflags: *mut c_uint,
    kdropped: *mut c_uint,
    array: *mut c_uint,
    sqes: *mut IoUringSqe,
    sqe_head: c_uint,
    sqe_tail: c_uint,
    ring_sz: size_t,
    ring_ptr: *mut c_void,
    ring_mask: c_uint,
    ring_entries: c_uint,
    pad: [c_uint; 2],
}

#[repr(C)]
struct IoUringCq {
    khead: *mut c_uint,
    ktail: *mut c_uint,
    kring_mask: *mut c_uint,
    kring_entries: *mut c_uint,
    kflags: *mut c_uint,
    koverflow: *mut c_uint,
    cqes: *mut IoUringCqe,
    ring_sz: size_t,
    ring_ptr: *mut c_void,
    ring_mask: c_uint,
    ring_entries: c_uint,
    pad: [c_uint; 2],
}

#[repr(C)]
struct IoUring {
    sq: IoUringSq,
    cq: IoUringCq,
    flags: c_uint,
    ring_fd: c_int,
    features: c_uint,
    enter_ring_fd: c_int,
    int_flags: u8,
    pad: [u8; 3],
    pad2: c_uint,
}

type FnIoUringQueueInitParams =
    unsafe extern "C" fn(c_uint, *mut IoUring, *mut IoUringParams) -> c_int;
type FnIoUringQueueInit = unsafe extern "C" fn(c_uint, *mut IoUring, c_uint) -> c_int;
type FnIoUringQueueExit = unsafe extern "C" fn(*mut IoUring);
type FnIoUringGetSqe = unsafe extern "C" fn(*mut IoUring) -> *mut IoUringSqe;
type FnIoUringSubmitAndWait = unsafe extern "C" fn(*mut IoUring, c_uint) -> c_int;
type FnIoUringGetCqe = unsafe extern "C" fn(
    *mut IoUring,
    *mut *mut IoUringCqe,
    c_uint,
    c_uint,
    *mut libc::sigset_t,
) -> c_int;

static FN_QUEUE_INIT_PARAMS: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static FN_QUEUE_INIT: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static FN_QUEUE_EXIT: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static FN_GET_SQE: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static FN_SUBMIT_AND_WAIT: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static FN_GET_CQE: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
#[allow(dead_code)]
static URING_RESOLVED: AtomicBool = AtomicBool::new(false);

#[cfg(target_os = "linux")]
unsafe fn resolve_uring_symbols() {
    if URING_RESOLVED.swap(true, Ordering::SeqCst) {
        return;
    }

    let mut handle = libc::RTLD_DEFAULT;
    let libname = b"liburing.so.2\0";
    let dl_h = libc::dlopen(
        libname.as_ptr() as *const libc::c_char,
        libc::RTLD_LAZY | libc::RTLD_LOCAL,
    );
    if !dl_h.is_null() {
        handle = dl_h;
    } else {
        let libname1 = b"liburing.so\0";
        let dl_h1 = libc::dlopen(
            libname1.as_ptr() as *const libc::c_char,
            libc::RTLD_LAZY | libc::RTLD_LOCAL,
        );
        if !dl_h1.is_null() {
            handle = dl_h1;
        }
    }

    let p1 = libc::dlsym(handle, b"io_uring_queue_init_params\0".as_ptr() as *const _);
    if !p1.is_null() {
        FN_QUEUE_INIT_PARAMS.store(p1, Ordering::SeqCst);
    }

    let p2 = libc::dlsym(handle, b"io_uring_queue_init\0".as_ptr() as *const _);
    if !p2.is_null() {
        FN_QUEUE_INIT.store(p2, Ordering::SeqCst);
    }

    let p3 = libc::dlsym(handle, b"io_uring_queue_exit\0".as_ptr() as *const _);
    if !p3.is_null() {
        FN_QUEUE_EXIT.store(p3, Ordering::SeqCst);
    }

    let p4 = libc::dlsym(handle, b"io_uring_get_sqe\0".as_ptr() as *const _);
    if !p4.is_null() {
        FN_GET_SQE.store(p4, Ordering::SeqCst);
    }

    let p5 = libc::dlsym(handle, b"io_uring_submit_and_wait\0".as_ptr() as *const _);
    if !p5.is_null() {
        FN_SUBMIT_AND_WAIT.store(p5, Ordering::SeqCst);
    }

    let p6 = libc::dlsym(handle, b"__io_uring_get_cqe\0".as_ptr() as *const _);
    if !p6.is_null() {
        FN_GET_CQE.store(p6, Ordering::SeqCst);
    }
}

#[cfg(not(target_os = "linux"))]
unsafe fn resolve_uring_symbols() {}

unsafe fn io_uring_queue_init_params(
    entries: c_uint,
    ring: *mut IoUring,
    p: *mut IoUringParams,
) -> c_int {
    resolve_uring_symbols();
    let ptr = FN_QUEUE_INIT_PARAMS.load(Ordering::Acquire);
    if !ptr.is_null() {
        let f: FnIoUringQueueInitParams = std::mem::transmute(ptr);
        f(entries, ring, p)
    } else {
        -1
    }
}

unsafe fn io_uring_queue_init(entries: c_uint, ring: *mut IoUring, flags: c_uint) -> c_int {
    resolve_uring_symbols();
    let ptr = FN_QUEUE_INIT.load(Ordering::Acquire);
    if !ptr.is_null() {
        let f: FnIoUringQueueInit = std::mem::transmute(ptr);
        f(entries, ring, flags)
    } else {
        -1
    }
}

unsafe fn io_uring_queue_exit(ring: *mut IoUring) {
    resolve_uring_symbols();
    let ptr = FN_QUEUE_EXIT.load(Ordering::Acquire);
    if !ptr.is_null() {
        let f: FnIoUringQueueExit = std::mem::transmute(ptr);
        f(ring);
    }
}

unsafe fn io_uring_get_sqe(ring: *mut IoUring) -> *mut IoUringSqe {
    resolve_uring_symbols();
    let ptr = FN_GET_SQE.load(Ordering::Acquire);
    if !ptr.is_null() {
        let f: FnIoUringGetSqe = std::mem::transmute(ptr);
        f(ring)
    } else {
        std::ptr::null_mut()
    }
}

unsafe fn io_uring_submit_and_wait(ring: *mut IoUring, wait_nr: c_uint) -> c_int {
    resolve_uring_symbols();
    let ptr = FN_SUBMIT_AND_WAIT.load(Ordering::Acquire);
    if !ptr.is_null() {
        let f: FnIoUringSubmitAndWait = std::mem::transmute(ptr);
        f(ring, wait_nr)
    } else {
        -1
    }
}

unsafe fn __io_uring_get_cqe(
    ring: *mut IoUring,
    cqe_ptr: *mut *mut IoUringCqe,
    submit: c_uint,
    wait_nr: c_uint,
    sigmask: *mut libc::sigset_t,
) -> c_int {
    resolve_uring_symbols();
    let ptr = FN_GET_CQE.load(Ordering::Acquire);
    if !ptr.is_null() {
        let f: FnIoUringGetCqe = std::mem::transmute(ptr);
        f(ring, cqe_ptr, submit, wait_nr, sigmask)
    } else {
        -1
    }
}

#[inline(always)]
unsafe fn io_uring_cq_advance(ring: *mut IoUring, nr: u32) {
    if nr != 0 && !ring.is_null() {
        let cq = &mut (*ring).cq;
        if !cq.khead.is_null() {
            let current = std::ptr::read_volatile(cq.khead);
            std::sync::atomic::fence(Ordering::Release);
            std::ptr::write_volatile(cq.khead, current.wrapping_add(nr));
        }
    }
}

#[inline(always)]
unsafe fn io_uring_cqe_seen(ring: *mut IoUring, cqe: *mut IoUringCqe) {
    if !cqe.is_null() {
        io_uring_cq_advance(ring, 1);
    }
}

#[inline(always)]
unsafe fn io_uring_peek_cqe(ring: *mut IoUring, cqe_ptr: *mut *mut IoUringCqe) -> c_int {
    __io_uring_get_cqe(ring, cqe_ptr, 0, 0, std::ptr::null_mut())
}

struct RustThreadRing {
    ring: IoUring,
    active: bool,
    owner_pid: i32,
}

impl Drop for RustThreadRing {
    fn drop(&mut self) {
        if self.active && self.owner_pid == unsafe { libc::getpid() } {
            unsafe { io_uring_queue_exit(&mut self.ring) };
            self.active = false;
        }
    }
}

thread_local! {
    static THREAD_RING: RefCell<Option<RustThreadRing>> = const { RefCell::new(None) };
}

fn get_thread_uring() -> Option<*mut IoUring> {
    let pid = unsafe { libc::getpid() };
    THREAD_RING.with(|cell| {
        let mut borrow = cell.borrow_mut();
        if let Some(r) = borrow.as_mut() {
            if r.owner_pid == pid && r.active {
                return Some(&mut r.ring as *mut IoUring);
            } else {
                // PID changed (fork occurred) - do NOT destroy parent's ring!
                // Simply release the thread-local instance so child creates its own ring.
                *borrow = None;
            }
        }

        let entries = std::env::var("FERRO_URING_ENTRIES")
            .ok()
            .and_then(|s| s.parse::<u32>().ok())
            .unwrap_or(FERRO_URING_ENTRIES)
            .clamp(64, 4096);

        // Initialize new io_uring
        let mut uninit_ring: IoUring = unsafe { std::mem::zeroed() };
        let mut params: IoUringParams = unsafe { std::mem::zeroed() };
        params.flags = IORING_SETUP_SQPOLL;
        params.sq_thread_idle = 2000;

        let ret = unsafe {
            io_uring_queue_init_params(entries, &mut uninit_ring, &mut params)
        };
        if ret >= 0 {
            *borrow = Some(RustThreadRing {
                ring: uninit_ring,
                active: true,
                owner_pid: pid,
            });
            return Some(&mut borrow.as_mut().unwrap().ring as *mut IoUring);
        }

        // Fallback 1: SINGLE_ISSUER
        let mut params2: IoUringParams = unsafe { std::mem::zeroed() };
        params2.flags = IORING_SETUP_SINGLE_ISSUER;
        let ret2 = unsafe {
            io_uring_queue_init_params(entries, &mut uninit_ring, &mut params2)
        };
        if ret2 >= 0 {
            *borrow = Some(RustThreadRing {
                ring: uninit_ring,
                active: true,
                owner_pid: pid,
            });
            return Some(&mut borrow.as_mut().unwrap().ring as *mut IoUring);
        }

        // Fallback 2: Standard Ring
        let ret3 = unsafe { io_uring_queue_init(entries, &mut uninit_ring, 0) };
        if ret3 >= 0 {
            *borrow = Some(RustThreadRing {
                ring: uninit_ring,
                active: true,
                owner_pid: pid,
            });
            return Some(&mut borrow.as_mut().unwrap().ring as *mut IoUring);
        }

        None
    })
}

// Function pointer types
type ReadFn = unsafe extern "C" fn(c_int, *mut c_void, size_t) -> ssize_t;
type WriteFn = unsafe extern "C" fn(c_int, *const c_void, size_t) -> ssize_t;
type CloseFn = unsafe extern "C" fn(c_int) -> c_int;
type Dup2Fn = unsafe extern "C" fn(c_int, c_int) -> c_int;
type Dup3Fn = unsafe extern "C" fn(c_int, c_int, c_int) -> c_int;
type SocketFn = unsafe extern "C" fn(c_int, c_int, c_int) -> c_int;
type ConnectFn = unsafe extern "C" fn(c_int, *const sockaddr, socklen_t) -> c_int;
type AcceptFn = unsafe extern "C" fn(c_int, *mut sockaddr, *mut socklen_t) -> c_int;
type Accept4Fn = unsafe extern "C" fn(c_int, *mut sockaddr, *mut socklen_t, c_int) -> c_int;
type PreadFn = unsafe extern "C" fn(c_int, *mut c_void, size_t, off_t) -> ssize_t;
type PwriteFn = unsafe extern "C" fn(c_int, *const c_void, size_t, off_t) -> ssize_t;
type FsyncFn = unsafe extern "C" fn(c_int) -> c_int;
type FdatasyncFn = unsafe extern "C" fn(c_int) -> c_int;
type EpollCreate1Fn = unsafe extern "C" fn(c_int) -> c_int;
type EpollCtlFn = unsafe extern "C" fn(c_int, c_int, c_int, *mut c_void) -> c_int;
type EpollWaitFn = unsafe extern "C" fn(c_int, *mut c_void, c_int, c_int) -> c_int;

static REAL_READ: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_WRITE: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_CLOSE: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_DUP2: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_DUP3: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_SOCKET: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_CONNECT: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_ACCEPT: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_ACCEPT4: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_PREAD: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_PWRITE: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_FSYNC: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_FDATASYNC: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_EPOLL_CREATE1: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_EPOLL_CTL: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static REAL_EPOLL_WAIT: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());

unsafe fn resolve_sym(name: &'static [u8]) -> *mut c_void {
    let sym = libc::dlsym(RTLD_NEXT, name.as_ptr() as *const libc::c_char);
    sym
}

fn ensure_symbols_initialized() {
    let pid = unsafe { libc::getpid() };
    if INITIALIZED.load(Ordering::Acquire) && INIT_PID.load(Ordering::Acquire) == pid {
        return;
    }

    if INITIALIZING
        .compare_exchange(false, true, Ordering::AcqRel, Ordering::Relaxed)
        .is_err()
    {
        while !INITIALIZED.load(Ordering::Acquire) && INIT_PID.load(Ordering::Acquire) == pid {
            std::hint::spin_loop();
        }
        return;
    }

    unsafe {
        REAL_READ.store(resolve_sym(b"read\0"), Ordering::Release);
        REAL_WRITE.store(resolve_sym(b"write\0"), Ordering::Release);
        REAL_CLOSE.store(resolve_sym(b"close\0"), Ordering::Release);
        REAL_DUP2.store(resolve_sym(b"dup2\0"), Ordering::Release);
        REAL_DUP3.store(resolve_sym(b"dup3\0"), Ordering::Release);
        REAL_SOCKET.store(resolve_sym(b"socket\0"), Ordering::Release);
        REAL_CONNECT.store(resolve_sym(b"connect\0"), Ordering::Release);
        REAL_ACCEPT.store(resolve_sym(b"accept\0"), Ordering::Release);
        REAL_ACCEPT4.store(resolve_sym(b"accept4\0"), Ordering::Release);

        let mut pread_ptr = resolve_sym(b"pread\0");
        if pread_ptr.is_null() {
            pread_ptr = resolve_sym(b"pread64\0");
        }
        REAL_PREAD.store(pread_ptr, Ordering::Release);

        let mut pwrite_ptr = resolve_sym(b"pwrite\0");
        if pwrite_ptr.is_null() {
            pwrite_ptr = resolve_sym(b"pwrite64\0");
        }
        REAL_PWRITE.store(pwrite_ptr, Ordering::Release);

        REAL_FSYNC.store(resolve_sym(b"fsync\0"), Ordering::Release);
        REAL_FDATASYNC.store(resolve_sym(b"fdatasync\0"), Ordering::Release);
        REAL_EPOLL_CREATE1.store(resolve_sym(b"epoll_create1\0"), Ordering::Release);
        REAL_EPOLL_CTL.store(resolve_sym(b"epoll_ctl\0"), Ordering::Release);
        REAL_EPOLL_WAIT.store(resolve_sym(b"epoll_wait\0"), Ordering::Release);
    }

    INIT_PID.store(pid, Ordering::Release);
    INITIALIZED.store(true, Ordering::Release);
    INITIALIZING.store(false, Ordering::Release);
}

#[cfg(target_os = "linux")]
unsafe fn is_bypassed_process() -> bool {
    // CMP-001 Safeguard: Read /proc/self/comm using raw kernel syscalls to prevent recursion
    // into interposed libc wrappers.
    let fd = libc::syscall(
        libc::SYS_openat,
        libc::AT_FDCWD,
        b"/proc/self/comm\0".as_ptr() as *const libc::c_char,
        libc::O_RDONLY | libc::O_CLOEXEC,
        0,
    ) as c_int;
    if fd < 0 {
        return false;
    }
    let mut buf = [0u8; 64];
    let n = libc::syscall(
        libc::SYS_read,
        fd,
        buf.as_mut_ptr() as *mut libc::c_void,
        buf.len(),
    );
    libc::syscall(libc::SYS_close, fd);
    if n <= 0 {
        return false;
    }
    let len = (n as usize).min(buf.len());
    let bytes = &buf[..len];
    let mut end = bytes.len();
    while end > 0 && (bytes[end - 1] == b'\n' || bytes[end - 1] == b'\r' || bytes[end - 1] == b' ') {
        end -= 1;
    }
    let trimmed = &bytes[..end];

    // Process-name exclusion list:
    // Debuggers, profilers, compilers, linkers, package managers, and alloc-sensitive tools
    const BYPASS_LIST: &[&[u8]] = &[
        b"strace",
        b"gdb",
        b"lldb",
        b"valgrind",
        b"perf",
        b"dpkg",
        b"dpkg-deb",
        b"apt",
        b"apt-get",
        b"apt-cache",
        b"gcc",
        b"g++",
        b"cc",
        b"c++",
        b"clang",
        b"clang++",
        b"ld",
        b"ld.bfd",
        b"ld.gold",
        b"ld.lld",
        b"as",
        b"make",
        b"ninja",
        b"cargo",
        b"rustc",
    ];

    BYPASS_LIST.iter().any(|&item| item == trimmed)
}

#[cfg(not(target_os = "linux"))]
unsafe fn is_bypassed_process() -> bool {
    false
}

fn is_secure_execution() -> bool {
    let cached = IS_SECURE.load(Ordering::Relaxed);
    if cached >= 0 {
        return cached == 1;
    }

    unsafe {
        let is_sec = if libc::getuid() != libc::geteuid() || libc::getgid() != libc::getegid() {
            1
        } else {
            #[cfg(target_os = "linux")]
            let aux = libc::getauxval(libc::AT_SECURE);
            #[cfg(not(target_os = "linux"))]
            let aux = 0;
            if aux != 0 || is_bypassed_process() {
                1
            } else {
                0
            }
        };
        IS_SECURE.store(is_sec, Ordering::Relaxed);
        is_sec == 1
    }
}

fn is_uring_eligible_fd(fd: c_int, count: size_t) -> bool {
    let min_bytes: size_t = match std::env::var("FERRO_IO_MIN_BYTES") {
        Ok(v) => v.parse::<size_t>().unwrap_or(MIN_URING_IO_BYTES),
        Err(_) => MIN_URING_IO_BYTES,
    };
    if count < min_bytes || fd <= 2 || fd as usize >= MAX_CACHED_FDS {
        return false;
    }

    let cached = FD_TYPE_CACHE[fd as usize].load(Ordering::Relaxed);
    if cached != 0 {
        return cached == 2;
    }

    unsafe {
        let mut st: libc::stat = std::mem::zeroed();
        if libc::fstat(fd, &mut st) == 0 && (st.st_mode & S_IFMT) == S_IFREG {
            FD_TYPE_CACHE[fd as usize].store(2, Ordering::Relaxed);
            #[cfg(target_os = "linux")]
            libc::posix_fadvise(fd, 0, 0, libc::POSIX_FADV_RANDOM);
            true
        } else {
            FD_TYPE_CACHE[fd as usize].store(1, Ordering::Relaxed);
            false
        }
    }
}

unsafe fn optimize_tcp_socket(fd: c_int, addr: *const sockaddr, addrlen: socklen_t) {
    if fd < 0 || fd as usize >= MAX_CACHED_FDS {
        return;
    }
    FD_TYPE_CACHE[fd as usize].store(1, Ordering::Relaxed);

    if is_secure_execution() {
        return;
    }

    let one: c_int = 1;
    libc::setsockopt(
        fd,
        IPPROTO_TCP,
        TCP_NODELAY,
        &one as *const _ as *const c_void,
        std::mem::size_of::<c_int>() as socklen_t,
    );

    #[cfg(target_os = "linux")]
    {
        let quickack: c_int = 1;
        libc::setsockopt(
            fd,
            IPPROTO_TCP,
            libc::TCP_QUICKACK,
            &quickack as *const _ as *const c_void,
            std::mem::size_of::<c_int>() as socklen_t,
        );

        let keepalive: c_int = 1;
        libc::setsockopt(
            fd,
            SOL_SOCKET,
            libc::SO_KEEPALIVE,
            &keepalive as *const _ as *const c_void,
            std::mem::size_of::<c_int>() as socklen_t,
        );
    }

    if !addr.is_null() && addrlen >= std::mem::size_of::<libc::sockaddr_in>() as socklen_t {
        let sa_fam = (*addr).sa_family as c_int;
        if sa_fam == AF_INET {
            let in_addr = addr as *const libc::sockaddr_in;
            let ip = u32::from_be((*in_addr).sin_addr.s_addr);
            if (ip >> 24) == 127 {
                let buf_size: c_int = 4194304; // 4MB loopback buffer
                libc::setsockopt(
                    fd,
                    SOL_SOCKET,
                    SO_SNDBUF,
                    &buf_size as *const _ as *const c_void,
                    std::mem::size_of::<c_int>() as socklen_t,
                );
                libc::setsockopt(
                    fd,
                    SOL_SOCKET,
                    SO_RCVBUF,
                    &buf_size as *const _ as *const c_void,
                    std::mem::size_of::<c_int>() as socklen_t,
                );
            }
        }
    }
}

// -------------------------------------------------------------
// POSIX Intercepted Symbols (Exported C ABI)
// -------------------------------------------------------------

#[no_mangle]
pub unsafe extern "C" fn read(fd: c_int, buf: *mut c_void, count: size_t) -> ssize_t {
    if count > SSIZE_MAX as size_t {
        set_errno(EINVAL);
        return -1;
    }

    ensure_symbols_initialized();
    let real_fn: ReadFn = std::mem::transmute(REAL_READ.load(Ordering::Acquire));

    if is_secure_execution() || count < MIN_URING_IO_BYTES || count > u32::MAX as size_t {
        return real_fn(fd, buf, count);
    }

    if is_uring_eligible_fd(fd, count) {
        if let Some(ring) = get_thread_uring() {
            let sqe = io_uring_get_sqe(ring);
            if !sqe.is_null() {
                (*sqe).opcode = IORING_OP_READ;
                (*sqe).flags = 0;
                (*sqe).ioprio = 0;
                (*sqe).fd = fd;
                (*sqe).off = u64::MAX; // -1: use and advance current offset
                (*sqe).addr = buf as u64;
                (*sqe).len = count as u32;
                (*sqe).rw_flags = 0;
                (*sqe).user_data = 0x5244; // 'RD'

                let sret = io_uring_submit_and_wait(ring, 1);
                if sret >= 0 {
                    let mut cqe: *mut IoUringCqe = std::ptr::null_mut();
                    let cret = io_uring_peek_cqe(ring, &mut cqe);
                    if cret == 0 && !cqe.is_null() {
                        let res = (*cqe).res;
                        io_uring_cqe_seen(ring, cqe);
                        if res >= 0 {
                            return res as ssize_t;
                        }
                        if res != -EINVAL && res != -ENOSYS && res != -EOPNOTSUPP {
                            set_errno(-res as c_int);
                            return -1;
                        }
                    }
                }
            }
        }
    }

    real_fn(fd, buf, count)
}

#[no_mangle]
pub unsafe extern "C" fn write(fd: c_int, buf: *const c_void, count: size_t) -> ssize_t {
    if count > SSIZE_MAX as size_t {
        set_errno(EINVAL);
        return -1;
    }

    ensure_symbols_initialized();
    let real_fn: WriteFn = std::mem::transmute(REAL_WRITE.load(Ordering::Acquire));

    if is_secure_execution() || count < MIN_URING_IO_BYTES || count > u32::MAX as size_t {
        return real_fn(fd, buf, count);
    }

    if is_uring_eligible_fd(fd, count) {
        if let Some(ring) = get_thread_uring() {
            let sqe = io_uring_get_sqe(ring);
            if !sqe.is_null() {
                (*sqe).opcode = IORING_OP_WRITE;
                (*sqe).flags = 0;
                (*sqe).ioprio = 0;
                (*sqe).fd = fd;
                (*sqe).off = u64::MAX; // -1: use and advance current offset
                (*sqe).addr = buf as u64;
                (*sqe).len = count as u32;
                (*sqe).rw_flags = 0;
                (*sqe).user_data = 0x5752; // 'WR'

                let sret = io_uring_submit_and_wait(ring, 1);
                if sret >= 0 {
                    let mut cqe: *mut IoUringCqe = std::ptr::null_mut();
                    let cret = io_uring_peek_cqe(ring, &mut cqe);
                    if cret == 0 && !cqe.is_null() {
                        let res = (*cqe).res;
                        io_uring_cqe_seen(ring, cqe);
                        if res >= 0 {
                            return res as ssize_t;
                        }
                        if res != -EINVAL && res != -ENOSYS && res != -EOPNOTSUPP {
                            set_errno(-res as c_int);
                            return -1;
                        }
                    }
                }
            }
        }
    }

    real_fn(fd, buf, count)
}

#[no_mangle]
pub unsafe extern "C" fn pread(
    fd: c_int,
    buf: *mut c_void,
    count: size_t,
    offset: off_t,
) -> ssize_t {
    if count > SSIZE_MAX as size_t {
        set_errno(EINVAL);
        return -1;
    }

    ensure_symbols_initialized();
    let real_fn: PreadFn = std::mem::transmute(REAL_PREAD.load(Ordering::Acquire));

    if is_secure_execution() || count < MIN_URING_IO_BYTES || count > u32::MAX as size_t {
        return real_fn(fd, buf, count, offset);
    }

    if is_uring_eligible_fd(fd, count) {
        if let Some(ring) = get_thread_uring() {
            let sqe = io_uring_get_sqe(ring);
            if !sqe.is_null() {
                (*sqe).opcode = IORING_OP_READ;
                (*sqe).flags = 0;
                (*sqe).ioprio = 0;
                (*sqe).fd = fd;
                (*sqe).off = offset as u64;
                (*sqe).addr = buf as u64;
                (*sqe).len = count as u32;
                (*sqe).rw_flags = 0;
                (*sqe).user_data = 0x5052; // 'PR'

                let sret = io_uring_submit_and_wait(ring, 1);
                if sret >= 0 {
                    let mut cqe: *mut IoUringCqe = std::ptr::null_mut();
                    let cret = io_uring_peek_cqe(ring, &mut cqe);
                    if cret == 0 && !cqe.is_null() {
                        let res = (*cqe).res;
                        io_uring_cqe_seen(ring, cqe);
                        if res >= 0 {
                            return res as ssize_t;
                        }
                        if res != -EINVAL && res != -ENOSYS && res != -EOPNOTSUPP {
                            set_errno(-res as c_int);
                            return -1;
                        }
                    }
                }
            }
        }
    }

    real_fn(fd, buf, count, offset)
}

#[no_mangle]
pub unsafe extern "C" fn pread64(
    fd: c_int,
    buf: *mut c_void,
    count: size_t,
    offset: off_t,
) -> ssize_t {
    pread(fd, buf, count, offset)
}

#[no_mangle]
pub unsafe extern "C" fn pwrite(
    fd: c_int,
    buf: *const c_void,
    count: size_t,
    offset: off_t,
) -> ssize_t {
    if count > SSIZE_MAX as size_t {
        set_errno(EINVAL);
        return -1;
    }

    ensure_symbols_initialized();
    let real_fn: PwriteFn = std::mem::transmute(REAL_PWRITE.load(Ordering::Acquire));

    if is_secure_execution() || count < MIN_URING_IO_BYTES || count > u32::MAX as size_t {
        return real_fn(fd, buf, count, offset);
    }

    if is_uring_eligible_fd(fd, count) {
        if let Some(ring) = get_thread_uring() {
            let sqe = io_uring_get_sqe(ring);
            if !sqe.is_null() {
                (*sqe).opcode = IORING_OP_WRITE;
                (*sqe).flags = 0;
                (*sqe).ioprio = 0;
                (*sqe).fd = fd;
                (*sqe).off = offset as u64;
                (*sqe).addr = buf as u64;
                (*sqe).len = count as u32;
                (*sqe).rw_flags = 0;
                (*sqe).user_data = 0x5057; // 'PW'

                let sret = io_uring_submit_and_wait(ring, 1);
                if sret >= 0 {
                    let mut cqe: *mut IoUringCqe = std::ptr::null_mut();
                    let cret = io_uring_peek_cqe(ring, &mut cqe);
                    if cret == 0 && !cqe.is_null() {
                        let res = (*cqe).res;
                        io_uring_cqe_seen(ring, cqe);
                        if res >= 0 {
                            return res as ssize_t;
                        }
                        if res != -EINVAL && res != -ENOSYS && res != -EOPNOTSUPP {
                            set_errno(-res as c_int);
                            return -1;
                        }
                    }
                }
            }
        }
    }

    real_fn(fd, buf, count, offset)
}

#[no_mangle]
pub unsafe extern "C" fn pwrite64(
    fd: c_int,
    buf: *const c_void,
    count: size_t,
    offset: off_t,
) -> ssize_t {
    pwrite(fd, buf, count, offset)
}

#[no_mangle]
pub unsafe extern "C" fn fdatasync(fd: c_int) -> c_int {
    ensure_symbols_initialized();
    let real_fn: FdatasyncFn = std::mem::transmute(REAL_FDATASYNC.load(Ordering::Acquire));

    if is_secure_execution() {
        return real_fn(fd);
    }

    if is_uring_eligible_fd(fd, 4096) {
        if let Some(ring) = get_thread_uring() {
            let sqe = io_uring_get_sqe(ring);
            if !sqe.is_null() {
                (*sqe).opcode = IORING_OP_FSYNC;
                (*sqe).flags = 0;
                (*sqe).ioprio = 0;
                (*sqe).fd = fd;
                (*sqe).off = 0;
                (*sqe).addr = 0;
                (*sqe).len = 0;
                (*sqe).rw_flags = IORING_FSYNC_DATASYNC;
                (*sqe).user_data = 0x4453; // 'DS'

                let sret = io_uring_submit_and_wait(ring, 1);
                if sret >= 0 {
                    let mut cqe: *mut IoUringCqe = std::ptr::null_mut();
                    let cret = io_uring_peek_cqe(ring, &mut cqe);
                    if cret == 0 && !cqe.is_null() {
                        let res = (*cqe).res;
                        io_uring_cqe_seen(ring, cqe);
                        if res >= 0 {
                            return 0;
                        }
                        if res != -EINVAL && res != -ENOSYS && res != -EOPNOTSUPP {
                            set_errno(-res as c_int);
                            return -1;
                        }
                    }
                }
            }
        }
    }

    real_fn(fd)
}

#[no_mangle]
pub unsafe extern "C" fn fsync(fd: c_int) -> c_int {
    ensure_symbols_initialized();
    let real_fn: FsyncFn = std::mem::transmute(REAL_FSYNC.load(Ordering::Acquire));

    if is_secure_execution() {
        return real_fn(fd);
    }

    if is_uring_eligible_fd(fd, 4096) {
        if let Some(ring) = get_thread_uring() {
            let sqe = io_uring_get_sqe(ring);
            if !sqe.is_null() {
                (*sqe).opcode = IORING_OP_FSYNC;
                (*sqe).flags = 0;
                (*sqe).ioprio = 0;
                (*sqe).fd = fd;
                (*sqe).off = 0;
                (*sqe).addr = 0;
                (*sqe).len = 0;
                (*sqe).rw_flags = 0;
                (*sqe).user_data = 0x4653; // 'FS'

                let sret = io_uring_submit_and_wait(ring, 1);
                if sret >= 0 {
                    let mut cqe: *mut IoUringCqe = std::ptr::null_mut();
                    let cret = io_uring_peek_cqe(ring, &mut cqe);
                    if cret == 0 && !cqe.is_null() {
                        let res = (*cqe).res;
                        io_uring_cqe_seen(ring, cqe);
                        if res >= 0 {
                            return 0;
                        }
                        if res != -EINVAL && res != -ENOSYS && res != -EOPNOTSUPP {
                            set_errno(-res as c_int);
                            return -1;
                        }
                    }
                }
            }
        }
    }

    real_fn(fd)
}

#[no_mangle]
pub unsafe extern "C" fn close(fd: c_int) -> c_int {
    if fd >= 0 && (fd as usize) < MAX_CACHED_FDS {
        FD_TYPE_CACHE[fd as usize].store(0, Ordering::Relaxed);
    }
    ensure_symbols_initialized();
    let real_fn: CloseFn = std::mem::transmute(REAL_CLOSE.load(Ordering::Acquire));
    real_fn(fd)
}

#[no_mangle]
pub unsafe extern "C" fn dup2(oldfd: c_int, newfd: c_int) -> c_int {
    if newfd >= 0 && (newfd as usize) < MAX_CACHED_FDS {
        FD_TYPE_CACHE[newfd as usize].store(0, Ordering::Relaxed);
    }
    ensure_symbols_initialized();
    let real_fn: Dup2Fn = std::mem::transmute(REAL_DUP2.load(Ordering::Acquire));
    real_fn(oldfd, newfd)
}

#[no_mangle]
pub unsafe extern "C" fn dup3(oldfd: c_int, newfd: c_int, flags: c_int) -> c_int {
    if newfd >= 0 && (newfd as usize) < MAX_CACHED_FDS {
        FD_TYPE_CACHE[newfd as usize].store(0, Ordering::Relaxed);
    }
    ensure_symbols_initialized();
    let real_fn: Dup3Fn = std::mem::transmute(REAL_DUP3.load(Ordering::Acquire));
    real_fn(oldfd, newfd, flags)
}

#[no_mangle]
pub unsafe extern "C" fn socket(domain: c_int, socket_type: c_int, protocol: c_int) -> c_int {
    ensure_symbols_initialized();
    let real_fn: SocketFn = std::mem::transmute(REAL_SOCKET.load(Ordering::Acquire));
    let fd = real_fn(domain, socket_type, protocol);

    if fd >= 0 && (fd as usize) < MAX_CACHED_FDS {
        FD_TYPE_CACHE[fd as usize].store(1, Ordering::Relaxed);
        if !is_secure_execution()
            && (domain == AF_INET || domain == AF_INET6)
            && (socket_type & libc::SOCK_STREAM) != 0
        {
            let one: c_int = 1;
            libc::setsockopt(
                fd,
                IPPROTO_TCP,
                TCP_NODELAY,
                &one as *const _ as *const c_void,
                std::mem::size_of::<c_int>() as socklen_t,
            );
        }
    }

    fd
}

#[no_mangle]
pub unsafe extern "C" fn connect(
    sockfd: c_int,
    addr: *const sockaddr,
    addrlen: socklen_t,
) -> c_int {
    ensure_symbols_initialized();
    optimize_tcp_socket(sockfd, addr, addrlen);
    let real_fn: ConnectFn = std::mem::transmute(REAL_CONNECT.load(Ordering::Acquire));
    real_fn(sockfd, addr, addrlen)
}

#[no_mangle]
pub unsafe extern "C" fn accept(
    sockfd: c_int,
    addr: *mut sockaddr,
    addrlen: *mut socklen_t,
) -> c_int {
    ensure_symbols_initialized();
    let real_fn: AcceptFn = std::mem::transmute(REAL_ACCEPT.load(Ordering::Acquire));
    let fd = real_fn(sockfd, addr, addrlen);
    if fd >= 0 {
        let len = if addrlen.is_null() { 0 } else { *addrlen };
        optimize_tcp_socket(fd, addr, len);
    }
    fd
}

#[no_mangle]
pub unsafe extern "C" fn accept4(
    sockfd: c_int,
    addr: *mut sockaddr,
    addrlen: *mut socklen_t,
    flags: c_int,
) -> c_int {
    ensure_symbols_initialized();
    let real_fn: Accept4Fn = std::mem::transmute(REAL_ACCEPT4.load(Ordering::Acquire));
    let fd = real_fn(sockfd, addr, addrlen, flags);
    if fd >= 0 {
        let len = if addrlen.is_null() { 0 } else { *addrlen };
        optimize_tcp_socket(fd, addr, len);
    }
    fd
}

#[no_mangle]
pub unsafe extern "C" fn epoll_create1(flags: c_int) -> c_int {
    ensure_symbols_initialized();
    let real_fn: EpollCreate1Fn = std::mem::transmute(REAL_EPOLL_CREATE1.load(Ordering::Acquire));
    real_fn(flags)
}

#[no_mangle]
pub unsafe extern "C" fn epoll_ctl(epfd: c_int, op: c_int, fd: c_int, event: *mut c_void) -> c_int {
    ensure_symbols_initialized();
    let real_fn: EpollCtlFn = std::mem::transmute(REAL_EPOLL_CTL.load(Ordering::Acquire));
    real_fn(epfd, op, fd, event)
}

#[no_mangle]
pub unsafe extern "C" fn epoll_wait(
    epfd: c_int,
    events: *mut c_void,
    maxevents: c_int,
    timeout: c_int,
) -> c_int {
    ensure_symbols_initialized();
    let real_fn: EpollWaitFn = std::mem::transmute(REAL_EPOLL_WAIT.load(Ordering::Acquire));
    real_fn(epfd, events, maxevents, timeout)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fd_cache_bounds_and_lifecycle() {
        assert_eq!(MAX_CACHED_FDS, 131072);

        let test_fd: usize = 1000;
        assert_eq!(FD_TYPE_CACHE[test_fd].load(Ordering::Relaxed), 0);

        // Mark as regular file eligible
        FD_TYPE_CACHE[test_fd].store(2, Ordering::Relaxed);
        assert_eq!(FD_TYPE_CACHE[test_fd].load(Ordering::Relaxed), 2);

        // Simulated close resets cache
        if test_fd < MAX_CACHED_FDS {
            FD_TYPE_CACHE[test_fd].store(0, Ordering::Relaxed);
        }
        assert_eq!(FD_TYPE_CACHE[test_fd].load(Ordering::Relaxed), 0);
    }

    #[test]
    fn test_min_uring_io_bytes() {
        assert_eq!(MIN_URING_IO_BYTES, 4096);
        assert!(!is_uring_eligible_fd(5, 512));
    }

    #[test]
    fn test_queue_entries_bounds() {
        assert_eq!(FERRO_URING_ENTRIES, 256);
    }
}
