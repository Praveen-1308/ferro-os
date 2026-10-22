#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <time.h>
#include <sys/types.h>
#include <sys/stat.h>

#define CHUNK_SIZE (1024 * 1024) // 1 MB
#define NUM_CHUNKS 64            // 64 MB total

static double get_time_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

static int compare_double(const void *a, const void *b) {
    double da = *(const double *)a;
    double db = *(const double *)b;
    return (da > db) - (da < db);
}

int main(int argc, char **argv) {
    const char *filepath = "/tmp/bench_fsync.tmp";
    if (argc > 1) {
        filepath = argv[1];
    }

    char *buf = malloc(CHUNK_SIZE);
    if (!buf) {
        perror("malloc");
        return 1;
    }
    memset(buf, 0xAA, CHUNK_SIZE);

    int fd = open(filepath, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) {
        perror("open");
        free(buf);
        return 1;
    }

    double latencies[NUM_CHUNKS];
    double total_t0 = get_time_sec();

    for (int i = 0; i < NUM_CHUNKS; i++) {
        double t0 = get_time_sec();
        ssize_t written = write(fd, buf, CHUNK_SIZE);
        double t1 = get_time_sec();
        if (written != CHUNK_SIZE) {
            perror("write");
            close(fd);
            free(buf);
            return 1;
        }
        latencies[i] = (t1 - t0) * 1000.0; // ms
    }

    double fsync_t0 = get_time_sec();
    if (fsync(fd) != 0) {
        perror("fsync");
    }
    double fsync_t1 = get_time_sec();
    double fsync_ms = (fsync_t1 - fsync_t0) * 1000.0;

    double total_t1 = get_time_sec();
    double total_sec = total_t1 - total_t0;
    double throughput_mb = (NUM_CHUNKS * 1.0) / total_sec;

    close(fd);
    unlink(filepath);
    free(buf);

    qsort(latencies, NUM_CHUNKS, sizeof(double), compare_double);
    double p50 = latencies[(int)(NUM_CHUNKS * 0.50)];
    double p95 = latencies[(int)(NUM_CHUNKS * 0.95)];
    double p99 = latencies[(int)(NUM_CHUNKS * 0.99)];
    double max_lat = latencies[NUM_CHUNKS - 1];

    fprintf(stderr, "=== BENCH_FSYNC COMPLETE ===\n");
    fprintf(stderr, "Volume: %d MB | Throughput: %.2f MB/s\n", NUM_CHUNKS, throughput_mb);
    fprintf(stderr, "p50: %.3f ms | p95: %.3f ms | p99: %.3f ms | max: %.3f ms\n", p50, p95, p99, max_lat);
    fprintf(stderr, "fsync_stall: %.3f ms\n", fsync_ms);

    // JSON Output on stdout
    printf("{\"metric\": \"throughput_mb\", \"throughput_mb\": %.2f, \"p50_ms\": %.3f, \"p95_ms\": %.3f, \"p99_ms\": %.3f, \"max_ms\": %.3f, \"fsync_stall_ms\": %.3f}\n",
           throughput_mb, p50, p95, p99, max_lat, fsync_ms);

    return 0;
}
