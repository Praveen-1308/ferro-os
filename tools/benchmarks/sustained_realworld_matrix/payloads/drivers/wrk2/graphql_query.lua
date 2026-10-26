-- payloads/drivers/wrk2/graphql_query.lua
-- Emits nested GraphQL AST query resolving User -> Orders -> Items -> Product -> Reviews.

local query_body = '{"query": "query GetCatalog { user(id: 42) { id username orders { id total_cents items { quantity product { id title price_cents reviews { rating comment } } } } } }"}'

function request()
    local headers = {
        ["Content-Type"] = "application/json",
        ["Accept"] = "application/json"
    }
    return wrk.format("POST", "/graphql", headers, query_body)
end
