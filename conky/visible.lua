-- SPDX-License-Identifier: GPL-3.0-or-later
-- Measure only the portions of each tick that survive the viewport and foreground masks.
local M={}
local EPS=1e-9

function M.segment(x1,y1,x2,y2,width,height,masks)
    local dx,dy=x2-x1,y2-y1
    local length=math.sqrt(dx*dx+dy*dy)
    if length<EPS then return {} end
    local lo,hi=0,1
    local function edge(p,q)
        if math.abs(p)<EPS then return q>=0 end
        local t=q/p
        if p<0 then lo=math.max(lo,t) else hi=math.min(hi,t) end
        return lo<hi
    end
    if not (edge(-dx,x1) and edge(dx,width-x1) and edge(-dy,y1) and edge(dy,height-y1)) then return {} end
    local intervals={{lo,hi}}
    for _,circle in ipairs(masks or {}) do
        local fx,fy=x1-circle[1],y1-circle[2]
        local a=length*length; local b=2*(fx*dx+fy*dy)
        local c=fx*fx+fy*fy-circle[3]*circle[3]
        local disc=b*b-4*a*c
        if disc>EPS then
            local root=math.sqrt(disc)
            local first,last=(-b-root)/(2*a),(-b+root)/(2*a)
            local next_intervals={}
            for _,part in ipairs(intervals) do
                local left,right=part[1],part[2]
                if last<=left or first>=right then
                    next_intervals[#next_intervals+1]=part
                else
                    if first>left then next_intervals[#next_intervals+1]={left,math.min(first,right)} end
                    if last<right then next_intervals[#next_intervals+1]={math.max(last,left),right} end
                end
            end
            intervals=next_intervals
        end
    end
    local result={}
    for _,part in ipairs(intervals) do
        local a,b=part[1],part[2]
        if b-a>EPS then result[#result+1]={x1=x1+dx*a,y1=y1+dy*a,x2=x1+dx*b,y2=y1+dy*b,length=(b-a)*length} end
    end
    return result
end

function M.track(p)
    local result={segments={},length=0}
    local denominator=math.abs(p.sweep)>=360 and p.count or p.count-1
    for i=0,p.count-1 do
        local angle=(p.start+p.sweep*i/denominator)*math.pi/180
        local c,s=math.cos(angle),math.sin(angle)
        local parts=M.segment(p.x+p.radius*c,p.y+p.radius*s,p.x+(p.radius+p.span)*c,
                              p.y+(p.radius+p.span)*s,p.width,p.height,p.masks)
        for _,segment in ipairs(parts) do
            segment.offset=result.length
            segment.tick=i
            result.length=result.length+segment.length
            result.segments[#result.segments+1]=segment
        end
    end
    return result
end

function M.fill(track,percent)
    local value=tonumber(percent)
    if not value or value~=value then value=0 end
    local budget=track.length*math.max(0,math.min(100,value))/100
    local result={}; local painted=0
    for _,segment in ipairs(track.segments) do
        local used=math.max(0,math.min(segment.length,budget-segment.offset))
        result[#result+1]={segment=segment,filled=used,
                          progress=track.length>EPS and (segment.offset+used)/track.length or 0}
        painted=painted+used
    end
    return result,painted
end

function M.panel_tracks(p)
    local outer=p.gauge_radius+p.gauge_span
    local thermal={p.temperature_x,p.temperature_y,p.temperature_radius+p.temperature_span+p.occlusion_gap}
    local gpu={p.gauge_x,p.gpu_y,outer+p.occlusion_gap}
    local cpu={p.gauge_x,p.cpu_y,outer+p.occlusion_gap}
    local function gauge(y,upper,masks)
        return M.track{x=p.gauge_x,y=y,radius=p.gauge_radius,span=p.gauge_span,
                       start=upper and -90 or 90,sweep=upper and -360 or 360,
                       count=p.gauge_count,width=p.width,height=p.height,masks=masks}
    end
    local result={vram=gauge(p.vram_y,true,{gpu,thermal}),gpu=gauge(p.gpu_y,true,{thermal}),
                  cpu=gauge(p.cpu_y,false,{thermal}),ram=gauge(p.ram_y,false,{cpu,thermal})}
    for _,upper in ipairs({true,false}) do
        result[upper and 'gpu_temperature' or 'cpu_temperature']=M.track{
            x=p.temperature_x,y=p.temperature_y,radius=p.temperature_radius,span=p.temperature_span,
            start=upper and 182 or 178,sweep=upper and 176 or -176,count=72,width=p.width,height=p.height}
    end
    return result
end
return M
