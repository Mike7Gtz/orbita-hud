-- SPDX-License-Identifier: GPL-3.0-or-later
-- Original Órbita HUD renderer · Onocru
require 'cairo'
pcall(require, 'cairo_xlib')
local source = debug.getinfo(1,'S').source:sub(2)
local ROOT = source:match('^(.*)/conky/render.lua$')
local function quote(s) return "'" .. s:gsub("'", "'\\''") .. "'" end
local pipe = io.popen('python3 '..quote(ROOT..'/runner.py')..' runtime 2>/dev/null')
local RUNTIME = pipe and pipe:read('*l') or ''
if pipe then pipe:close() end
local PI = math.pi
local cyan={0.03,0.83,1}; local blue={0.19,0.43,1}
local white={0.94,0.97,1}; local muted={0.38,0.57,0.72}
local panel={}
local panel_file=assert(io.open(ROOT..'/conky/panel.layout','r'))
for row in panel_file:lines() do
    local k,v=row:match('^([%w_]+)=(.*)$')
    if k then panel[k]=assert(tonumber(v)) end
end
panel_file:close()
local function rgba(cr,c,a) cairo_set_source_rgba(cr,c[1],c[2],c[3],a or 1) end
local function line(cr,x1,y1,x2,y2,width,c,a)
    rgba(cr,c,a); cairo_set_line_width(cr,width)
    cairo_move_to(cr,x1,y1); cairo_line_to(cr,x2,y2); cairo_stroke(cr)
end
local function polar(x,y,r,a) return x+r*math.cos(a), y+r*math.sin(a) end
local function arc(cr,x,y,r,start,finish,width,c,alpha)
    rgba(cr,c,alpha); cairo_set_line_width(cr,width)
    cairo_new_sub_path(cr); cairo_arc(cr,x,y,r,start,finish); cairo_stroke(cr)
end
local function label(cr,text,x,y,size,c,weight,align)
    cairo_select_font_face(cr,'DejaVu Sans',CAIRO_FONT_SLANT_NORMAL,weight or CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr,size)
    local e=cairo_text_extents_t:create(); cairo_text_extents(cr,tostring(text),e)
    if align=='center' then x=x-e.width/2-e.x_bearing elseif align=='right' then x=x-e.width-e.x_bearing end
    rgba(cr,c or white); cairo_move_to(cr,x,y); cairo_show_text(cr,tostring(text))
end
local function read(name,ttl)
    local data={}; local f=io.open(RUNTIME..'/'..name..'.state','r')
    if f then
        for row in f:lines() do
            local k,v=row:match('^([%w_.]+)=(.*)$'); if k then data[k]=v end
        end
        f:close()
    end
    if not tonumber(data.generated_at) or os.time()-tonumber(data.generated_at)>ttl then return {} end
    return data
end
local function number(data,key)
    local value=tonumber(data[key]); if value and value==value and math.abs(value)<1e10 then return value end
end
local function percentage(value) return value and string.format('%.0f%%',value) or '--' end
local function temperature(value) return value and string.format('%.0f°C',value) or '--' end
local function hue(t)
    -- cyan -> blue -> magenta -> blue -> cyan, fixed palette; heights are live FFT.
    local stops={{0,0.82,1},{0.24,0.37,1},{0.85,0.12,0.98},{0.24,0.37,1},{0,0.82,1}}
    local v=(t%1)*4; local i=math.floor(v)+1; local k=v-math.floor(v)
    local a,b=stops[i],stops[i+1]
    return {a[1]+(b[1]-a[1])*k,a[2]+(b[2]-a[2])*k,a[3]+(b[3]-a[3])*k}
end
local function ticks(cr,x,y,r,a0,sweep,count,value,c,width,span,gradient)
    local filled=value and math.floor(math.max(0,math.min(100,value))/100*count+.5) or 0
    for i=0,count-1 do
        local angle=(a0+sweep*i/(count-1))*PI/180
        local x1,y1=polar(x,y,r,angle); local x2,y2=polar(x,y,r+span,angle)
        local color=c
        if gradient then color=hue((i/(count-1))*.55) end
        line(cr,x1,y1,x2,y2,width,i<filled and color or muted,i<filled and 1 or .30)
    end
end

function orbita_draw_clock(cr,width,height,telemetry,usage,audio,stamp)
    cairo_save(cr); local scale=math.min(width,height)/800
    cairo_translate(cr,(width-800*scale)/2,(height-800*scale)/2); cairo_scale(cr,scale,scale)
    local bands={}
    if audio.available=='1' then
        for v in (audio.bands or ''):gmatch('[^,]+') do bands[#bands+1]=math.max(0,math.min(1,tonumber(v) or 0)) end
    end
    local n=math.max(64,#bands)
    for i=0,n-1 do
        local a=-PI/2+i/n*PI*2; local energy=bands[i+1] or 0
        local r=336; local h=5+energy*54; local c=hue(i/n)
        local x1,y1=polar(400,400,r,a); local x2,y2=polar(400,400,r+h,a)
        if energy>.04 then line(cr,x1,y1,x2,y2,11,c,.09); line(cr,x1,y1,x2,y2,7,c,.18) end
        line(cr,x1,y1,x2,y2,4,c,energy>.02 and .95 or .25)
    end
    ticks(cr,400,400,306,-90,360,180,nil,cyan,2,7)
    ticks(cr,400,400,282,-90,360,120,nil,blue,2,5)
    local t=os.date('*t',stamp or os.time())
    local fractions={(t.hour%24+t.min/60)/24,(t.min+t.sec/60)/60,t.sec/60}
    for i,r in ipairs({254,236,218}) do
        arc(cr,400,400,r,-PI/2,PI*1.5, i==1 and 7 or 2,muted,.3)
        arc(cr,400,400,r,-PI/2,-PI/2+2*PI*fractions[i], i==1 and 7 or 3,i==2 and blue or cyan,1)
    end
    local days={'DOM','LUN','MAR','MIÉ','JUE','VIE','SÁB'}
    local months={'ENE','FEB','MAR','ABR','MAY','JUN','JUL','AGO','SEP','OCT','NOV','DIC'}
    label(cr,string.format('%02d',t.hour),325,369,122,white,CAIRO_FONT_WEIGHT_BOLD,'center')
    label(cr,string.format('%s · %02d %s · %04d',days[t.wday],t.day,months[t.month],t.year),400,414,20,muted,nil,'center')
    label(cr,string.format('%02d',t.min),470,540,122,white,CAIRO_FONT_WEIGHT_BOLD,'center')
    label(cr,string.format('%02d',t.sec),400,596,16,cyan,nil,'center')
    cairo_restore(cr)
end

-- Cut each foreground disk separately: intersecting holes must stay transparent,
-- rather than reappearing through the XOR of one combined even/odd path.
function orbita_clear_panel_surface(cr)
    cairo_save(cr)
    cairo_set_operator(cr,CAIRO_OPERATOR_CLEAR)
    cairo_paint(cr)
    cairo_restore(cr)
end

function orbita_clip_background(cr,width,height,circles,paint)
    cairo_save(cr)
    for _,circle in ipairs(circles) do
        cairo_new_path(cr)
        cairo_rectangle(cr,0,0,width,height)
        cairo_new_sub_path(cr)
        cairo_arc(cr,circle[1],circle[2],circle[3],0,2*PI)
        cairo_set_fill_rule(cr,CAIRO_FILL_RULE_EVEN_ODD)
        cairo_clip(cr)
    end
    cairo_new_path(cr)
    paint()
    cairo_restore(cr)
end

function orbita_draw_panel(cr,width,height,telemetry,usage,audio,stamp,side)
    local p=panel
    cairo_save(cr); local scale=math.min(width/p.width,height/p.height)
    cairo_translate(cr,(width-p.width*scale)/2,0); cairo_scale(cr,scale,scale)
    local left=(side or telemetry.side)=='left'
    local function X(x) return left and p.width-x or x end
    local function text(s,x,y,size,c,weight,max_width)
        if max_width then
            cairo_select_font_face(cr,'DejaVu Sans',CAIRO_FONT_SLANT_NORMAL,weight or CAIRO_FONT_WEIGHT_NORMAL)
            cairo_set_font_size(cr,size)
            local e=cairo_text_extents_t:create(); cairo_text_extents(cr,tostring(s),e)
            if e.width>max_width then size=size*max_width/e.width end
        end
        label(cr,s,X(x),y,size,c,weight,'center')
    end
    local function shapes(fn)
        cairo_save(cr); if left then cairo_translate(cr,p.width,0); cairo_scale(cr,-1,1) end
        fn(); cairo_restore(cr)
    end
    local now=stamp or os.time()
    local function quota_line(caption,value,y,size,color)
        local value=percentage(value)
        cairo_select_font_face(cr,'DejaVu Sans',CAIRO_FONT_SLANT_NORMAL,CAIRO_FONT_WEIGHT_BOLD)
        cairo_set_font_size(cr,size)
        local a=cairo_text_extents_t:create(); local b=cairo_text_extents_t:create()
        cairo_text_extents(cr,caption,a); cairo_text_extents(cr,value,b)
        local gap=9; local total=a.width+gap+b.width
        local start=X(p.quota_text_x)-total/2
        label(cr,caption,start+a.width/2,y,size,color,CAIRO_FONT_WEIGHT_BOLD,'center')
        label(cr,value,start+a.width+gap+b.width/2,y,size,white,CAIRO_FONT_WEIGHT_BOLD,'center')
    end
    local function quota(name,title,y,lower)
        local observed=number(usage,name..'.observed_at') or 0
        local stale=usage[name..'.stale']~='0' or now-observed>(number(usage,'stale_seconds') or 900)
        local used={}
        for i,key in ipairs({'session','weekly'}) do
            local reset=number(usage,name..'.'..key..'.reset')
            used[i]=not stale and (not reset or reset>now) and number(usage,name..'.'..key..'.used') or nil
        end
        shapes(function()
            local start=lower and -90 or -72
            ticks(cr,p.quota_x,y,p.quota_outer_radius,start,-198,90,used[1],cyan,2.5,p.quota_outer_span)
            ticks(cr,p.quota_x,y,p.quota_inner_radius,start,-198,90,used[2],{.70,.86,1},2.3,p.quota_inner_span)
        end)
        text(title,p.quota_text_x,y-48,25,white,CAIRO_FONT_WEIGHT_BOLD)
        local hours=(number(usage,name..'.session.minutes') or 300)/60
        quota_line(string.format('%g h',hours),used[1],y-2,20,cyan)
        quota_line('Semanal',used[2],y+39,18,{.35,.72,1})
        local source=usage[name..'.source'] or ''
        local note=stale and 'Sin lectura vigente' or (name=='chatgpt' and 'Cuota Codex' or (source=='imported' and 'Lectura importada' or 'Suscripción'))
        text(note,p.quota_text_x,y+75,10,muted)
    end
    quota('chatgpt','ChatGPT',p.quota_top_y,false)
    quota('claude','Claude',p.quota_bottom_y,true)
    local outer=p.gauge_radius+p.gauge_span
    local thermal_outer=p.temperature_radius+p.temperature_span
    local thermal_mask={p.temperature_x,p.temperature_y,thermal_outer+p.occlusion_gap}
    local gpu_mask={p.gauge_x,p.gpu_y,outer+p.occlusion_gap}
    local cpu_mask={p.gauge_x,p.cpu_y,outer+p.occlusion_gap}
    local function gauge_ring(key,y,upper,masks)
        local v=number(telemetry,key)
        shapes(function()
            orbita_clip_background(cr,p.width,p.height,masks,function()
                -- A complete circle continues behind the next disk and off screen.
                -- The visible half advances from the top (GPU) or bottom (CPU).
                local filled=v and math.floor(math.max(0,math.min(100,v))*p.gauge_count/200+.5) or 0
                for i=0,p.gauge_count-1 do
                    local angle=((upper and -90 or 90)+(upper and -1 or 1)*360*i/p.gauge_count)*PI/180
                    local x1,y1=polar(p.gauge_x,y,p.gauge_radius,angle)
                    local x2,y2=polar(p.gauge_x,y,outer,angle)
                    line(cr,x1,y1,x2,y2,2.2,i<filled and {.02,1,.64} or muted,i<filled and 1 or .48)
                end
            end)
        end)
    end
    gauge_ring('vram.percent',p.vram_y,true,{gpu_mask,thermal_mask})
    gauge_ring('ram.percent',p.ram_y,false,{cpu_mask,thermal_mask})
    gauge_ring('gpu.load',p.gpu_y,true,{thermal_mask})
    gauge_ring('cpu.load',p.cpu_y,false,{thermal_mask})
    local gpu=number(telemetry,'gpu.temperature'); local cpu=number(telemetry,'cpu.temperature')
    local function thermal(value,upper)
        local stops={{0,.80,1},{.16,.43,1},{.64,.30,1},{.97,.22,.63},{1,.32,.19}}
        local edge_angle=math.acos(math.max(-1,math.min(1,(p.width-p.temperature_x)/thermal_outer)))*180/PI
        local visible_fraction=math.max(.01,(178-edge_angle)/176)
        for i=0,71 do
            local fraction=i/71
            local progress=math.min(1,fraction/visible_fraction)
            local v=(upper and progress or 1-progress)*4
            local index=math.min(4,math.floor(v)+1); local k=v-(index-1)
            local a,b=stops[index],stops[index+1]
            local c={a[1]+(b[1]-a[1])*k,a[2]+(b[2]-a[2])*k,a[3]+(b[3]-a[3])*k}
            local angle=((upper and 182 or 178)+(upper and 176 or -176)*fraction)*PI/180
            local x1,y1=polar(p.temperature_x,p.temperature_y,p.temperature_radius,angle)
            local x2,y2=polar(p.temperature_x,p.temperature_y,thermal_outer,angle)
            local alpha=value and (progress<=math.max(0,math.min(1,value/120)) and 1 or .55) or .30
            line(cr,x1,y1,x2,y2,3,value and c or muted,alpha)
        end
    end
    shapes(function()
        thermal(gpu,true); thermal(cpu,false)
    end)
    local function gauge_label(caption,key,y,upper)
        local label_offset=upper and p.gauge_label_upper or p.gauge_label_lower
        local value_offset=upper and p.gauge_value_upper or p.gauge_value_lower
        text(caption,p.gauge_text_x,y+label_offset,15,white,CAIRO_FONT_WEIGHT_BOLD,p.gauge_text_width)
        text(percentage(number(telemetry,key)),p.gauge_text_x,y+value_offset,32,white,CAIRO_FONT_WEIGHT_BOLD,p.gauge_text_width)
    end
    gauge_label('VRAM','vram.percent',p.vram_y,true)
    gauge_label('GPU','gpu.load',p.gpu_y,true)
    gauge_label('CPU','cpu.load',p.cpu_y,false)
    gauge_label('RAM','ram.percent',p.ram_y,false)
    text('GPU',p.temperature_text_x,425,16,white,CAIRO_FONT_WEIGHT_BOLD)
    text(temperature(gpu),p.temperature_text_x,465,34,white,CAIRO_FONT_WEIGHT_BOLD,p.temperature_text_width)
    line(cr,X(335),500,X(453),500,1,muted,.6)
    text('CPU',p.temperature_text_x,535,16,white,CAIRO_FONT_WEIGHT_BOLD)
    text(temperature(cpu),p.temperature_text_x,575,34,white,CAIRO_FONT_WEIGHT_BOLD,p.temperature_text_width)
    cairo_restore(cr)
end

function conky_orbita_start()
    os.execute('python3 '..quote(ROOT..'/runner.py')..' daemon --ensure >/dev/null 2>&1 &')
end

local function draw(kind)
    if not conky_window then return end
    local w=conky_window
    local surface=cairo_xlib_surface_create(w.display,w.drawable,w.visual,w.width,w.height)
    local cr=cairo_create(surface)
    local data=read('telemetry',6); local usage=read('usage',900); local audio=read('audio',2)
    if kind=='clock' then orbita_draw_clock(cr,w.width,w.height,data,usage,audio)
    else
        -- Render the complete transparent frame in memory. Xlib/Conky back buffers
        -- must receive the cleared holes too, not just the newly painted ticks.
        local frame=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,w.width,w.height)
        local frame_cr=cairo_create(frame)
        orbita_clear_panel_surface(frame_cr)
        cairo_translate(frame_cr,1,1)
        orbita_draw_panel(frame_cr,w.width-2,w.height-2,data,usage,audio)
        cairo_destroy(frame_cr)
        cairo_set_operator(cr,CAIRO_OPERATOR_SOURCE)
        cairo_set_source_surface(cr,frame,0,0)
        cairo_paint(cr)
        cairo_surface_destroy(frame)
    end
    cairo_destroy(cr); cairo_surface_destroy(surface)
end
function conky_orbita_clock() draw('clock') end
function conky_orbita_panel() draw('panel') end
