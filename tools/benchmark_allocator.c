#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <time.h>
#include <stdint.h>
#include <unistd.h>

#define NUM_THREADS 8
#define ALLOCS_PER_THREAD 200000
#define BATCH_SIZE 64

static const size_t SIZES[] = {16, 32, 64, 128, 256, 512, 1024, 2048, 4096};
static const size_t NUM_SIZES = sizeof(SIZES) / sizeof(SIZES[0]);

typedef struct {
    int thread_id;
    double elapsed_sec;
    uint64_t ops_completed;
} ThreadData;

void* worker_thread(void* arg) {
    ThreadData* data = (ThreadData*)arg;
    struct timespec start, end;
    void* pointers[BATCH_SIZE];
    uint32_t seed = (uint32_t)(data->thread_id * 10007 + 42);

    clock_gettime(CLOCK_MONOTONIC, &start);

    uint64_t ops = 0;
    for (int i = 0; i < ALLOCS_PER_THREAD / BATCH_SIZE; i++) {
        // Allocate batch
        for (int b = 0; b < BATCH_SIZE; b++) {
            seed = seed * 1664525u + 1013904223u;
            size_t sz = SIZES[seed % NUM_SIZES];
            pointers[b] = malloc(sz);
            if (pointers[b]) {
                // Touch memory to ensure actual page mapping
                *((volatile char*)pointers[b]) = 1;
            }
        }
        // Free batch
        for (int b = 0; b < BATCH_SIZE; b++) {
            if (pointers[b]) {
                free(pointers[b]);
            }
        }
        ops += BATCH_SIZE;
    }

    clock_gettime(CLOCK_MONOTONIC, &end);

    data->elapsed_sec = (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;
    data->ops_completed = ops;
    return NULL;
}

int main(int argc, char** argv) {
    pthread_t threads[NUM_THREADS];
    ThreadData tdata[NUM_THREADS];

    const char* label = (argc > 1) ? argv[1] : "Standard Allocator";
    printf("======================================================================\n");
    printf("      MULTI-THREADED MEMORY ALLOCATOR BENCHMARK (%s)\n", label);
    printf("======================================================================\n");
    printf("Threads:               %d\n", NUM_THREADS);
    printf("Allocations per Thread: %d\n", ALLOCS_PER_THREAD);
    printf("Total Allocations:     %d (sizes 16B - 4096B)\n", NUM_THREADS * ALLOCS_PER_THREAD);
    printf("Executing concurrent allocations...\n");

    struct timespec global_start, global_end;
    clock_gettime(CLOCK_MONOTONIC, &global_start);

    for (int t = 0; t < NUM_THREADS; t++) {
        tdata[t].thread_id = t;
        tdata[t].elapsed_sec = 0;
        tdata[t].ops_completed = 0;
        pthread_create(&threads[t], NULL, worker_thread, &tdata[t]);
    }

    uint64_t total_ops = 0;
    for (int t = 0; t < NUM_THREADS; t++) {
        pthread_join(threads[t], NULL);
        total_ops += tdata[t].ops_completed;
    }

    clock_gettime(CLOCK_MONOTONIC, &global_end);
    double total_time = (global_end.tv_sec - global_start.tv_sec) + 
                        (global_end.tv_nsec - global_start.tv_nsec) / 1e9;
    double throughput = (double)total_ops / total_time;
    double avg_latency_ns = (total_time / total_ops) * 1e9;

    printf("\n--- Results: %s ---\n", label);
    printf("Total Completed Ops:   %lu\n", (unsigned long)total_ops);
    printf("Total Elapsed Time:    %.4f seconds\n", total_time);
    printf("Allocation Throughput: %.2f ops/sec\n", throughput);
    printf("Avg Op Latency:        %.2f ns\n", avg_latency_ns);
    printf("======================================================================\n");

    return 0;
}
