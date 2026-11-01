-- Calendar progress and subsecond wall time. No processes are spawned per frame.
local M={}
function M.now(telemetry,uptime)
    local wall=tonumber(telemetry.generated_at)
    local boot=tonumber(telemetry['clock.boottime'])
    if not uptime then
        local file=io.open('/proc/uptime','r')
        if file then uptime=tonumber(file:read('*n'));file:close() end
    end
    if wall and boot and uptime and uptime>=boot-.02 and uptime-boot<6 then
        return wall+uptime-boot
    end
    return os.time()
end

function M.month_days(year,month)
    local days={31,28,31,30,31,30,31,31,30,31,30,31}
    if month==2 and year%4==0 and (year%100~=0 or year%400==0) then return 29 end
    return days[month]
end

function M.progress(stamp)
    local whole=math.floor(stamp)
    local t=os.date('*t',whole)
    local sec=t.sec+stamp-whole
    local minute=t.min+sec/60
    local hour=t.hour+minute/60
    local day=hour/24
    -- Monday first. Calendar months have equal sectors, but each month uses
    -- its actual day count, including leap years, to fill its own sector.
    local week=((t.wday+5)%7+day)/7
    local year=(t.month-1+(t.day-1+day)/M.month_days(t.year,t.month))/12
    return {seconds=sec/60,minutes=minute/60,hours=hour/24,
            week=week,year=year,date=t}
end

function M.segment_fraction(progress,index,count)
    return math.max(0,math.min(1,progress*count-index))
end
return M
