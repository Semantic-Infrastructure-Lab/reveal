-- Smoke-tier fixture (BACK-431 Issue G) — Lua.
local function validate(order)
    if order == nil then
        error("empty order")
    end
    return order
end

local function processOrder(order)
    local ok, result = pcall(validate, order)
    if not ok then
        return nil
    end
    local count = 0
    while count < 3 do
        count = count + 1
    end
    return string.upper(result)
end

local function run(order)
    return processOrder(order)
end
