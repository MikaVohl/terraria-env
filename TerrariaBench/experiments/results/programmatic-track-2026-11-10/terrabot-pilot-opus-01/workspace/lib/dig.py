import tb, time
def dig_down(rows, maxt=120):
    t0=time.time()
    start=tb.me()['foot_y']
    stuck=0
    tb.select('Copper Pickaxe') if not tb.has('Iron Pickaxe') else tb.select('Iron Pickaxe')
    while tb.me()['foot_y']<start+rows and time.time()-t0<maxt:
        me=tb.me(); fy=me['foot_y']
        l=int(me['left']); r=int(me['left']+me['width']-0.01)
        g=tb.tiles(l-1,fy+1,r+1,fy+3)
        if any(g.liquid(c,fy+k) for c in range(l,r+1) for k in range(1,3)):
            return 'liquid'
        for c in range(l,r+1):
            for k in (1,2):
                if g.known(c,fy+k) and g.empty(c,fy+k): continue
                for _ in range(6):
                    tb.use_at(c,fy+k,ticks=20)
                    gg=tb.tiles(c,fy+k,c,fy+k)
                    if gg.known(c,fy+k) and not gg.solid(c,fy+k): break
        tb.sleep(12)
        if tb.me()['foot_y']==fy:
            stuck+=1
            if stuck>3: return 'stuck'
        else: stuck=0
    return tb.me()['foot_y']