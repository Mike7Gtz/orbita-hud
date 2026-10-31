local source = debug.getinfo(1, 'S').source:sub(2)
local root = source:match('^(.*)/conky/layout.lua$')
local function quote(s) return "'" .. s:gsub("'", "'\\''") .. "'" end
return function(kind)
    local values = {root=root}
    local pipe = io.popen('python3 ' .. quote(root .. '/runner.py') .. ' layout ' .. kind .. ' 2>/dev/null')
    if pipe then
        for line in pipe:lines() do
            local k,v = line:match('^([%w_]+)=(.*)$')
            if k then values[k] = tonumber(v) or v end
        end
        pipe:close()
    end
    return values
end
