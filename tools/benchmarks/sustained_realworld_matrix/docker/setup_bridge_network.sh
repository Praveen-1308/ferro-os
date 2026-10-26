#!/usr/bin/env bash
# ==============================================================================
# setup_bridge_network.sh
# Manages the isolated Docker bridge network 'realworld_matrix_net' (172.30.0.0/16)
# for the Sustained Real-World Benchmark Matrix 3-container topology.
# ==============================================================================
set -euo pipefail

NETWORK_NAME="realworld_matrix_net"
SUBNET="172.30.0.0/16"
GATEWAY="172.30.0.1"
BRIDGE_IFNAME="br-matrix"

log_info() {
    echo "[INFO] [$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*"
}

log_warn() {
    echo "[WARN] [$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*" >&2
}

log_error() {
    echo "[ERROR] [$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*" >&2
}

is_network_present() {
    docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1
}

get_network_subnet() {
    docker network inspect "${NETWORK_NAME}" --format '{{(index .IPAM.Config 0).Subnet}}' 2>/dev/null || echo ""
}

setup_network() {
    if is_network_present; then
        local current_subnet
        current_subnet="$(get_network_subnet)"
        if [[ "${current_subnet}" == "${SUBNET}" ]]; then
            log_info "Network '${NETWORK_NAME}' already exists with correct subnet (${SUBNET}). Ready."
            return 0
        else
            log_warn "Network '${NETWORK_NAME}' exists with wrong subnet (${current_subnet}). Recreating..."
            teardown_network
        fi
    fi

    log_info "Creating Docker bridge network '${NETWORK_NAME}' (${SUBNET}, gw=${GATEWAY})..."
    docker network create \
        --driver bridge \
        --subnet "${SUBNET}" \
        --gateway "${GATEWAY}" \
        --opt "com.docker.network.bridge.name"="${BRIDGE_IFNAME}" \
        --label "project=sustained_realworld_matrix" \
        "${NETWORK_NAME}" >/dev/null

    log_info "Network '${NETWORK_NAME}' created successfully."
}

teardown_network() {
    if is_network_present; then
        log_info "Disconnecting active containers from '${NETWORK_NAME}'..."
        local connected_containers
        connected_containers=$(docker network inspect "${NETWORK_NAME}" --format '{{range $k, $v := .Containers}}{{$k}} {{end}}' 2>/dev/null || true)
        for cid in ${connected_containers}; do
            log_info "Disconnecting container ${cid}..."
            docker network disconnect -f "${NETWORK_NAME}" "${cid}" 2>/dev/null || true
        done

        log_info "Removing Docker network '${NETWORK_NAME}'..."
        docker network rm "${NETWORK_NAME}" >/dev/null 2>&1 || true
        log_info "Network '${NETWORK_NAME}' removed."
    else
        log_info "Network '${NETWORK_NAME}' does not exist. Nothing to teardown."
    fi
}

status_network() {
    if is_network_present; then
        echo "=== Docker Network Status: ${NETWORK_NAME} ==="
        docker network inspect "${NETWORK_NAME}" --format '
Name:       {{.Name}}
Id:         {{.Id}}
Driver:     {{.Driver}}
Subnet:     {{(index .IPAM.Config 0).Subnet}}
Gateway:    {{(index .IPAM.Config 0).Gateway}}
Containers: {{len .Containers}}
'
        docker network inspect "${NETWORK_NAME}" --format '{{range $k, $v := .Containers}}  - {{$v.Name}} (IPv4: {{$v.IPv4Address}})
{{end}}'
    else
        echo "Network '${NETWORK_NAME}' is NOT present."
        return 1
    fi
}

case "${1:-setup}" in
    setup|--setup|-s)
        setup_network
        ;;
    teardown|--teardown|-t|down)
        teardown_network
        ;;
    status|--status)
        status_network
        ;;
    reset|--reset)
        teardown_network
        setup_network
        ;;
    *)
        echo "Usage: $0 [setup|teardown|status|reset]"
        exit 1
        ;;
esac
