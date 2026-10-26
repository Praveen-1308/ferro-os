-- payloads/drivers/wrk2/jwt_auth.lua
-- Injects RFC 7519 HMAC-SHA256 JWT tokens into Authorization: Bearer headers.

local token_pool = {
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzEiLCJzY29wZSI6InJlYWQ6Y2F0YWxvZyB3cml0ZTpvcmRlcnMiLCJpYXQiOjE3OTgyNDMyMDAsImV4cCI6MjAwMDAwMDAwMCwiaXNzIjoiZmVycm8tbWF0cml4LWF1dGgifQ.uA6rU1zNnZpS5d_U5F1vK_O9G_fV0E1W_B1Z_A1Y_Z0",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzQyIiwic2NvcGUiOiJyZWFkOmNhdGFsb2ciLCJpYXQiOjE3OTgyNDMyMDAsImV4cCI6MjAwMDAwMDAwMCwiaXNzIjoiZmVycm8tbWF0cml4LWF1dGgifQ.aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV2wX3yZ4aB5c",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzk5Iiwic2NvcGUiOiJyZWFkOmNhdGFsb2cgd3JpdGU6b3JkZXJzIGFkbWluIiwiaWF0IjoxNzk4MjQzMjAwLCJleHAiOjIwMDAwMDAwMDAsImlzcyI6ImZlcnJvLW1hdHJpeC1hdXRoIn0.pQ8rS7tU6vW5xY4zA3bC2dE1fG0hI9jK8lM7nO6pQ5r"
}

function request()
    local idx = math.random(1, #token_pool)
    local token = token_pool[idx]
    local headers = {
        ["Authorization"] = "Bearer " .. token,
        ["Accept"] = "application/json"
    }
    return wrk.format("GET", "/api/protected/profile", headers)
end
