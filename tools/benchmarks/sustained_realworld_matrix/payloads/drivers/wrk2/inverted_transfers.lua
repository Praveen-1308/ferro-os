-- payloads/drivers/wrk2/inverted_transfers.lua
-- Emits paired inverted transactions (A->B vs B->A) to provoke lock contention / deadlocks.

local counter = 0

function request()
    counter = counter + 1
    local from_id = (counter % 2 == 0) and 101 or 102
    local to_id = (counter % 2 == 0) and 102 or 101
    local body = string.format('{"from_account": %d, "to_account": %d, "amount_cents": 500}', from_id, to_id)
    local headers = {
        ["Content-Type"] = "application/json",
        ["Accept"] = "application/json"
    }
    return wrk.format("POST", "/api/transfer", headers, body)
end
