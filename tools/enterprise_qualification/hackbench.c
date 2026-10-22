/*
 * hackbench.c - Scheduler benchmark
 * Compatible with rt-tests hackbench
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <pthread.h>
#include <fcntl.h>

static unsigned int num_groups = 10;
static unsigned int total_children = 20;
static unsigned int loops = 100;
static unsigned int datasize = 100;
static int use_pipes = 0;
static int use_threads = 0;

struct child_data {
    int read_fd;
    int *write_fds;
    unsigned int num_writes;
};

static void barf(const char *msg) {
    perror(msg);
    exit(1);
}

static void fdpair(int fds[2]) {
    if (use_pipes) {
        if (pipe(fds) < 0)
            barf("pipe");
    } else {
        if (socketpair(AF_UNIX, SOCK_STREAM, 0, fds) < 0)
            barf("socketpair");
    }
}

static void *receiver(void *arg) {
    int fd = (int)(intptr_t)arg;
    char *buf = malloc(datasize);
    if (!buf) barf("malloc");

    unsigned int total = loops * total_children * datasize;
    unsigned int recvd = 0;

    while (recvd < total) {
        ssize_t n = read(fd, buf, datasize);
        if (n <= 0) {
            if (n < 0 && (errno == EINTR || errno == EAGAIN)) continue;
            break;
        }
        recvd += n;
    }

    free(buf);
    close(fd);
    return NULL;
}

static void *sender(void *arg) {
    struct child_data *data = (struct child_data *)arg;
    char *buf = malloc(datasize);
    if (!buf) barf("malloc");
    memset(buf, 'X', datasize);

    for (unsigned int l = 0; l < loops; l++) {
        for (unsigned int i = 0; i < data->num_writes; i++) {
            unsigned int written = 0;
            while (written < datasize) {
                ssize_t n = write(data->write_fds[i], buf + written, datasize - written);
                if (n <= 0) {
                    if (n < 0 && (errno == EINTR || errno == EAGAIN)) continue;
                    break;
                }
                written += n;
            }
        }
    }

    free(buf);
    return NULL;
}

static unsigned int group(pthread_t *threads, unsigned int thread_idx) {
    int r_fds[total_children][2];
    for (unsigned int i = 0; i < total_children; i++) {
        fdpair(r_fds[i]);
    }

    int *w_fds = malloc(total_children * sizeof(int));
    if (!w_fds) barf("malloc");
    for (unsigned int i = 0; i < total_children; i++) {
        w_fds[i] = r_fds[i][1];
    }

    for (unsigned int i = 0; i < total_children; i++) {
        if (use_threads) {
            if (pthread_create(&threads[thread_idx++], NULL, receiver, (void *)(intptr_t)r_fds[i][0]) != 0)
                barf("pthread_create receiver");
        } else {
            pid_t pid = fork();
            if (pid < 0) barf("fork receiver");
            if (pid == 0) {
                for (unsigned int j = 0; j < total_children; j++) {
                    close(r_fds[j][1]);
                    if (j != i) close(r_fds[j][0]);
                }
                receiver((void *)(intptr_t)r_fds[i][0]);
                exit(0);
            }
            close(r_fds[i][0]);
        }
    }

    for (unsigned int i = 0; i < total_children; i++) {
        struct child_data *cd = malloc(sizeof(struct child_data));
        cd->num_writes = total_children;
        cd->write_fds = w_fds;
        cd->read_fd = -1;

        if (use_threads) {
            if (pthread_create(&threads[thread_idx++], NULL, sender, cd) != 0)
                barf("pthread_create sender");
        } else {
            pid_t pid = fork();
            if (pid < 0) barf("fork sender");
            if (pid == 0) {
                for (unsigned int j = 0; j < total_children; j++) {
                    close(r_fds[j][0]);
                }
                sender(cd);
                exit(0);
            }
        }
    }

    if (!use_threads) {
        for (unsigned int i = 0; i < total_children; i++) {
            close(w_fds[i]);
        }
    }

    return thread_idx;
}

int main(int argc, char **argv) {
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-p") == 0 || strcmp(argv[i], "--pipe") == 0) {
            use_pipes = 1;
        } else if (strcmp(argv[i], "-T") == 0 || strcmp(argv[i], "--threads") == 0) {
            use_threads = 1;
        } else if (strcmp(argv[i], "-l") == 0 && i + 1 < argc) {
            loops = atoi(argv[++i]);
        } else if (strcmp(argv[i], "-g") == 0 && i + 1 < argc) {
            num_groups = atoi(argv[++i]);
        } else if (strcmp(argv[i], "-f") == 0 && i + 1 < argc) {
            total_children = atoi(argv[++i]);
        } else if (strcmp(argv[i], "-s") == 0 && i + 1 < argc) {
            datasize = atoi(argv[++i]);
        }
    }

    unsigned int total_tasks = num_groups * total_children * 2;
    printf("Running in %s mode with %u groups using %s (%u tasks total)...\n",
           use_threads ? "threaded" : "process",
           num_groups,
           use_pipes ? "pipes" : "sockets",
           total_tasks);

    pthread_t *threads = NULL;
    if (use_threads) {
        threads = malloc(total_tasks * sizeof(pthread_t));
        if (!threads) barf("malloc threads");
    }

    struct timeval start, stop;
    gettimeofday(&start, NULL);

    unsigned int thread_idx = 0;
    for (unsigned int i = 0; i < num_groups; i++) {
        thread_idx = group(threads, thread_idx);
    }

    if (use_threads) {
        for (unsigned int i = 0; i < total_tasks; i++) {
            pthread_join(threads[i], NULL);
        }
        free(threads);
    } else {
        int status;
        while (wait(&status) > 0 || errno == EINTR);
    }

    gettimeofday(&stop, NULL);

    double diff = (stop.tv_sec - start.tv_sec) + (stop.tv_usec - start.tv_usec) / 1000000.0;
    printf("Time: %.3f\n", diff);

    return 0;
}
