import tb

def best_weapon():
    best=None
    for it in tb.inventory():
        if it['damage']>0 and it['pick']==0 and it['axe']==0 and it['hammer']==0 and not it['ammo'] and it['place_tile'] is None:
            if best is None or it['damage']>best['damage']:
                best=it
    return best

def fight(radius=12, max_ticks=900):
    """Kill hostile non-boss NPCs within radius."""
    w=best_weapon()
    if w: tb.select(w['slot'])
    t=0; kills=0
    while t<max_ticks:
        me=tb.me()
        if me['dead']: return kills
        hs=[n for n in tb.npcs(radius) if n['hostile'] and not n['town']]
        if not hs: return kills
        n=min(hs,key=lambda n:abs(n['x']-me['x'])+abs(n['y']-me['y']))
        dx=n['x']-me['x']
        if abs(dx)>2.5:
            d=1 if dx>0 else -1
            keys=['right' if d>0 else 'left']
            if n['y']<me['y']-2: keys.append('jump')
            tb.hold(keys,ticks=8,aim=(n['x'],n['y']))
            t+=8
        else:
            r=tb.swing_at(n)
            t+=15
            if r is None: kills+=1
    return kills