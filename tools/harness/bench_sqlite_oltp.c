#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include "sqlite3.h"

#define NUM_TXNS 2500

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
    const char *mode = (argc > 1) ? argv[1] : "wal";
    const char *db_path = "/tmp/bench_oltp.db";
    unlink(db_path);

    sqlite3 *db;
    if (sqlite3_open(db_path, &db) != SQLITE_OK) {
        fprintf(stderr, "Cannot open database: %s\n", sqlite3_errmsg(db));
        return 1;
    }

    char *errmsg = 0;
    if (strcmp(mode, "wal") == 0) {
        sqlite3_exec(db, "PRAGMA journal_mode = WAL;", 0, 0, &errmsg);
        sqlite3_exec(db, "PRAGMA synchronous = NORMAL;", 0, 0, &errmsg);
    } else {
        sqlite3_exec(db, "PRAGMA journal_mode = DELETE;", 0, 0, &errmsg);
        sqlite3_exec(db, "PRAGMA synchronous = FULL;", 0, 0, &errmsg);
    }

    sqlite3_exec(db, "CREATE TABLE accounts (id INTEGER PRIMARY KEY, balance REAL);", 0, 0, &errmsg);
    sqlite3_exec(db, "CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER, amount REAL, ts REAL);", 0, 0, &errmsg);

    // Seed 1000 accounts
    sqlite3_exec(db, "BEGIN TRANSACTION;", 0, 0, &errmsg);
    sqlite3_stmt *stmt_seed;
    sqlite3_prepare_v2(db, "INSERT INTO accounts (id, balance) VALUES (?, 1000.0);", -1, &stmt_seed, 0);
    for (int i = 1; i <= 1000; i++) {
        sqlite3_bind_int(stmt_seed, 1, i);
        sqlite3_step(stmt_seed);
        sqlite3_reset(stmt_seed);
    }
    sqlite3_finalize(stmt_seed);
    sqlite3_exec(db, "COMMIT;", 0, 0, &errmsg);

    sqlite3_stmt *stmt_update, *stmt_insert;
    sqlite3_prepare_v2(db, "UPDATE accounts SET balance = balance + ? WHERE id = ?;", -1, &stmt_update, 0);
    sqlite3_prepare_v2(db, "INSERT INTO history (account_id, amount, ts) VALUES (?, ?, ?);", -1, &stmt_insert, 0);

    double latencies[NUM_TXNS];
    double total_t0 = get_time_sec();

    for (int i = 0; i < NUM_TXNS; i++) {
        int acct = (i % 1000) + 1;
        double amt = (double)(i % 50 - 25);
        double now = get_time_sec();

        double t0 = get_time_sec();
        sqlite3_exec(db, "BEGIN TRANSACTION;", 0, 0, &errmsg);

        sqlite3_bind_double(stmt_update, 1, amt);
        sqlite3_bind_int(stmt_update, 2, acct);
        sqlite3_step(stmt_update);
        sqlite3_reset(stmt_update);

        sqlite3_bind_int(stmt_insert, 1, acct);
        sqlite3_bind_double(stmt_insert, 2, amt);
        sqlite3_bind_double(stmt_insert, 3, now);
        sqlite3_step(stmt_insert);
        sqlite3_reset(stmt_insert);

        sqlite3_exec(db, "COMMIT;", 0, 0, &errmsg);
        double t1 = get_time_sec();
        latencies[i] = (t1 - t0) * 1000.0; // ms
    }

    double total_t1 = get_time_sec();
    double total_sec = total_t1 - total_t0;
    double tps = NUM_TXNS / total_sec;

    sqlite3_finalize(stmt_update);
    sqlite3_finalize(stmt_insert);
    sqlite3_close(db);
    unlink(db_path);

    qsort(latencies, NUM_TXNS, sizeof(double), compare_double);
    double p50 = latencies[(int)(NUM_TXNS * 0.50)];
    double p95 = latencies[(int)(NUM_TXNS * 0.95)];
    double p99 = latencies[(int)(NUM_TXNS * 0.99)];
    double max_lat = latencies[NUM_TXNS - 1];

    fprintf(stderr, "=== BENCH_SQLITE_OLTP [%s] COMPLETE ===\n", mode);
    fprintf(stderr, "Transactions: %d | Throughput: %.2f TPS\n", NUM_TXNS, tps);
    fprintf(stderr, "Latency - p50: %.3f ms | p95: %.3f ms | p99: %.3f ms | max: %.3f ms\n", p50, p95, p99, max_lat);

    printf("{\"metric\": \"tps\", \"tps\": %.2f, \"p50_ms\": %.3f, \"p95_ms\": %.3f, \"p99_ms\": %.3f, \"max_ms\": %.3f, \"mode\": \"%s\"}\n",
           tps, p50, p95, p99, max_lat, mode);

    return 0;
}
