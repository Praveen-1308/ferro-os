#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <time.h>
#include <sys/types.h>
#include <sys/stat.h>

#define NUM_FILES 2000

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
    const char *base_dir = "/tmp/bench_maildir";
    char dir_tmp[512], dir_cur[512];
    snprintf(dir_tmp, sizeof(dir_tmp), "%s/tmp", base_dir);
    snprintf(dir_cur, sizeof(dir_cur), "%s/cur", base_dir);

    mkdir(base_dir, 0755);
    mkdir(dir_tmp, 0755);
    mkdir(dir_cur, 0755);

    double latencies[NUM_FILES];
    char path_tmp[512], path_cur[512];
    char payload[] = "From: user@ferro-os.dev\nSubject: Benchmark Inode Churn\n\nBody content.\n";
    size_t payload_len = strlen(payload);

    double total_t0 = get_time_sec();

    // 1. Create and write files in tmp/
    for (int i = 0; i < NUM_FILES; i++) {
        snprintf(path_tmp, sizeof(path_tmp), "%s/msg_%d.eml", dir_tmp, i);
        double t0 = get_time_sec();
        int fd = open(path_tmp, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd >= 0) {
            write(fd, payload, payload_len);
            close(fd);
        }
        double t1 = get_time_sec();
        latencies[i] = (t1 - t0) * 1000.0; // ms
    }

    // 2. Atomic rename from tmp/ to cur/
    for (int i = 0; i < NUM_FILES; i++) {
        snprintf(path_tmp, sizeof(path_tmp), "%s/msg_%d.eml", dir_tmp, i);
        snprintf(path_cur, sizeof(path_cur), "%s/msg_%d.eml", dir_cur, i);
        rename(path_tmp, path_cur);
    }

    // 3. Unlink all files
    for (int i = 0; i < NUM_FILES; i++) {
        snprintf(path_cur, sizeof(path_cur), "%s/msg_%d.eml", dir_cur, i);
        unlink(path_cur);
    }

    double total_t1 = get_time_sec();
    double total_sec = total_t1 - total_t0;
    // Total ops = 2000 creates + 2000 renames + 2000 unlinks = 6000 VFS operations
    double total_ops = NUM_FILES * 3.0;
    double ops_sec = total_ops / total_sec;

    rmdir(dir_tmp);
    rmdir(dir_cur);
    rmdir(base_dir);

    qsort(latencies, NUM_FILES, sizeof(double), compare_double);
    double p50 = latencies[(int)(NUM_FILES * 0.50)];
    double p95 = latencies[(int)(NUM_FILES * 0.95)];
    double p99 = latencies[(int)(NUM_FILES * 0.99)];
    double max_lat = latencies[NUM_FILES - 1];

    fprintf(stderr, "=== BENCH_MAILDIR COMPLETE ===\n");
    fprintf(stderr, "Files: %d (6000 total VFS ops) | Throughput: %.2f ops/sec\n", NUM_FILES, ops_sec);
    fprintf(stderr, "Create Latency - p50: %.3f ms | p95: %.3f ms | p99: %.3f ms | max: %.3f ms\n", p50, p95, p99, max_lat);

    // JSON Output on stdout
    printf("{\"metric\": \"tps\", \"tps\": %.2f, \"p50_ms\": %.3f, \"p95_ms\": %.3f, \"p99_ms\": %.3f, \"max_ms\": %.3f}\n",
           ops_sec, p50, p95, p99, max_lat);

    return 0;
}
