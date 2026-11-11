import tb
ORES=['Copper','Tin','Iron','Lead','Silver','Tungsten','Gold','Platinum']
def scan(r=40):
    out=[]
    for k in ORES:
        for p in tb.find_tiles(k,radius=r,limit=40): out.append((k,p))
    me=tb.me()
    out.sort(key=lambda kp:abs(kp[1][0]-me['x'])+abs(kp[1][1]-me['y']))
    return out
def mine_ores(r=30, maxn=60, tmax=120):
    import time
    t0=time.time(); n=0
    while n<maxn and time.time()-t0<tmax:
        s=scan(r)
        if not s: break
        k,(x,y)=s[0]
        me=tb.me()
        if abs(x-me['x'])>4 or abs(y-me['y'])>4:
            tb.goto(x,y+1,dig=True,near=3,timeout=15)
        try: ok=tb.mine(x,y,timeout_ticks=300)
        except Exception as e: ok=False
        if not ok:
            # try get closer once
            tb.goto(x,y+1,dig=True,near=1,timeout=10)
            try: ok=tb.mine(x,y,timeout_ticks=300)
            except Exception: ok=False
            if not ok: break
        n+=1
    return n