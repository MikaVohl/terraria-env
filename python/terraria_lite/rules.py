"""Machine-readable player knowledge, read from the same C tables as the UI."""
import ctypes as C
import json
from terraria_lite import SPEC, _lib

def player_knowledge():
    for name in ("tl_recipe_name","tl_recipe_station"):
        fn=getattr(_lib,name); fn.argtypes=[C.c_int]; fn.restype=C.c_char_p
    for name in ("tl_recipe_inputs","tl_recipe_action","tl_item_terraria_id"):
        fn=getattr(_lib,name); fn.argtypes=[C.c_int]; fn.restype=C.c_int
    for name in ("tl_recipe_item","tl_recipe_qty"):
        fn=getattr(_lib,name); fn.argtypes=[C.c_int,C.c_int]; fn.restype=C.c_int
    _lib.tl_recipe_count.argtypes=[]; _lib.tl_recipe_count.restype=C.c_int
    recipes=[]
    for i in range(_lib.tl_recipe_count()):
        ingredients={SPEC.item_names[_lib.tl_recipe_item(i,j)]:_lib.tl_recipe_qty(i,j)
                     for j in range(_lib.tl_recipe_inputs(i))}
        recipes.append({"name":_lib.tl_recipe_name(i).decode(),"ingredients":ingredients,
                        "station":_lib.tl_recipe_station(i).decode(),
                        "action":_lib.tl_recipe_action(i)})
    return {"environment_version":SPEC.version,
            "player_geometry":{"width_tiles":SPEC.player_w,"height_tiles":SPEC.player_h,"anchor":"left feet cell"},
            "core_rules":{"trees":"pass-through and non-opaque; axe felling; chop before mining supporting ground",
                          "furniture":"non-solid; benches/anvils support from above",
                          "base_jump_height_tiles":SPEC.jump_height,"safe_fall_tiles":SPEC.fall_safe,"fall_damage_per_excess_tile":SPEC.fall_damage,"life_crystal_health_cap":SPEC.health_cap},
            "starting_equipment":[{"name":"Copper Pickaxe","terraria_id":3509},
                                  {"name":"Copper Axe","terraria_id":3506},
                                  {"name":"Copper Shortsword","terraria_id":3507}],
            "harvesting":"Cutting a tree removes the connected trunk above the cut; one wood per removed trunk cell. Directional mining automatically uses the axe for trees.",
            "actions":SPEC.action_names,
            "achievements":SPEC.achievement_names,"recipes":recipes,
            "items":[{"name":n,"terraria_id":_lib.tl_item_terraria_id(i)}
                     for i,n in enumerate(SPEC.item_names)]}

if __name__=="__main__": print(json.dumps(player_knowledge(),indent=2))
