-- payloads/drivers/wrk2/web_feed.lua
-- High-throughput wrk2 driver for REST & web endpoints.
-- Samples dynamic product IDs using Zipfian power-law distribution.

local counter = 0
local threads = {}

function setup(thread)
    thread:set("id", counter)
    table.insert(threads, thread)
    counter = counter + 1
end

function init(args)
    math.randomseed(os.time() + id * 1000)
end

function request()
    -- Zipfian-like distribution over 10,000 products: (random^2) skew
    local r = math.random()
    local product_id = math.floor(1 + (r * r) * 9999)
    local path = "/api/v1/products/" .. product_id
    return wrk.format("GET", path, {["Accept"] = "application/json"})
end
