// SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause)
/*
 * ferro_sockops.c - FerroOS eBPF Network Stack Bypass for Localhost Sockets
 * Intercepts loopback TCP socket traffic and redirects payload directly between
 * socket queues via BPF SOCKHASH, completely bypassing IP routing, netfilter,
 * TCP header construction, and softirq loopback overhead.
 */

#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

struct sock_key {
    __u32 sip;
    __u32 dip;
    __u32 sport;
    __u32 dport;
};

struct {
    __uint(type, BPF_MAP_TYPE_SOCKHASH);
    __uint(max_entries, 65536);
    __type(key, struct sock_key);
    __type(value, __u64);
} ferro_sock_hash SEC(".maps");

static inline void extract_key_from_skops(struct bpf_sock_ops *skops, struct sock_key *key) {
    key->sip = skops->local_ip4;
    key->dip = skops->remote_ip4;
    key->sport = bpf_htonl(skops->local_port);
    key->dport = skops->remote_port;
}

static inline void extract_key_from_msg(struct sk_msg_md *msg, struct sock_key *key) {
    key->sip = msg->remote_ip4;
    key->dip = msg->local_ip4;
    key->sport = bpf_htonl(msg->remote_port);
    key->dport = msg->local_port;
}

SEC("sockops")
int ferro_bpf_sockops(struct bpf_sock_ops *skops) {
    __u32 op = skops->op;

    if (op == BPF_SOCK_OPS_ACTIVE_ESTABLISHED_CB || op == BPF_SOCK_OPS_PASSIVE_ESTABLISHED_CB) {
        // Only accelerate IPv4 localhost connections (127.0.0.0/8)
        if (skops->family == 2 /* AF_INET */) {
            __u32 local_ip = bpf_ntohl(skops->local_ip4);
            __u32 remote_ip = bpf_ntohl(skops->remote_ip4);

            if ((local_ip >> 24) == 127 && (remote_ip >> 24) == 127) {
                struct sock_key key = {};
                extract_key_from_skops(skops, &key);
                bpf_sock_hash_update(skops, &ferro_sock_hash, &key, BPF_NOEXIST);
            }
        }
    }
    return 0;
}

SEC("sk_msg")
int ferro_bpf_skmsg(struct sk_msg_md *msg) {
    if (msg->family == 2 /* AF_INET */) {
        struct sock_key key = {};
        extract_key_from_msg(msg, &key);
        // Direct socket bypass: bypasses TCP/IP stack and redirects directly to target socket
        return bpf_msg_redirect_hash(msg, &ferro_sock_hash, &key, BPF_F_INGRESS);
    }
    return SK_PASS;
}

char _license[] SEC("license") = "Dual BSD/GPL";
