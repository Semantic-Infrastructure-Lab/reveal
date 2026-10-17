-- Hand-written Lua conformance fixture (BACK-1162).
local unused = require("unused_fixture")

local function validate(order)
    if order == nil then
        return nil
    end
    return order
end

local function processOrder(order)
    local result = validate(order)
    if result == nil then
        return nil
    end
    local handle = io.open("orders.log", "a")
    io.write(result)
    result = result * 2
    return result
end

local function run(order)
    return processOrder(order)
end

local Batch = {}
function Batch.run(items)
    for _, item in ipairs(items) do
        Batch.total = Batch.total + item
        cache.set(item)
    end
end

-- Lua has no native decorator, class inheritance, or try/catch syntax.
-- Table/metatable conventions and pcall/xpcall are outside those syntax probes.
