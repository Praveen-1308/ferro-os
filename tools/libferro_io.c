/*
 * NOTICE: LEGACY C REFERENCE IMPLEMENTATION.
 * SUPERSEDED BY PURE-RUST cdylib: `crates/ferro-io` (target/release/libferro_io.so).
 * All official builds and container environments exclusively utilize the pure-Rust
 * implementation providing memory-safe io_uring submission, SQPOLL acceleration,
 * atomic FD classification, and zero-latency TCP loopback optimization.
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <errno.h>
#include <limits.h>
#if defined(__linux__)
#include <sys/auxv.h>
#endif
#include <liburing.h>

/*
 * libferro_io.so - High-Performance POSIX I/O Interposition Shim v2.2 (Hardened)
 *
 * Security & Defensive Invariants:
 *  1. AT_SECURE & SUID Safety:
 *     - If running in privileged/setuid context or AT_SECURE mode, disables all
 *       unsafe manipulations and passes straight through to libc/syscalls.
 *  2. Integer Overflow & Size Boundary Protection:
 *     - Clamps size_t counts exceeding SSIZE_MAX and returns EINVAL per POSIX standard.
 *  3. Dynamic Lock-Free FD Cache Thrash Protection:
 *     - Array of 65,536 slots: 0=unknown, 1=bypass (socket/pipe/TTY), 2=regular file.
 *     - Handles descriptor recycling safely by intercepting close(), dup2(), and dup3().
 *     - Descriptors >= 65,536 automatically safe-bypass the cache table without out-of-bounds indexing.
 *  4. Fork & Thread Safety:
 *     - pthread_atfork handlers ensure clean mutex and state reset across fork boundaries.
 *  5. Local Socket Acceleration:
 *     - Automatically enables TCP_NODELAY and TCP_QUICKACK on non-secure TCP streams.
 */

#define MAX_CACHED_FDS 65536
// 0 = unknown, 1 = bypass (socket/pipe/TTY/char), 2 = regular_file_eligible
static uint8_t g_fd_type_cache[MAX_CACHED_FDS];

typedef ssize_t (*real_read_fn)(int fd, void *buf, size_t count);
typedef ssize_t (*real_write_fn)(int fd, const void *buf, size_t count);
typedef int (*real_close_fn)(int fd);
typedef int (*real_dup2_fn)(int oldfd, int newfd);
typedef int (*real_dup3_fn)(int oldfd, int newfd, int flags);
typedef int (*real_socket_fn)(int domain, int type, int protocol);
typedef int (*real_epoll_create1_fn)(int flags);
typedef int (*real_epoll_ctl_fn)(int epfd, int op, int fd, struct epoll_event *event);
typedef int (*real_epoll_wait_fn)(int epfd, struct epoll_event *events, int maxevents, int timeout);
typedef int (*real_connect_fn)(int sockfd, const struct sockaddr *addr, socklen_t addrlen);
typedef int (*real_accept_fn)(int sockfd, struct sockaddr *addr, socklen_t *addrlen);
typedef int (*real_accept4_fn)(int sockfd, struct sockaddr *addr, socklen_t *addrlen, int flags);
typedef ssize_t (*real_pread_fn)(int fd, void *buf, size_t count, off_t offset);
typedef ssize_t (*real_pwrite_fn)(int fd, const void *buf, size_t count, off_t offset);
typedef int (*real_fsync_fn)(int fd);
typedef int (*real_fdatasync_fn)(int fd);

static real_read_fn g_real_read = NULL;
static real_write_fn g_real_write = NULL;
static real_close_fn g_real_close = NULL;
static real_dup2_fn g_real_dup2 = NULL;
static real_dup3_fn g_real_dup3 = NULL;
static real_socket_fn g_real_socket = NULL;
static real_epoll_create1_fn g_real_epoll_create1 = NULL;
static real_epoll_ctl_fn g_real_epoll_ctl = NULL;
static real_epoll_wait_fn g_real_epoll_wait = NULL;
static real_connect_fn g_real_connect = NULL;
static real_accept_fn g_real_accept = NULL;
static real_accept4_fn g_real_accept4 = NULL;
static real_pread_fn g_real_pread = NULL;
static real_pwrite_fn g_real_pwrite = NULL;
static real_fsync_fn g_real_fsync = NULL;
static real_fdatasync_fn g_real_fdatasync = NULL;

static pthread_mutex_t g_init_mutex = PTHREAD_MUTEX_INITIALIZER;
static atomic_int g_initialized = 0;
static pid_t g_ring_pid = 0;
static int g_is_secure = -1;

#define FERRO_URING_ENTRIES 64

static __thread struct io_uring t_ring;
static __thread int t_ring_inited = 0;
static __thread pid_t t_ring_pid = 0;

static inline struct io_uring *get_thread_uring(void) {
    pid_t pid = getpid();
    if (__builtin_expect(!t_ring_inited || t_ring_pid != pid, 0)) {
        if (t_ring_inited && t_ring_pid != pid) {
            io_uring_queue_exit(&t_ring);
            t_ring_inited = 0;
        }

        struct io_uring_params params;
        memset(&params, 0, sizeof(params));
        // Attempt kernel SQPOLL (Submission Queue Polling thread) with 2000ms idle timeout
        params.flags = IORING_SETUP_SQPOLL;
        params.sq_thread_idle = 2000;

        int ret = io_uring_queue_init_params(FERRO_URING_ENTRIES, &t_ring, &params);
        if (ret < 0) {
            // SQPOLL may require elevated privileges; fall back to SINGLE_ISSUER or standard ring
            memset(&params, 0, sizeof(params));
#ifdef IORING_SETUP_SINGLE_ISSUER
            params.flags = IORING_SETUP_SINGLE_ISSUER;
            ret = io_uring_queue_init_params(FERRO_URING_ENTRIES, &t_ring, &params);
            if (ret < 0)
#endif
            {
                ret = io_uring_queue_init(FERRO_URING_ENTRIES, &t_ring, 0);
                if (ret < 0) {
                    return NULL;
                }
            }
        }
        t_ring_inited = 1;
        t_ring_pid = pid;
    }
    return &t_ring;
}

static inline int is_secure_execution(void) {
    if (__builtin_expect(g_is_secure >= 0, 1)) return g_is_secure;
#if defined(AT_SECURE)
    unsigned long aux = getauxval(AT_SECURE);
    if (aux != 0) {
        g_is_secure = 1;
        return 1;
    }
#endif
    if (getuid() != geteuid() || getgid() != getegid()) {
        g_is_secure = 1;
        return 1;
    }
    g_is_secure = 0;
    return 0;
}

static void init_real_symbols(void) {
    if (atomic_load(&g_initialized) && g_ring_pid == getpid()) return;

    pthread_mutex_lock(&g_init_mutex);

    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        g_real_read = (real_read_fn)dlsym(RTLD_NEXT, "read");
        g_real_write = (real_write_fn)dlsym(RTLD_NEXT, "write");
        g_real_close = (real_close_fn)dlsym(RTLD_NEXT, "close");
        g_real_dup2 = (real_dup2_fn)dlsym(RTLD_NEXT, "dup2");
        g_real_dup3 = (real_dup3_fn)dlsym(RTLD_NEXT, "dup3");
        g_real_socket = (real_socket_fn)dlsym(RTLD_NEXT, "socket");
        g_real_epoll_create1 = (real_epoll_create1_fn)dlsym(RTLD_NEXT, "epoll_create1");
        g_real_epoll_ctl = (real_epoll_ctl_fn)dlsym(RTLD_NEXT, "epoll_ctl");
        g_real_epoll_wait = (real_epoll_wait_fn)dlsym(RTLD_NEXT, "epoll_wait");
        g_real_connect = (real_connect_fn)dlsym(RTLD_NEXT, "connect");
        g_real_accept = (real_accept_fn)dlsym(RTLD_NEXT, "accept");
        g_real_accept4 = (real_accept4_fn)dlsym(RTLD_NEXT, "accept4");
        g_real_pread = (real_pread_fn)dlsym(RTLD_NEXT, "pread");
        if (!g_real_pread) g_real_pread = (real_pread_fn)dlsym(RTLD_NEXT, "pread64");
        g_real_pwrite = (real_pwrite_fn)dlsym(RTLD_NEXT, "pwrite");
        if (!g_real_pwrite) g_real_pwrite = (real_pwrite_fn)dlsym(RTLD_NEXT, "pwrite64");
        g_real_fsync = (real_fsync_fn)dlsym(RTLD_NEXT, "fsync");
        g_real_fdatasync = (real_fdatasync_fn)dlsym(RTLD_NEXT, "fdatasync");

        g_ring_pid = getpid();
        atomic_store(&g_initialized, 1);
    }

    pthread_mutex_unlock(&g_init_mutex);
}

// Fork safety handlers
static void atfork_prepare(void) {
    pthread_mutex_lock(&g_init_mutex);
}

static void atfork_parent(void) {
    pthread_mutex_unlock(&g_init_mutex);
}

static void atfork_child(void) {
    pthread_mutex_init(&g_init_mutex, NULL);
    g_ring_pid = getpid();
    t_ring_inited = 0;
    for (int i = 0; i < MAX_CACHED_FDS; i++) {
        g_fd_type_cache[i] = 0;
    }
    atomic_store(&g_initialized, 0);
    g_is_secure = -1;
    init_real_symbols();
}

static inline int is_uring_eligible_fd(int fd, size_t count) {
    // Invariant 1: Transfers < 64 KB bypass io_uring immediately
    if (count < 65536) return 0;

    // Standard streams and out-of-range FDs always bypass safely
    if (fd <= 2 || fd >= MAX_CACHED_FDS) return 0;

    uint8_t cached = __atomic_load_n(&g_fd_type_cache[fd], __ATOMIC_RELAXED);
    if (__builtin_expect(cached != 0, 1)) {
        return (cached == 2);
    }

    // Call fstat at most ONCE per file descriptor lifecycle
    struct stat st;
    if (fstat(fd, &st) == 0 && S_ISREG(st.st_mode)) {
        __atomic_store_n(&g_fd_type_cache[fd], 2, __ATOMIC_RELAXED);
        // Optimize readahead for database B-tree file accesses
        posix_fadvise(fd, 0, 0, POSIX_FADV_RANDOM);
        return 1;
    } else {
        __atomic_store_n(&g_fd_type_cache[fd], 1, __ATOMIC_RELAXED);
        return 0;
    }
}

// Intercept socket() to configure TCP_NODELAY and mark as bypass immediately
int socket(int domain, int type, int protocol) {
    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        init_real_symbols();
    }
    int fd = g_real_socket ? g_real_socket(domain, type, protocol) : syscall(SYS_socket, domain, type, protocol);
    if (fd >= 0 && fd < MAX_CACHED_FDS) {
        __atomic_store_n(&g_fd_type_cache[fd], 1, __ATOMIC_RELAXED);
        if (!is_secure_execution() && (domain == AF_INET || domain == AF_INET6)) {
            if ((type & SOCK_STREAM) != 0) {
                int one = 1;
                setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
#ifdef TCP_QUICKACK
                setsockopt(fd, IPPROTO_TCP, TCP_QUICKACK, &one, sizeof(one));
#endif
            }
        }
    }
    return fd;
}

static inline void optimize_tcp_socket(int fd, const struct sockaddr *addr, socklen_t addrlen) {
    if (fd < 0 || fd >= MAX_CACHED_FDS) return;
    __atomic_store_n(&g_fd_type_cache[fd], 1, __ATOMIC_RELAXED);
    if (is_secure_execution()) return;

    int one = 1;
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
#ifdef TCP_QUICKACK
    setsockopt(fd, IPPROTO_TCP, TCP_QUICKACK, &one, sizeof(one));
#endif
    if (addr && addrlen >= sizeof(struct sockaddr_in) && addr->sa_family == AF_INET) {
        const struct sockaddr_in *in = (const struct sockaddr_in *)addr;
        uint32_t ip = ntohl(in->sin_addr.s_addr);
        if ((ip >> 24) == 127) {
            // Local loopback network bypass: maximize socket buffers to 4MB to prevent TCP window stalls
            int buf_size = 4194304;
            setsockopt(fd, SOL_SOCKET, SO_SNDBUF, &buf_size, sizeof(buf_size));
            setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &buf_size, sizeof(buf_size));
        }
    }
}

int connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        init_real_symbols();
    }
    optimize_tcp_socket(sockfd, addr, addrlen);
    if (g_real_connect) return g_real_connect(sockfd, addr, addrlen);
#if defined(SYS_connect)
    return syscall(SYS_connect, sockfd, addr, addrlen);
#else
    return -1;
#endif
}

int accept(int sockfd, struct sockaddr *addr, socklen_t *addrlen) {
    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        init_real_symbols();
    }
    int fd = -1;
    if (g_real_accept) {
        fd = g_real_accept(sockfd, addr, addrlen);
    } else {
#if defined(SYS_accept)
        fd = syscall(SYS_accept, sockfd, addr, addrlen);
#endif
    }
    if (fd >= 0) {
        optimize_tcp_socket(fd, addr, addrlen ? *addrlen : 0);
    }
    return fd;
}

int accept4(int sockfd, struct sockaddr *addr, socklen_t *addrlen, int flags) {
    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        init_real_symbols();
    }
    int fd = -1;
    if (g_real_accept4) {
        fd = g_real_accept4(sockfd, addr, addrlen, flags);
    } else {
#if defined(SYS_accept4)
        fd = syscall(SYS_accept4, sockfd, addr, addrlen, flags);
#endif
    }
    if (fd >= 0) {
        optimize_tcp_socket(fd, addr, addrlen ? *addrlen : 0);
    }
    return fd;
}

// Hook close() to invalidate cached FD type when an FD is recycled
int close(int fd) {
    if (fd >= 0 && fd < MAX_CACHED_FDS) {
        __atomic_store_n(&g_fd_type_cache[fd], 0, __ATOMIC_RELAXED);
    }
    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        init_real_symbols();
        if (!g_real_close) return syscall(SYS_close, fd);
    }
    return g_real_close(fd);
}

// Hook dup2 and dup3 to prevent stale FD cache entries
int dup2(int oldfd, int newfd) {
    if (newfd >= 0 && newfd < MAX_CACHED_FDS) {
        __atomic_store_n(&g_fd_type_cache[newfd], 0, __ATOMIC_RELAXED);
    }
    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        init_real_symbols();
    }
    if (g_real_dup2) return g_real_dup2(oldfd, newfd);
#if defined(SYS_dup2)
    return syscall(SYS_dup2, oldfd, newfd);
#elif defined(SYS_dup3)
    return syscall(SYS_dup3, oldfd, newfd, 0);
#else
    return -1;
#endif
}

int dup3(int oldfd, int newfd, int flags) {
    if (newfd >= 0 && newfd < MAX_CACHED_FDS) {
        __atomic_store_n(&g_fd_type_cache[newfd], 0, __ATOMIC_RELAXED);
    }
    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        init_real_symbols();
    }
#if defined(SYS_dup3)
    return g_real_dup3 ? g_real_dup3(oldfd, newfd, flags) : syscall(SYS_dup3, oldfd, newfd, flags);
#else
    return -1;
#endif
}

__attribute__((constructor))
static void ferro_io_init(void) {
    pthread_atfork(atfork_prepare, atfork_parent, atfork_child);
}

ssize_t read(int fd, void *buf, size_t count) {
    // Integer overflow protection per POSIX SSIZE_MAX standard
    if (__builtin_expect(count > SSIZE_MAX, 0)) {
        errno = EINVAL;
        return -1;
    }

    if (is_secure_execution()) {
        if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
            init_real_symbols();
            if (!g_real_read) return syscall(SYS_read, fd, buf, count);
        }
        return g_real_read(fd, buf, count);
    }

    // Fast-path: Small reads < 64KB bypass io_uring and fstat checks entirely
    if (__builtin_expect(count < 65536, 1)) {
        if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
            init_real_symbols();
            if (!g_real_read) return syscall(SYS_read, fd, buf, count);
        }
        return g_real_read(fd, buf, count);
    }

    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        init_real_symbols();
        if (!g_real_read) return syscall(SYS_read, fd, buf, count);
    }

    if (is_uring_eligible_fd(fd, count)) {
        struct io_uring *ring = get_thread_uring();
        if (ring) {
            struct io_uring_sqe *sqe = io_uring_get_sqe(ring);
            if (sqe) {
                // Offset (__u64)-1 instructs Linux io_uring to use and advance current file offset (POSIX read semantics)
                io_uring_prep_read(sqe, fd, buf, (unsigned int)count, (__u64)-1);
                int sret = io_uring_submit_and_wait(ring, 1);
                if (sret >= 0) {
                    struct io_uring_cqe *cqe = NULL;
                    int cret = io_uring_peek_cqe(ring, &cqe);
                    if (cret == 0 && cqe) {
                        int res = cqe->res;
                        io_uring_cqe_seen(ring, cqe);
                        if (res >= 0) {
                            return (ssize_t)res;
                        }
                        if (res != -EINVAL && res != -ENOSYS && res != -EOPNOTSUPP) {
                            errno = -res;
                            return -1;
                        }
                    }
                }
            }
        }
    }

    return g_real_read(fd, buf, count);
}

ssize_t write(int fd, const void *buf, size_t count) {
    // Integer overflow protection per POSIX SSIZE_MAX standard
    if (__builtin_expect(count > SSIZE_MAX, 0)) {
        errno = EINVAL;
        return -1;
    }

    if (is_secure_execution()) {
        if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
            init_real_symbols();
            if (!g_real_write) return syscall(SYS_write, fd, buf, count);
        }
        return g_real_write(fd, buf, count);
    }

    // Fast-path: Small writes < 64KB bypass io_uring and fstat checks entirely
    if (__builtin_expect(count < 65536, 1)) {
        if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
            init_real_symbols();
            if (!g_real_write) return syscall(SYS_write, fd, buf, count);
        }
        return g_real_write(fd, buf, count);
    }

    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        init_real_symbols();
        if (!g_real_write) return syscall(SYS_write, fd, buf, count);
    }

    if (is_uring_eligible_fd(fd, count)) {
        struct io_uring *ring = get_thread_uring();
        if (ring) {
            struct io_uring_sqe *sqe = io_uring_get_sqe(ring);
            if (sqe) {
                // Offset (__u64)-1 instructs Linux io_uring to use and advance current file offset (POSIX write semantics)
                io_uring_prep_write(sqe, fd, buf, (unsigned int)count, (__u64)-1);
                int sret = io_uring_submit_and_wait(ring, 1);
                if (sret >= 0) {
                    struct io_uring_cqe *cqe = NULL;
                    int cret = io_uring_peek_cqe(ring, &cqe);
                    if (cret == 0 && cqe) {
                        int res = cqe->res;
                        io_uring_cqe_seen(ring, cqe);
                        if (res >= 0) {
                            return (ssize_t)res;
                        }
                        if (res != -EINVAL && res != -ENOSYS && res != -EOPNOTSUPP) {
                            errno = -res;
                            return -1;
                        }
                    }
                }
            }
        }
    }

    return g_real_write(fd, buf, count);
}

/*
 * Transparent io_uring pread & pread64 Interception
 */
ssize_t pread(int fd, void *buf, size_t count, off_t offset) {
    if (__builtin_expect(count > SSIZE_MAX, 0)) {
        errno = EINVAL;
        return -1;
    }
    if (is_secure_execution() || __builtin_expect(count < 65536, 1)) {
        if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
            init_real_symbols();
            if (!g_real_pread) return syscall(SYS_pread64, fd, buf, count, offset);
        }
        return g_real_pread(fd, buf, count, offset);
    }
    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        init_real_symbols();
        if (!g_real_pread) return syscall(SYS_pread64, fd, buf, count, offset);
    }
    if (is_uring_eligible_fd(fd, count)) {
        struct io_uring *ring = get_thread_uring();
        if (ring) {
            struct io_uring_sqe *sqe = io_uring_get_sqe(ring);
            if (sqe) {
                io_uring_prep_read(sqe, fd, buf, (unsigned int)count, (__u64)offset);
                int sret = io_uring_submit_and_wait(ring, 1);
                if (sret >= 0) {
                    struct io_uring_cqe *cqe = NULL;
                    int cret = io_uring_peek_cqe(ring, &cqe);
                    if (cret == 0 && cqe) {
                        int res = cqe->res;
                        io_uring_cqe_seen(ring, cqe);
                        if (res >= 0) {
                            return (ssize_t)res;
                        }
                        if (res != -EINVAL && res != -ENOSYS && res != -EOPNOTSUPP) {
                            errno = -res;
                            return -1;
                        }
                    }
                }
            }
        }
    }
    return g_real_pread(fd, buf, count, offset);
}

ssize_t pread64(int fd, void *buf, size_t count, off_t offset) {
    return pread(fd, buf, count, offset);
}

/*
 * Transparent io_uring pwrite & pwrite64 Interception
 */
ssize_t pwrite(int fd, const void *buf, size_t count, off_t offset) {
    if (__builtin_expect(count > SSIZE_MAX, 0)) {
        errno = EINVAL;
        return -1;
    }
    if (is_secure_execution() || __builtin_expect(count < 65536, 1)) {
        if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
            init_real_symbols();
            if (!g_real_pwrite) return syscall(SYS_pwrite64, fd, buf, count, offset);
        }
        return g_real_pwrite(fd, buf, count, offset);
    }
    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        init_real_symbols();
        if (!g_real_pwrite) return syscall(SYS_pwrite64, fd, buf, count, offset);
    }
    if (is_uring_eligible_fd(fd, count)) {
        struct io_uring *ring = get_thread_uring();
        if (ring) {
            struct io_uring_sqe *sqe = io_uring_get_sqe(ring);
            if (sqe) {
                io_uring_prep_write(sqe, fd, buf, (unsigned int)count, (__u64)offset);
                int sret = io_uring_submit_and_wait(ring, 1);
                if (sret >= 0) {
                    struct io_uring_cqe *cqe = NULL;
                    int cret = io_uring_peek_cqe(ring, &cqe);
                    if (cret == 0 && cqe) {
                        int res = cqe->res;
                        io_uring_cqe_seen(ring, cqe);
                        if (res >= 0) {
                            return (ssize_t)res;
                        }
                        if (res != -EINVAL && res != -ENOSYS && res != -EOPNOTSUPP) {
                            errno = -res;
                            return -1;
                        }
                    }
                }
            }
        }
    }
    return g_real_pwrite(fd, buf, count, offset);
}

ssize_t pwrite64(int fd, const void *buf, size_t count, off_t offset) {
    return pwrite(fd, buf, count, offset);
}

/*
 * Transparent io_uring fsync & fdatasync Interception
 */
int fdatasync(int fd) {
    if (is_secure_execution()) {
        if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
            init_real_symbols();
            if (!g_real_fdatasync) return syscall(SYS_fdatasync, fd);
        }
        return g_real_fdatasync(fd);
    }
    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        init_real_symbols();
        if (!g_real_fdatasync) return syscall(SYS_fdatasync, fd);
    }
    if (is_uring_eligible_fd(fd, 4096)) {
        struct io_uring *ring = get_thread_uring();
        if (ring) {
            struct io_uring_sqe *sqe = io_uring_get_sqe(ring);
            if (sqe) {
                io_uring_prep_fsync(sqe, fd, IORING_FSYNC_DATASYNC);
                int sret = io_uring_submit_and_wait(ring, 1);
                if (sret >= 0) {
                    struct io_uring_cqe *cqe = NULL;
                    int cret = io_uring_peek_cqe(ring, &cqe);
                    if (cret == 0 && cqe) {
                        int res = cqe->res;
                        io_uring_cqe_seen(ring, cqe);
                        if (res >= 0) {
                            return 0;
                        }
                        if (res != -EINVAL && res != -ENOSYS && res != -EOPNOTSUPP) {
                            errno = -res;
                            return -1;
                        }
                    }
                }
            }
        }
    }
    return g_real_fdatasync(fd);
}

int fsync(int fd) {
    if (is_secure_execution()) {
        if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
            init_real_symbols();
            if (!g_real_fsync) return syscall(SYS_fsync, fd);
        }
        return g_real_fsync(fd);
    }
    if (!atomic_load(&g_initialized) || g_ring_pid != getpid()) {
        init_real_symbols();
        if (!g_real_fsync) return syscall(SYS_fsync, fd);
    }
    if (is_uring_eligible_fd(fd, 4096)) {
        struct io_uring *ring = get_thread_uring();
        if (ring) {
            struct io_uring_sqe *sqe = io_uring_get_sqe(ring);
            if (sqe) {
                io_uring_prep_fsync(sqe, fd, 0);
                int sret = io_uring_submit_and_wait(ring, 1);
                if (sret >= 0) {
                    struct io_uring_cqe *cqe = NULL;
                    int cret = io_uring_peek_cqe(ring, &cqe);
                    if (cret == 0 && cqe) {
                        int res = cqe->res;
                        io_uring_cqe_seen(ring, cqe);
                        if (res >= 0) {
                            return 0;
                        }
                        if (res != -EINVAL && res != -ENOSYS && res != -EOPNOTSUPP) {
                            errno = -res;
                            return -1;
                        }
                    }
                }
            }
        }
    }
    return g_real_fsync(fd);
}

/*
 * Epoll Dynamic Emulation & Pass-Through
 */
int epoll_create1(int flags) {
    if (!atomic_load(&g_initialized)) {
        return syscall(SYS_epoll_create1, flags);
    }
    if (g_real_epoll_create1) {
        return g_real_epoll_create1(flags);
    }
    return syscall(SYS_epoll_create1, flags);
}

int epoll_ctl(int epfd, int op, int fd, struct epoll_event *event) {
    if (!atomic_load(&g_initialized)) {
        return syscall(SYS_epoll_ctl, epfd, op, fd, event);
    }
    if (g_real_epoll_ctl) {
        return g_real_epoll_ctl(epfd, op, fd, event);
    }
    return syscall(SYS_epoll_ctl, epfd, op, fd, event);
}

int epoll_wait(int epfd, struct epoll_event *events, int maxevents, int timeout) {
    if (!atomic_load(&g_initialized)) {
#if defined(SYS_epoll_pwait)
        return syscall(SYS_epoll_pwait, epfd, events, maxevents, timeout, NULL);
#elif defined(SYS_epoll_wait)
        return syscall(SYS_epoll_wait, epfd, events, maxevents, timeout);
#else
        return -1;
#endif
    }
    if (g_real_epoll_wait) {
        return g_real_epoll_wait(epfd, events, maxevents, timeout);
    }
#if defined(SYS_epoll_pwait)
    return syscall(SYS_epoll_pwait, epfd, events, maxevents, timeout, NULL);
#elif defined(SYS_epoll_wait)
    return syscall(SYS_epoll_wait, epfd, events, maxevents, timeout);
#else
    return -1;
#endif
}
