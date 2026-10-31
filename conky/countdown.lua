local M={}
function M.format(reset,now)
    local value=tonumber(reset)
    if not value or value~=value or value==math.huge or value==-math.huge then return nil,'unavailable' end
    local seconds=math.ceil(value-now)
    if seconds<=0 then return nil,'expired' end
    if seconds>=86400 then return string.format('%d d %d h',math.floor(seconds/86400),math.floor(seconds%86400/3600)) end
    if seconds>=3600 then return string.format('%d h %02d min',math.floor(seconds/3600),math.floor(seconds%3600/60)) end
    if seconds>=60 then return string.format('%d min',math.floor(seconds/60)) end
    return string.format('%d s',seconds)
end
return M
