#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <time.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>

#define NUM_PRODUCERS 4
#define NUM_CONSUMERS 4
#define QUEUE_CAPACITY 8192
#define OPS_PER_PRODUCER 250000

typedef struct {
    void* items[QUEUE_CAPACITY];
    size_t head;
    size_t tail;
    pthread_mutex_t lock;
    pthread_cond_t not_empty;
    pthread_cond_t not_full;
    bool finished;
} BoundedQueue;

BoundedQueue g_queues[NUM_PRODUCERS];

void queue_init(BoundedQueue* q) {
    q->head = 0;
    q->tail = 0;
    q->finished = false;
    pthread_mutex_init(&q->lock, NULL);
    pthread_cond_init(&q->not_empty, NULL);
    pthread_cond_init(&q->not_full, NULL);
}

void queue_push(BoundedQueue* q, void* ptr) {
    pthread_mutex_lock(&q->lock);
    while ((q->head - q->tail) == QUEUE_CAPACITY) {
        pthread_cond_wait(&q->not_full, &q->lock);
    }
    q->items[q->head % QUEUE_CAPACITY] = ptr;
    q->head++;
    pthread_cond_signal(&q->not_empty);
    pthread_mutex_unlock(&q->lock);
}

void* queue_pop(BoundedQueue* q) {
    pthread_mutex_lock(&q->lock);
    while (q->head == q->tail && !q->finished) {
        pthread_cond_wait(&q->not_empty, &q->lock);
    }
    if (q->head == q->tail && q->finished) {
        pthread_mutex_unlock(&q->lock);
        return NULL;
    }
    void* ptr = q->items[q->tail % QUEUE_CAPACITY];
    q->tail++;
    pthread_cond_signal(&q->not_full);
    pthread_mutex_unlock(&q->lock);
    return ptr;
}

void* producer_thread(void* arg) {
    int id = (int)(intptr_t)arg;
    BoundedQueue* q = &g_queues[id];
    size_t sizes[] = {32, 64, 128, 256, 512, 1024, 2048};
    size_t num_sizes = sizeof(sizes) / sizeof(sizes[0]);
    uint32_t seed = (uint32_t)(id * 1337 + 42);

    for (int i = 0; i < OPS_PER_PRODUCER; i++) {
        seed = seed * 1664525u + 1013904223u;
        size_t sz = sizes[seed % num_sizes];
        void* ptr = malloc(sz);
        if (ptr) {
            *((volatile char*)ptr) = 1; // page touch
            queue_push(q, ptr);
        }
    }

    pthread_mutex_lock(&q->lock);
    q->finished = true;
    pthread_cond_broadcast(&q->not_empty);
    pthread_mutex_unlock(&q->lock);

    return NULL;
}

void* consumer_thread(void* arg) {
    int id = (int)(intptr_t)arg;
    // Each consumer drains its corresponding producer queue to ensure cross-thread remote free
    BoundedQueue* q = &g_queues[id];

    while (1) {
        void* ptr = queue_pop(q);
        if (!ptr) break;
        free(ptr); // Remote free: thread B frees memory allocated by thread A!
    }

    return NULL;
}

int main(int argc, char** argv) {
    const char* label = (argc > 1) ? argv[1] : "Cross-Thread Allocator Test";
    printf("======================================================================\n");
    printf("  CROSS-THREAD ALLOCATION & REMOTE-FREE STRESS TEST (%s)\n", label);
    printf("======================================================================\n");
    printf("Producers: %d (allocate memory)\n", NUM_PRODUCERS);
    printf("Consumers: %d (free memory allocated by producers)\n", NUM_CONSUMERS);
    printf("Total Remote-Free Operations: %d\n", NUM_PRODUCERS * OPS_PER_PRODUCER);
    printf("Executing cross-thread memory migration...\n");

    for (int i = 0; i < NUM_PRODUCERS; i++) {
        queue_init(&g_queues[i]);
    }

    pthread_t producers[NUM_PRODUCERS];
    pthread_t consumers[NUM_CONSUMERS];

    struct timespec start, end;
    clock_gettime(CLOCK_MONOTONIC, &start);

    for (intptr_t i = 0; i < NUM_CONSUMERS; i++) {
        pthread_create(&consumers[i], NULL, consumer_thread, (void*)i);
    }
    for (intptr_t i = 0; i < NUM_PRODUCERS; i++) {
        pthread_create(&producers[i], NULL, producer_thread, (void*)i);
    }

    for (int i = 0; i < NUM_PRODUCERS; i++) {
        pthread_join(producers[i], NULL);
    }
    for (int i = 0; i < NUM_CONSUMERS; i++) {
        pthread_join(consumers[i], NULL);
    }

    clock_gettime(CLOCK_MONOTONIC, &end);
    double elapsed = (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;
    uint64_t total_ops = NUM_PRODUCERS * OPS_PER_PRODUCER;
    double throughput = (double)total_ops / elapsed;
    double avg_lat_ns = (elapsed / total_ops) * 1e9;

    printf("\n--- Results: %s ---\n", label);
    printf("Total Remote Alloc/Frees: %lu\n", (unsigned long)total_ops);
    printf("Total Elapsed Time:       %.4f seconds\n", elapsed);
    printf("Remote Free Throughput:   %.2f ops/sec\n", throughput);
    printf("Average Latency:          %.2f ns\n", avg_lat_ns);
    printf("======================================================================\n");

    return 0;
}
