-- payloads/drivers/wrk2/leak_client.lua
-- Emits sustained HTTP traffic to memory-leak endpoint.

function request()
    local headers = {
        ["Content-Type"] = "application/json",
        ["Accept"] = "application/json"
    }
    local body = '{"chunk_size_kb": 16, "tag": "bench_leak_record"}'
    return wrk.format("POST", "/api/v1/leak", headers, body)
end
