using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

namespace TerrariaBenchObserver;

// v10 transfer PoC only (observer 0.8-poc). Inactive unless TERRARIABENCH_POC_DIR is set, so the
// benchmark profiles never see it. Lockstep: after each action the game thread blocks in
// PostUpdateEverything until the driver writes the next command (the game is paused between steps).
// Inputs are the player's control flags and the mouse position, set in SetControls for exactly
// `ticks` game updates (the same flags held keys / mouse buttons set). Declared shortcuts (not game
// input): hold (select an inventory item), craft (one real recipe, real ingredients and stations),
// loot (Loot All of a chest within reach), equip (body armour).
public static class PocBridge
{
    public static string Dir => Environment.GetEnvironmentVariable("TERRARIABENCH_POC_DIR");
    public static bool Active => !string.IsNullOrWhiteSpace(Dir) && !Released;
    public static bool Released;

    public sealed class Action
    {
        public bool Left, Right, Jump, Down, Up, UseItem, UseTile, Aim;
        public float Wx, Wy;
        public int TicksLeft;
    }

    public static Action Current;
    public static long Tick;
    public static long Seq = -1;
    public static List<object> Results = new();
    public const int Radius = 24, RadiusY = 18;

    public static void Block(Player p)
    {
        string dir = Dir, cmd = Path.Combine(dir, "cmd.json");
        WriteState(p, dir);
        while (true)
        {
            if (File.Exists(Path.Combine(dir, "release"))) { Released = true; Current = null; return; }
            if (File.Exists(cmd)) break;
            Thread.Sleep(1);
        }
        string text = File.ReadAllText(cmd);
        File.Delete(cmd);
        using var doc = JsonDocument.Parse(text);
        var root = doc.RootElement;
        Seq = root.GetProperty("seq").GetInt64();
        Results = new List<object>();
        if (root.TryGetProperty("ops", out var ops))
            foreach (var op in ops.EnumerateArray())
                Results.Add(Run(p, op));
        var a = new Action { TicksLeft = root.TryGetProperty("ticks", out var t) ? t.GetInt32() : 15 };
        if (root.TryGetProperty("input", out var input))
        {
            bool B(string k) => input.TryGetProperty(k, out var v) && v.GetBoolean();
            a.Left = B("left"); a.Right = B("right"); a.Jump = B("jump"); a.Down = B("down"); a.Up = B("up");
            a.UseItem = B("use"); a.UseTile = B("use_tile");
            if (input.TryGetProperty("aim", out var aim))
            { a.Aim = true; a.Wx = (float)aim[0].GetDouble(); a.Wy = (float)aim[1].GetDouble(); }
        }
        Current = a;
    }

    static string[] Names(JsonElement op) => op.GetProperty("names").EnumerateArray().Select(x => x.GetString()).ToArray();

    static object Run(Player p, JsonElement op)
    {
        string kind = op.GetProperty("op").GetString();
        try
        {
            switch (kind)
            {
                case "hold": return Hold(p, Names(op));
                case "craft": return Craft(p, Names(op));
                case "loot": return Loot(p);
                case "equip": return Equip(p, Names(op));
            }
            return new { op = kind, ok = false, why = "unknown op" };
        }
        catch (Exception e) { return new { op = kind, ok = false, why = e.Message }; }
    }

    static object Hold(Player p, string[] names)
    {
        foreach (string name in names)
            for (int slot = 0; slot < 50; slot++)
                if (!p.inventory[slot].IsAir && p.inventory[slot].Name == name)
                {
                    int target = slot;
                    if (slot >= 10) { (p.inventory[9], p.inventory[slot]) = (p.inventory[slot], p.inventory[9]); target = 9; }
                    p.selectedItem = target;
                    return new { op = "hold", ok = true, name, slot = target };
                }
        return new { op = "hold", ok = false, why = "not in inventory" };
    }

    static int Count(Player p, Recipe r, Item req) =>
        p.inventory.Take(58).Where(i => !i.IsAir && (i.type == req.type || r.AcceptedByItemGroups(i.type, req.type))).Sum(i => i.stack);

    static object Craft(Player p, string[] names)
    {
        p.AdjTiles();
        foreach (string name in names)
            for (int n = 0; n < Recipe.numRecipes; n++)
            {
                Recipe r = Main.recipe[n];
                if (r == null || r.createItem.IsAir || r.createItem.Name != name || r.Disabled) continue;
                if (r.requiredTile.Any(tile => tile >= 0 && !p.adjTile[tile])) continue;
                if (!r.Conditions.All(c => c.IsMet())) continue;
                if (!r.requiredItem.All(req => req.IsAir || Count(p, r, req) >= req.stack)) continue;
                foreach (Item req in r.requiredItem)
                {
                    int need = req.stack;
                    for (int s = 0; s < 58 && need > 0 && !req.IsAir; s++)
                    {
                        Item i = p.inventory[s];
                        if (i.IsAir || !(i.type == req.type || r.AcceptedByItemGroups(i.type, req.type))) continue;
                        int take = Math.Min(need, i.stack);
                        i.stack -= take; need -= take;
                        if (i.stack <= 0) i.TurnToAir();
                    }
                }
                p.QuickSpawnItem(new EntitySource_Misc("v10-poc craft shortcut"), r.createItem.type, r.createItem.stack);
                ReferenceObserver.Record("crafted", new Dictionary<string, object> {
                    ["item_type"] = r.createItem.type, ["stack"] = r.createItem.stack, ["name"] = r.createItem.Name, ["via"] = "v10_poc_shortcut" });
                return new { op = "craft", ok = true, name, stack = r.createItem.stack };
            }
        return new { op = "craft", ok = false, why = "no satisfiable recipe (items/station)" };
    }

    static object Loot(Player p)
    {
        int cx = (int)(p.Center.X / 16), cy = (int)(p.Center.Y / 16);
        for (int x = cx - 4; x <= cx + 4; x++)
            for (int y = cy - 4; y <= cy + 4; y++)
            {
                if (!WorldGen.InWorld(x, y)) continue;
                Tile t = Main.tile[x, y];
                if (!t.HasTile || !TileID.Sets.BasicChest[t.TileType]) continue;
                int left = x - (t.TileFrameX % 36) / 18, top = y - (t.TileFrameY % 36) / 18;
                int c = Chest.FindChest(left, top);
                if (c < 0) continue;
                int moved = 0;
                foreach (Item i in Main.chest[c].item)
                {
                    if (i == null || i.IsAir) continue;
                    p.QuickSpawnItem(new EntitySource_Misc("v10-poc loot shortcut"), i.type, i.stack);
                    moved += i.stack; i.TurnToAir();
                }
                return new { op = "loot", ok = moved > 0, chest = new[] { left, top }, moved };
            }
        return new { op = "loot", ok = false, why = "no chest within 4 tiles" };
    }

    static object Equip(Player p, string[] names)
    {
        foreach (string name in names)
            for (int s = 0; s < 50; s++)
                if (!p.inventory[s].IsAir && p.inventory[s].Name == name)
                {
                    (p.armor[1], p.inventory[s]) = (p.inventory[s], p.armor[1]);
                    return new { op = "equip", ok = true, name };
                }
        return new { op = "equip", ok = false, why = "no armour in inventory" };
    }

    static void WriteState(Player p, string dir)
    {
        int ptx = (int)(p.Center.X / 16), pty = (int)(p.Center.Y / 16);
        int x0 = ptx - Radius, y0 = pty - RadiusY, w = 2 * Radius + 1, h = 2 * RadiusY + 1;
        var type = new int[w * h]; var frame = new int[w * h]; var light = new int[w * h]; var liquid = new int[w * h]; var solid = new int[w * h];
        for (int r = 0; r < h; r++)
            for (int c = 0; c < w; c++)
            {
                int x = x0 + c, y = y0 + r, k = r * w + c;
                if (!WorldGen.InWorld(x, y)) { type[k] = -2; continue; }
                Tile t = Main.tile[x, y];
                type[k] = t.HasTile && !t.IsActuated ? t.TileType : -1;
                frame[k] = t.HasTile ? t.TileFrameX : 0;
                light[k] = (int)Math.Round(Math.Clamp(Lighting.Brightness(x, y), 0f, 1f) * 255);
                liquid[k] = t.LiquidAmount;
                solid[k] = t.HasTile && !t.IsActuated && Main.tileSolid[t.TileType] && !Main.tileSolidTop[t.TileType] ? 1 : 0;
            }
        var npcs = Main.npc.Where(n => n.active && n.life > 0 && !n.friendly && !n.townNPC && !n.CountsAsACritter
                                       && Math.Abs(n.Center.X - p.Center.X) < 40 * 16 && Math.Abs(n.Center.Y - p.Center.Y) < 30 * 16)
            .Select(n => new { id = n.whoAmI, type = n.type, net = n.netID, ai = n.aiStyle, name = n.TypeName, x = n.Center.X, y = n.Center.Y,
                               life = n.life, life_max = n.lifeMax, boss = n.boss, ai0 = n.ai[0] }).ToArray();
        var state = new {
            seq = Seq, tick = Tick, results = Results,
            player = new { x = p.position.X, y = p.position.Y, w = p.width, h = p.height, vx = p.velocity.X, vy = p.velocity.Y,
                           life = p.statLife, life_max = p.statLifeMax2, life_max_base = p.statLifeMax, dead = p.dead, dir = p.direction,
                           jump = p.jump, anim = p.itemAnimation, anim_max = p.itemAnimationMax, immune = p.immuneTime,
                           potion_delay = p.potionDelay, fall_start = p.fallStart, sel = p.selectedItem,
                           held = p.HeldItem.Name, pulley = p.pulley, body_armor = p.armor[1].Name,
                           item_time = p.itemTime,
                           hits = p.hitTile.data.Where(d => d != null && d.damage > 0).Select(d => new[] { d.X, d.Y, d.damage }).ToArray(),
                           adj = new[] { p.adjTile[TileID.WorkBenches], p.adjTile[TileID.Furnaces], p.adjTile[TileID.Anvils], p.adjTile[TileID.DemonAltar] } },
            inv = p.inventory.Take(58).Select((i, s) => new { s, t = i.type, n = i.stack, name = i.Name }).Where(e => e.t > 0).ToArray(),
            world = new { day = Main.dayTime, time = Main.time, surface = Main.worldSurface, rock = Main.rockLayer,
                          spawn = new[] { Main.spawnTileX, Main.spawnTileY }, size = new[] { Main.maxTilesX, Main.maxTilesY },
                          eoc_down = NPC.downedBoss1 },
            screen = new { x = Main.screenPosition.X, y = Main.screenPosition.Y, w = Main.screenWidth, h = Main.screenHeight, zoom = Main.GameZoomTarget },
            grid = new { x0, y0, w, h, type, frame, light, liquid, solid },
            npcs
        };
        string path = Path.Combine(dir, "state.json"), tmp = path + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(state));
        File.Move(tmp, path, true);
    }
}

public sealed class PocSystem : ModSystem
{
    public override void OnWorldLoad() { PocBridge.Current = null; PocBridge.Tick = 0; }

    public override void PostUpdateEverything()
    {
        if (!PocBridge.Active || Main.gameMenu || Main.netMode != NetmodeID.SinglePlayer) return;
        Player p = Main.LocalPlayer;
        if (!p.active) return;
        PocBridge.Tick++;
        var a = PocBridge.Current;
        if (a != null && --a.TicksLeft > 0) return;
        PocBridge.Current = null;
        try { PocBridge.Block(p); }
        catch (Exception e) { Mod.Logger.Error("v10 PoC bridge stopped.", e); PocBridge.Released = true; }
    }
}

public sealed class PocPlayer : ModPlayer
{
    public override void SetControls()
    {
        if (!PocBridge.Active || Player.whoAmI != Main.myPlayer) return;
        var a = PocBridge.Current;
        Player.controlLeft = a?.Left ?? false; Player.controlRight = a?.Right ?? false;
        Player.controlJump = a?.Jump ?? false; Player.controlDown = a?.Down ?? false; Player.controlUp = a?.Up ?? false;
        Player.controlUseItem = a?.UseItem ?? false; Player.controlUseTile = a?.UseTile ?? false;
        Player.controlHook = Player.controlMount = Player.controlQuickHeal = Player.controlQuickMana = Player.controlThrow = false;
        Player.controlSmart = false;
        if (a != null && a.Aim)
        {
            Main.mouseX = (int)Math.Round((a.Wx - Main.screenPosition.X) * Main.GameZoomTarget);
            Main.mouseY = (int)Math.Round((a.Wy - Main.screenPosition.Y) * Main.GameZoomTarget);
        }
    }
}
