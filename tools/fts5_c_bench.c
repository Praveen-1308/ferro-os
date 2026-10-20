#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <time.h>
#include <sqlite3.h>

#define NUM_DOCS 10000
#define NUM_QUERIES 800

static const char *words[] = {
    "connection", "timeout", "reconnect", "failed", "success",
    "handshake", "packet", "dropped", "buffer", "overflow"
};
#define NUM_WORDS 10

const char *db_path = "/tmp/c_test_fts.db";

static double get_time_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

void init_db(void) {
    sqlite3 *db;
    remove(db_path);
    char buf[128];
    snprintf(buf, sizeof(buf), "%s-wal", db_path); remove(buf);
    snprintf(buf, sizeof(buf), "%s-shm", db_path); remove(buf);

    if (sqlite3_open(db_path, &db) != SQLITE_OK) {
        fprintf(stderr, "Failed to open db\n");
        exit(1);
    }
    sqlite3_exec(db, "PRAGMA journal_mode = WAL;", NULL, NULL, NULL);
    sqlite3_exec(db, "CREATE VIRTUAL TABLE logs USING fts5(msg);", NULL, NULL, NULL);

    sqlite3_exec(db, "BEGIN TRANSACTION;", NULL, NULL, NULL);
    sqlite3_stmt *stmt;
    sqlite3_prepare_v2(db, "INSERT INTO logs VALUES (?);", -1, &stmt, NULL);
    for (int i = 0; i < NUM_DOCS; i++) {
        char msg[256];
        snprintf(msg, sizeof(msg), "Transaction %d %s %s error failure", i, words[i % NUM_WORDS], words[(i+3) % NUM_WORDS]);
        sqlite3_bind_text(stmt, 1, msg, -1, SQLITE_STATIC);
        sqlite3_step(stmt);
        sqlite3_reset(stmt);
    }
    sqlite3_finalize(stmt);
    sqlite3_exec(db, "COMMIT;", NULL, NULL, NULL);
    sqlite3_close(db);
}

typedef struct {
    int q_count;
} worker_arg_t;

void *worker(void *arg) {
    worker_arg_t *w = (worker_arg_t *)arg;
    sqlite3 *db;
    if (sqlite3_open(db_path, &db) != SQLITE_OK) return NULL;

    sqlite3_stmt *stmt;
    const char *sql = "SELECT rank, msg FROM logs WHERE logs MATCH ? ORDER BY rank LIMIT 10;";
    if (sqlite3_prepare_v2(db, sql, -1, &stmt, NULL) != SQLITE_OK) {
        sqlite3_close(db);
        return NULL;
    }

    for (int i = 0; i < w->q_count; i++) {
        const char *word = words[i % NUM_WORDS];
        sqlite3_bind_text(stmt, 1, word, -1, SQLITE_STATIC);
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            // consume
        }
        sqlite3_reset(stmt);
    }
    sqlite3_finalize(stmt);
    sqlite3_close(db);
    return NULL;
}

int main(int argc, char **argv) {
    init_db();
    printf("SQLite version: %s\n", sqlite3_libversion());

    int thread_counts[] = {1, 2, 4, 8, 16};
    for (int tc = 0; tc < 5; tc++) {
        int nth = thread_counts[tc];
        int q_per = NUM_QUERIES / nth;
        pthread_t th[16];
        worker_arg_t args[16];

        double t0 = get_time_sec();
        for (int i = 0; i < nth; i++) {
            args[i].q_count = q_per;
            pthread_create(&th[i], NULL, worker, &args[i]);
        }
        for (int i = 0; i < nth; i++) {
            pthread_join(th[i], NULL);
        }
        double dt = get_time_sec() - t0;
        printf("C Bench | Threads: %2d | Duration: %.4fs | QPS: %.1f\n", nth, dt, (double)NUM_QUERIES / dt);
    }
    return 0;
}
