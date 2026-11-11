using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.Map;
using Terraria.ModLoader;
using Terraria.UI;

namespace TerraBot;

// tb-api-1.0-rc1. Inert unless TERRABOT_SOCKET is set. A Unix-socket JSON-lines server whose requests run on the
// game thread. Fairness rules (see terrariabench/tb/CONTRACT.md):
//  * reads: tiles lit on screen show their live state; other tiles show what the player's own map remembers
//    (Main.Map, only where revealed); NPCs and items only when on screen and lit (or within 4 tiles); NPC fields
//    are position, type, name and health, never AI state;
//  * actions: the player's control flags + cursor for N game updates (movement, item use, tile interaction), and the
//    real UI code for inventory-only steps: hotbar select, Main.CraftItem, ItemSlot.SwapEquip, chest transfers with a
//    chest the player opened itself. Nothing edits tiles, spawns items or moves the player directly.
public sealed class TerraBot : Mod
{
    public override void Load() => Server.Start(Logger);
    public override void Unload() => Server.Stop();
}

public sealed class Job
{
    public long Id;
    public string Op;
    public JsonElement Args;
    public string Reply;
    public readonly ManualResetEventSlim Done = new();
}

public static class Server
{
    public static string SocketPath => Environment.GetEnvironmentVariable("TERRABOT_SOCKET");
    public static string Dir => Environment.GetEnvironmentVariable("TERRABOT_DIR");
    public static bool TestMode => Environment.GetEnvironmentVariable("TERRABOT_TEST") == "1";
    public static bool Enabled => !string.IsNullOrWhiteSpace(SocketPath);
    public static readonly ConcurrentQueue<Job> Queue = new();
    public static volatile bool InWorld;
    static Socket listener;
    static volatile bool running;
    static log4net.ILog log;

    public static void Start(log4net.ILog logger)
    {
        if (!Enabled || Main.dedServ) return;
        log = logger;
        string path = SocketPath;
        if (File.Exists(path)) File.Delete(path);
        listener = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
        listener.Bind(new UnixDomainSocketEndPoint(path));
        listener.Listen(8);
        running = true;
        new Thread(AcceptLoop) { IsBackground = true, Name = "TerraBot accept" }.Start();
        log.Info($"TerraBot {Api.Version} listening on {path}");
    }

    public static void Stop()
    {
        running = false;
        try { listener?.Close(); } catch { }
        listener = null;
        try { if (Enabled && File.Exists(SocketPath)) File.Delete(SocketPath); } catch { }
    }

    static void AcceptLoop()
    {
        while (running)
        {
            Socket s;
            try { s = listener.Accept(); }
            catch { if (!running) return; continue; }
            new Thread(() => Serve(s)) { IsBackground = true, Name = "TerraBot conn" }.Start();
        }
    }

    static void Serve(Socket s)
    {
        using var stream = new NetworkStream(s, true);
        using var reader = new StreamReader(stream, new UTF8Encoding(false));
        using var writer = new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = true, NewLine = "\n" };
        try
        {
            string line;
            while (running && (line = reader.ReadLine()) != null)
            {
                if (string.IsNullOrWhiteSpace(line)) continue;
                var job = new Job();
                string reply;
                try
                {
                    using var doc = JsonDocument.Parse(line);
                    var root = doc.RootElement;
                    job.Id = root.TryGetProperty("id", out var id) ? id.GetInt64() : 0;
                    job.Op = root.GetProperty("op").GetString();
                    job.Args = root.TryGetProperty("args", out var a) ? a.Clone() : JsonDocument.Parse("{}").RootElement.Clone();
                    if (job.Op == "ping")
                        reply = Api.Ok(job.Id, new Dictionary<string, object> { ["in_world"] = InWorld, ["api"] = Api.Version, ["test_mode"] = TestMode });
                    else
                    {
                        Queue.Enqueue(job);
                        int limit = 30000 + (job.Args.TryGetProperty("ticks", out var t) && t.ValueKind == JsonValueKind.Number ? t.GetInt32() * 40 : 0);
                        reply = job.Done.Wait(limit) ? job.Reply : Api.Err(job.Id, "game did not answer in time (not in a world, or paused)");
                    }
                }
                catch (Exception e) { reply = Api.Err(job.Id, "bad request: " + e.Message); }
                writer.WriteLine(reply);
            }
        }
        catch (IOException) { }
        catch (ObjectDisposedException) { }
    }

    public static void Journal(string file, Dictionary<string, object> data)
    {
        if (string.IsNullOrWhiteSpace(Dir)) return;
        try { File.AppendAllText(Path.Combine(Dir, file), JsonSerializer.Serialize(data) + "\n"); }
        catch (Exception e) { log?.Warn("TerraBot journal write failed: " + e.Message); }
    }
}

// One held input: control flags + cursor for Ticks game updates.
public sealed class Hold
{
    public HashSet<string> Keys = new();
    public bool Aim;
    public float Wx, Wy; // world pixels
    public int Ticks, Applied;
    public long StartTick;
    public Job Job;
}

public static class Api
{
    public const string Version = "tb-api-1.0-rc1";
    public static readonly string[] KeyNames = { "left", "right", "up", "down", "jump", "use", "use_tile", "quick_heal", "quick_mana", "quick_buff", "hook" };
    public const int MaxHoldTicks = 600;
    public static Hold Current;
    public static readonly List<(Job job, long until)> Waits = new();
    public static readonly List<Dictionary<string, object>> Events = new();
    public static long EventSeq, Tick;
    static bool? wasDay;
    static HashSet<int> stationTiles;

    public static string Ok(long id, object result) => JsonSerializer.Serialize(new Dictionary<string, object> { ["id"] = id, ["ok"] = true, ["result"] = result });
    public static string Err(long id, string error) => JsonSerializer.Serialize(new Dictionary<string, object> { ["id"] = id, ["ok"] = false, ["error"] = error });

    public static void Finish(Job job, object result)
    {
        if (job == null) return;
        job.Reply = Ok(job.Id, result);
        job.Done.Set();
    }

    public static void Fail(Job job, string error)
    {
        job.Reply = Err(job.Id, error);
        job.Done.Set();
    }

    public static void Event(string kind, Dictionary<string, object> data = null)
    {
        var e = data ?? new Dictionary<string, object>();
        e["seq"] = ++EventSeq; e["event"] = kind; e["tick"] = Tick;
        Events.Add(e);
        if (Events.Count > 4000) Events.RemoveRange(0, 1000);
        Server.Journal("game_events.jsonl", new Dictionary<string, object>(e) { ["unix"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0 });
    }

    // ---- update loop (game thread) ----
    public static void Update()
    {
        Player p = Main.LocalPlayer;
        Tick++;
        if (wasDay.HasValue && wasDay.Value != Main.dayTime) Event(Main.dayTime ? "dawn" : "dusk");
        wasDay = Main.dayTime;
        var h = Current;
        if (h != null && (h.Applied >= h.Ticks || p.dead || Tick - h.StartTick > h.Ticks + 30))
        {
            Current = null;
            Finish(h.Job, Short(p, new Dictionary<string, object> { ["ticks"] = h.Applied, ["interrupted_by_death"] = p.dead && h.Applied < h.Ticks }));
        }
        for (int i = Waits.Count - 1; i >= 0; i--)
            if (Tick >= Waits[i].until) { Finish(Waits[i].job, Short(p, new Dictionary<string, object>())); Waits.RemoveAt(i); }
        Drain(p);
    }

    // Requests are also dispatched right before the players update, so a hold sent in reply to the previous one
    // continues on the very next update (no released-keys gap between consecutive holds).
    public static void Drain(Player p)
    {
        while (Server.Queue.TryDequeue(out var job))
        {
            try { Dispatch(p, job); }
            catch (Exception e) { Fail(job, e.GetType().Name + ": " + e.Message); }
        }
    }

    public static void Reset()
    {
        if (Current != null) Fail(Current.Job, "world unloaded");
        Current = null;
        foreach (var w in Waits) Fail(w.job, "world unloaded");
        Waits.Clear();
        wasDay = null;
    }

    static Dictionary<string, object> Short(Player p, Dictionary<string, object> d)
    {
        d["x"] = R(p.Center.X / 16f); d["y"] = R(p.Center.Y / 16f); d["vx"] = R(p.velocity.X); d["vy"] = R(p.velocity.Y);
        d["life"] = p.statLife; d["dead"] = p.dead; d["tick"] = Tick;
        return d;
    }

    static double R(double v) => Math.Round(v, 3);

    static void Dispatch(Player p, Job job)
    {
        var a = job.Args;
        switch (job.Op)
        {
            case "me": Finish(job, Me(p)); return;
            case "inventory": Finish(job, Inventory(p)); return;
            case "time": Finish(job, Time()); return;
            case "world": Finish(job, World(p)); return;
            case "tiles": Finish(job, Tiles(p, I(a, "x0"), I(a, "y0"), I(a, "x1"), I(a, "y1"), false)); return;
            case "find_tiles": Finish(job, FindTiles(p, a)); return;
            case "npcs": Finish(job, Npcs(p, F(a, "radius", 100f), false)); return;
            case "items": Finish(job, Items(p, F(a, "radius", 100f))); return;
            case "events": Finish(job, Events.Where(e => (long)e["seq"] > L(a, "since", 0)).ToArray()); return;
            case "recipes": Finish(job, Recipes(p, a)); return;
            case "chest": Finish(job, ChestView(p)); return;
            case "input": StartHold(p, job); return;
            case "stop": if (Current != null) { var c = Current; Current = null; Finish(c.Job, Short(p, new Dictionary<string, object> { ["ticks"] = c.Applied, ["stopped"] = true })); }
                Finish(job, Short(p, new Dictionary<string, object>())); return;
            case "wait": Waits.Add((job, Tick + Math.Clamp(I(a, "ticks", 1), 1, 3600))); return;
            case "select": Act(job, Select(p, a)); return;
            case "craft": Act(job, Craft(p, S(a, "item"), Math.Clamp(I(a, "n", 1), 1, 999))); return;
            case "equip": Act(job, Equip(p, a)); return;
            case "take": Act(job, Take(p, S(a, "item"), I(a, "n", int.MaxValue))); return;
            case "put": Act(job, Put(p, S(a, "item"), I(a, "n", int.MaxValue))); return;
            case "close_chest": Act(job, CloseChest(p)); return;
            case "truth_tiles": if (!Server.TestMode) break; Finish(job, Tiles(p, I(a, "x0"), I(a, "y0"), I(a, "x1"), I(a, "y1"), true)); return;
            case "truth_npcs": if (!Server.TestMode) break; Finish(job, Npcs(p, F(a, "radius", 300f), true)); return;
            case "truth_edit": if (!Server.TestMode) break; Finish(job, TruthEdit(a)); return;
            case "truth_give": if (!Server.TestMode) break; Finish(job, TruthGive(p, S(a, "item"), Math.Clamp(I(a, "n", 1), 1, 9999))); return;
            case "truth_morning": if (!Server.TestMode) break; Main.dayTime = true; Main.time = 0; Finish(job, Time()); return;
        }
        Fail(job, "unknown op " + job.Op);
    }

    // Test mode only (map-memory leak test): change one cell behind the player's back, without TileFrame and so
    // without a map update, as an unseen change would. Returns the previous state for restoring.
    static Dictionary<string, object> TruthEdit(JsonElement a)
    {
        int x = I(a, "x"), y = I(a, "y");
        if (!WorldGen.InWorld(x, y, 1)) throw new ArgumentException("truth_edit: out of world");
        Tile t = Main.tile[x, y];
        var old = new Dictionary<string, object> { ["type"] = t.HasTile ? t.TileType : -1, ["liquid"] = (int)t.LiquidAmount };
        if (a.TryGetProperty("type", out var tv) && tv.ValueKind == JsonValueKind.Number)
        {
            int type = tv.GetInt32();
            t.HasTile = type >= 0;
            if (type >= 0) t.TileType = (ushort)type;
        }
        if (a.TryGetProperty("liquid", out var lv) && lv.ValueKind == JsonValueKind.Number)
        {
            t.LiquidAmount = (byte)Math.Clamp(lv.GetInt32(), 0, 255);
            t.LiquidType = LiquidID.Water;
        }
        return old;
    }

    // Test mode only (live pathfinder tests on dev worlds): items as setup (torches, blocks) without the hours of
    // gathering, given at the player like a pickup.
    static Dictionary<string, object> TruthGive(Player p, string name, int n)
    {
        int type = -1;
        for (int t = 1; t < ItemLoader.ItemCount && type < 0; t++)
            if (string.Equals(Lang.GetItemNameValue(t), name, StringComparison.OrdinalIgnoreCase)) type = t;
        if (type < 0) throw new ArgumentException($"truth_give: unknown item '{name}'");
        p.QuickSpawnItem(p.GetSource_Misc("TerraBotTest"), type, n);
        return new Dictionary<string, object> { ["item"] = Lang.GetItemNameValue(type), ["n"] = n };
    }

    static void Act(Job job, Dictionary<string, object> r)
    {
        Server.Journal("game_actions.jsonl", new Dictionary<string, object> { ["tick"] = Tick, ["op"] = job.Op, ["args"] = job.Args.GetRawText(),
            ["ok"] = r.TryGetValue("ok", out var ok) && (bool)ok, ["unix"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0 });
        if (r.TryGetValue("ok", out var good) && !(bool)good) Fail(job, (string)r["why"]); else Finish(job, r);
    }

    // ---- arg helpers ----
    static int I(JsonElement a, string k, int d = 0) => a.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number ? (int)Math.Floor(v.GetDouble()) : d;
    static long L(JsonElement a, string k, long d = 0) => a.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetInt64() : d;
    static float F(JsonElement a, string k, float d = 0) => a.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number ? (float)v.GetDouble() : d;
    static string S(JsonElement a, string k) => a.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

    // ---- visibility (no X-ray) ----
    static Rectangle ScreenPx() => new((int)Main.screenPosition.X, (int)Main.screenPosition.Y,
        (int)(Main.screenWidth / Main.GameZoomTarget), (int)(Main.screenHeight / Main.GameZoomTarget));

    static bool OnScreenLit(int x, int y)
    {
        var s = ScreenPx();
        return x * 16 + 16 > s.Left && x * 16 < s.Right && y * 16 + 16 > s.Top && y * 16 < s.Bottom && Lighting.Brightness(x, y) > 0.03f;
    }

    // Map memory: Main.Map[x, y].Type is a MapHelper lookup index (tile option, wall, liquid or background); this
    // inverts it once to the tile type (>= 0), MapWall, MapLiquid - liquidType, or MapAir (background/unmapped).
    const int MapAir = -1, MapWall = -3, MapLiquid = -10;
    public const int Remembered = 512;
    static int[] mapIndex;

    static int[] BuildMapIndex()
    {
        var a = new int[MapHelper.LookupCount()];
        Array.Fill(a, MapAir);
        void Set(int k, int v) { if (k > 0 && k < a.Length) a[k] = v; }
        for (int t = 0; t < Math.Min(MapHelper.tileLookup.Length, MapHelper.tileOptionCounts.Length); t++)
            for (int o = 0; o < MapHelper.tileOptionCounts[t]; o++) Set(MapHelper.tileLookup[t] + o, t);
        for (int w = 1; w < Math.Min(MapHelper.wallLookup.Length, MapHelper.wallOptionCounts.Length); w++)
            for (int o = 0; o < MapHelper.wallOptionCounts[w]; o++) Set(MapHelper.wallLookup[w] + o, MapWall);
        var f = typeof(MapHelper).GetField("liquidPosition", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
        int liquid = Convert.ToInt32(f.GetValue(null));
        for (int l = 0; l < LiquidID.Count; l++) Set(liquid + l, MapLiquid - l);
        return a;
    }

    static int LiquidFlag(int liquidType) => liquidType == LiquidID.Lava ? 8 : liquidType == LiquidID.Honey ? 16 : 4;

    // One cell as the player knows it: lit on screen (or truth) -> the live tile; revealed elsewhere -> what the
    // player's map shows (flag 512; slopes, half blocks, liquids under tiles and walls behind tiles are not on the
    // map); otherwise unknown (-2). flags: 1 solid, 2 platform, 4 water, 8 lava, 16 honey, 32 wall, 64 half block,
    // 128 sloped, 256 actuated, 512 remembered.
    static void CellView(int x, int y, bool truth, out int type, out int flags)
    {
        type = -2; flags = 0;
        if (!WorldGen.InWorld(x, y, 1)) return;
        if (truth || OnScreenLit(x, y))
        {
            Tile t = Main.tile[x, y];
            bool has = t.HasTile;
            type = has ? t.TileType : -1;
            if (has && !t.IsActuated && Main.tileSolid[t.TileType] && !Main.tileSolidTop[t.TileType]) flags |= 1;
            if (has && !t.IsActuated && Main.tileSolidTop[t.TileType]) flags |= 2;
            if (t.LiquidAmount > 0) flags |= LiquidFlag(t.LiquidType);
            if (t.WallType > 0) flags |= 32;
            if (has && t.IsHalfBlock) flags |= 64;
            if (has && t.Slope != SlopeType.Solid) flags |= 128;
            if (has && t.IsActuated) flags |= 256;
            return;
        }
        if (Main.Map == null || !Main.Map.IsRevealed(x, y)) return;
        mapIndex ??= BuildMapIndex();
        int m = Main.Map[x, y].Type;
        int v = m < mapIndex.Length ? mapIndex[m] : MapAir;
        flags = Remembered;
        if (v >= 0)
        {
            type = v;
            if (Main.tileSolid[v] && !Main.tileSolidTop[v]) flags |= 1;
            if (Main.tileSolidTop[v]) flags |= 2;
        }
        else
        {
            type = -1;
            if (v == MapWall) flags |= 32;
            else if (v <= MapLiquid) flags |= LiquidFlag(MapLiquid - v);
        }
    }

    static bool EntityVisible(Player p, Rectangle box)
    {
        if (Vector2.Distance(box.Center.ToVector2(), p.Center) < 4 * 16) return true;
        if (!box.Intersects(ScreenPx())) return false;
        int cx = box.Center.X / 16, cy = box.Center.Y / 16;
        return WorldGen.InWorld(cx, cy, 1) && Lighting.Brightness(cx, cy) > 0.03f;
    }

    // ---- reads ----
    public static string TileName(int type)
    {
        if (type < 0) return type == -1 ? "Empty" : "Unknown";
        if (type < TileID.Count && TileID.Search.TryGetName(type, out string n)) return n;
        return TileLoader.GetTile(type)?.Name ?? type.ToString();
    }

    static string ItemName(int type) => Lang.GetItemNameValue(type);

    static Dictionary<string, object> ItemView(Item i, int slot) => new()
    {
        ["slot"] = slot, ["name"] = i.Name, ["type"] = i.type, ["stack"] = i.stack, ["pick"] = i.pick, ["axe"] = i.axe * 5, ["hammer"] = i.hammer,
        ["damage"] = i.damage, ["place_tile"] = i.createTile >= 0 ? TileName(i.createTile) : null, ["place_wall"] = i.createWall > 0,
        ["place_solid"] = i.createTile >= 0 && Main.tileSolid[i.createTile] && !Main.tileSolidTop[i.createTile] && !Main.tileFrameImportant[i.createTile],
        ["consumable"] = i.consumable, ["heal_life"] = i.healLife, ["use_time"] = i.useTime, ["use_animation"] = i.useAnimation,
        ["tile_boost"] = i.tileBoost, ["auto_reuse"] = i.autoReuse, ["ammo"] = i.ammo > 0, ["armor"] = i.headSlot >= 0 || i.bodySlot >= 0 || i.legSlot >= 0,
        ["accessory"] = i.accessory, ["max_stack"] = i.maxStack,
    };

    static Dictionary<string, object> Me(Player p)
    {
        var buffs = new List<object>();
        for (int b = 0; b < Player.MaxBuffs; b++)
            if (p.buffType[b] > 0 && p.buffTime[b] > 0) buffs.Add(new Dictionary<string, object> { ["name"] = Lang.GetBuffName(p.buffType[b]), ["ticks"] = p.buffTime[b] });
        p.AdjTiles();
        var stations = new List<string>();
        stationTiles ??= Enumerable.Range(0, Recipe.numRecipes).Select(n => Main.recipe[n]).Where(r => r != null)
            .SelectMany(r => r.requiredTile).Where(t => t >= 0).ToHashSet();
        for (int t = 0; t < p.adjTile.Length; t++) if (p.adjTile[t] && stationTiles.Contains(t)) stations.Add(TileName(t));
        string layer = p.ZoneUnderworldHeight ? "underworld" : p.ZoneRockLayerHeight ? "cavern" : p.ZoneDirtLayerHeight ? "underground" : p.ZoneSkyHeight ? "space" : "surface";
        var biomes = new List<string>();
        if (p.ZoneJungle) biomes.Add("jungle"); if (p.ZoneSnow) biomes.Add("snow"); if (p.ZoneDesert) biomes.Add("desert");
        if (p.ZoneCorrupt) biomes.Add("corruption"); if (p.ZoneCrimson) biomes.Add("crimson"); if (p.ZoneDungeon) biomes.Add("dungeon");
        if (p.ZoneBeach) biomes.Add("ocean"); if (p.ZoneGlowshroom) biomes.Add("mushroom"); if (p.ZoneHallow) biomes.Add("hallow");
        bool onGround = p.velocity.Y == 0f && Collision.SolidCollision(p.position + new Vector2(0, p.height), p.width, 2, true);
        int fall = p.velocity.Y > 0 ? Math.Max(0, (int)(p.position.Y / 16f) - p.fallStart) : 0;
        Item h = p.HeldItem;
        return new Dictionary<string, object>
        {
            ["x"] = R(p.Center.X / 16f), ["y"] = R(p.Center.Y / 16f), ["left"] = R(p.position.X / 16f), ["top"] = R(p.position.Y / 16f),
            ["width"] = R(p.width / 16f), ["height"] = R(p.height / 16f),
            ["tile_x"] = (int)(p.Center.X / 16f), ["foot_y"] = (int)((p.position.Y + p.height - 1) / 16f),
            ["vx"] = R(p.velocity.X), ["vy"] = R(p.velocity.Y), ["on_ground"] = onGround, ["dir"] = p.direction, ["fall_tiles"] = fall,
            ["life"] = p.statLife, ["life_max"] = p.statLifeMax2, ["mana"] = p.statMana, ["mana_max"] = p.statManaMax2,
            ["defense"] = (int)p.statDefense, ["dead"] = p.dead, ["respawn_ticks"] = p.dead ? p.respawnTimer : 0,
            ["breath"] = p.breath, ["breath_max"] = p.breathMax, ["breath_ticks_per_point"] = p.breathCDMax,
            ["submerged"] = Collision.DrownCollision(p.position, p.width, p.height, p.gravDir),
            ["wet"] = p.wet, ["lava"] = p.lavaWet, ["immune_ticks"] = p.immune ? p.immuneTime : 0,
            ["potion_sickness_ticks"] = p.potionDelay,
            ["held"] = h.IsAir ? null : ItemView(h, p.selectedItem), ["selected_slot"] = p.selectedItem,
            ["item_busy_ticks"] = Math.Max(p.itemAnimation, p.itemTime),
            ["reach_tiles"] = new[] { Player.tileRangeX + (h.IsAir ? 0 : h.tileBoost), Player.tileRangeY + (h.IsAir ? 0 : h.tileBoost) },
            ["buffs"] = buffs, ["armor"] = p.armor.Take(3).Select(i => i.IsAir ? null : i.Name).ToArray(),
            ["accessories"] = p.armor.Skip(3).Take(7).Where(i => !i.IsAir).Select(i => i.Name).ToArray(),
            ["layer"] = layer, ["biomes"] = biomes, ["stations_near"] = stations,
            ["chest_open"] = p.chest >= 0, ["inventory_open"] = Main.playerInventory,
            ["spawn"] = new[] { p.SpawnX >= 0 ? p.SpawnX : Main.spawnTileX, p.SpawnY >= 0 ? p.SpawnY : Main.spawnTileY },
            ["tick"] = Tick,
        };
    }

    static object Inventory(Player p) =>
        p.inventory.Take(58).Select((i, s) => (i, s)).Where(e => !e.i.IsAir).Select(e => ItemView(e.i, e.s)).ToArray();

    static Dictionary<string, object> Time()
    {
        double t = Main.time + (Main.dayTime ? 4.5 * 3600 : 19.5 * 3600);
        int hh = (int)(t / 3600) % 24, mm = (int)(t % 3600 / 60);
        return new Dictionary<string, object> { ["day"] = Main.dayTime, ["clock"] = $"{hh:00}:{mm:00}", ["ticks_into_phase"] = R(Main.time),
            ["phase_length"] = Main.dayTime ? Main.dayLength : Main.nightLength, ["moon_phase"] = Main.moonPhase,
            ["blood_moon"] = Main.bloodMoon, ["eclipse"] = Main.eclipse, ["game_updates"] = Tick };
    }

    static Dictionary<string, object> World(Player p) => new()
    {
        ["api"] = Version, ["size"] = new[] { Main.maxTilesX, Main.maxTilesY }, ["spawn"] = new[] { Main.spawnTileX, Main.spawnTileY },
        ["screen_tiles"] = new[] { ScreenPx().Width / 16, ScreenPx().Height / 16 }, ["hardmode"] = Main.hardMode,
        ["eye_of_cthulhu_defeated"] = NPC.downedBoss1, ["difficulty"] = Main.GameMode, ["test_mode"] = Server.TestMode,
    };

    // flags: see CellView
    static object Tiles(Player p, int x0, int y0, int x1, int y1, bool truth)
    {
        if (x1 < x0) (x0, x1) = (x1, x0);
        if (y1 < y0) (y0, y1) = (y1, y0);
        x0 = Math.Max(0, x0); y0 = Math.Max(0, y0); x1 = Math.Min(Main.maxTilesX - 1, x1); y1 = Math.Min(Main.maxTilesY - 1, y1);
        int w = x1 - x0 + 1, hgt = y1 - y0 + 1;
        if (w <= 0 || hgt <= 0) return new Dictionary<string, object> { ["x0"] = x0, ["y0"] = y0, ["w"] = 0, ["h"] = 0, ["t"] = Array.Empty<int>(), ["f"] = Array.Empty<int>(), ["names"] = new Dictionary<string, string>() };
        if ((long)w * hgt > 40000) throw new ArgumentException("tiles(): at most 40000 cells per call");
        var type = new int[w * hgt]; var flags = new int[w * hgt]; var names = new Dictionary<string, string>();
        for (int r = 0; r < hgt; r++)
            for (int c = 0; c < w; c++)
            {
                int x = x0 + c, y = y0 + r, k = r * w + c;
                CellView(x, y, truth, out int tt, out int f);
                type[k] = tt;
                flags[k] = f;
                if (tt >= 0 && !names.ContainsKey(tt.ToString())) names[tt.ToString()] = TileName(tt);
            }
        return new Dictionary<string, object> { ["x0"] = x0, ["y0"] = y0, ["w"] = w, ["h"] = hgt, ["t"] = type, ["f"] = flags, ["names"] = names };
    }

    static object FindTiles(Player p, JsonElement a)
    {
        string kind = S(a, "kind") ?? "";
        int radius = Math.Clamp(I(a, "radius", 60), 1, 200), limit = Math.Clamp(I(a, "limit", 50), 1, 500);
        var types = new HashSet<int>();
        if (int.TryParse(kind, out int id)) types.Add(id);
        else
            for (int t = 0; t < TileLoader.TileCount; t++)
                if (string.Equals(TileName(t), kind, StringComparison.OrdinalIgnoreCase)) types.Add(t);
        if (types.Count == 0) throw new ArgumentException($"unknown tile kind '{kind}' (use TileID names such as Trees, Copper, Iron, Tin, Lead, Containers, Heart, DemonAltar)");
        int cx = (int)(p.Center.X / 16f), cy = (int)(p.Center.Y / 16f);
        var found = new List<(int d2, int x, int y)>();
        for (int x = cx - radius; x <= cx + radius; x++)
            for (int y = cy - radius; y <= cy + radius; y++)
            {
                CellView(x, y, false, out int tt, out _);
                if (tt < 0 || !types.Contains(tt)) continue;
                found.Add(((x - cx) * (x - cx) + (y - cy) * (y - cy), x, y));
            }
        return found.OrderBy(f => f.d2).Take(limit).Select(f => new[] { f.x, f.y }).ToArray();
    }

    static object Npcs(Player p, float radius, bool truth)
    {
        return Main.npc.Where(n => n.active && n.life > 0 && Vector2.Distance(n.Center, p.Center) <= radius * 16 && (truth || EntityVisible(p, n.Hitbox)))
            .OrderBy(n => Vector2.Distance(n.Center, p.Center))
            .Select(n => new Dictionary<string, object>
            {
                ["id"] = n.whoAmI, ["name"] = n.TypeName, ["type"] = n.type, ["x"] = R(n.Center.X / 16f), ["y"] = R(n.Center.Y / 16f),
                ["width"] = R(n.width / 16f), ["height"] = R(n.height / 16f), ["life"] = n.life, ["life_max"] = n.lifeMax,
                ["hostile"] = !n.friendly && !n.townNPC && !n.CountsAsACritter && n.damage > 0, ["boss"] = n.boss, ["town"] = n.townNPC,
            }).ToArray();
    }

    static object Items(Player p, float radius) =>
        Main.item.Where(i => i.active && !i.IsAir && Vector2.Distance(i.Center, p.Center) <= radius * 16 && EntityVisible(p, i.Hitbox))
            .OrderBy(i => Vector2.Distance(i.Center, p.Center))
            .Select(i => new Dictionary<string, object> { ["name"] = i.Name, ["type"] = i.type, ["stack"] = i.stack, ["x"] = R(i.Center.X / 16f), ["y"] = R(i.Center.Y / 16f) })
            .Take(100).ToArray();

    static string GroupOrName(Recipe r, Item req)
    {
        foreach (int g in r.acceptedGroups)
            if (RecipeGroup.recipeGroups.TryGetValue(g, out var group) && group.IconicItemId == req.type) return group.GetText();
        return req.Name;
    }

    static Dictionary<string, object> RecipeView(Recipe r) => new()
    {
        ["item"] = r.createItem.Name, ["stack"] = r.createItem.stack,
        ["ingredients"] = r.requiredItem.Where(i => !i.IsAir).Select(i => new object[] { GroupOrName(r, i), i.stack }).ToArray(),
        ["stations"] = r.requiredTile.Where(t => t >= 0).Select(TileName).ToArray(),
        ["conditions"] = r.Conditions.Select(c => c.Description.Value).ToArray(),
    };

    static object Recipes(Player p, JsonElement a)
    {
        string item = S(a, "item");
        bool available = !(a.TryGetProperty("available", out var av) && av.ValueKind == JsonValueKind.False);
        if (available)
        {
            p.AdjTiles();
            Recipe.FindRecipes();
            var list = new List<object>();
            for (int i = 0; i < Main.numAvailableRecipes; i++)
            {
                Recipe r = Main.recipe[Main.availableRecipe[i]];
                if (item == null || string.Equals(r.createItem.Name, item, StringComparison.OrdinalIgnoreCase)) list.Add(RecipeView(r));
            }
            return list;
        }
        if (string.IsNullOrWhiteSpace(item)) throw new ArgumentException("recipes(available=False) needs item=");
        var all = new List<object>();
        for (int n = 0; n < Recipe.numRecipes; n++)
        {
            Recipe r = Main.recipe[n];
            if (r != null && !r.createItem.IsAir && !r.Disabled && string.Equals(r.createItem.Name, item, StringComparison.OrdinalIgnoreCase)) all.Add(RecipeView(r));
        }
        return all;
    }

    static object ChestView(Player p)
    {
        if (p.chest < 0) return null;
        Item[] items = p.chest >= 0 ? Main.chest[p.chest].item : Array.Empty<Item>();
        return new Dictionary<string, object> { ["index"] = p.chest, ["items"] = items.Select((i, s) => (i, s)).Where(e => e.i != null && !e.i.IsAir).Select(e => ItemView(e.i, e.s)).ToArray() };
    }

    // ---- actions ----
    static void StartHold(Player p, Job job)
    {
        var a = job.Args;
        var hold = new Hold { Ticks = Math.Clamp(I(a, "ticks", 1), 1, MaxHoldTicks), StartTick = Tick, Job = job };
        if (a.TryGetProperty("keys", out var keys) && keys.ValueKind == JsonValueKind.Array)
            foreach (var k in keys.EnumerateArray())
            {
                string name = k.GetString();
                if (!KeyNames.Contains(name)) { Fail(job, $"unknown key '{name}'; keys are {string.Join(", ", KeyNames)}"); return; }
                hold.Keys.Add(name);
            }
        if (a.TryGetProperty("aim", out var aim) && aim.ValueKind == JsonValueKind.Array)
        { hold.Aim = true; hold.Wx = (float)aim[0].GetDouble() * 16f; hold.Wy = (float)aim[1].GetDouble() * 16f; }
        if (Current != null) { var old = Current; Finish(old.Job, Short(p, new Dictionary<string, object> { ["ticks"] = old.Applied, ["interrupted"] = true })); }
        Current = hold;
    }

    // Called from SetControls once per update of the local player.
    public static void ApplyControls(Player p)
    {
        var h = Current;
        bool on = h != null && h.Applied < h.Ticks;
        bool K(string k) => on && h.Keys.Contains(k);
        p.controlLeft = K("left"); p.controlRight = K("right"); p.controlUp = K("up"); p.controlDown = K("down");
        p.controlJump = K("jump"); p.controlUseItem = K("use"); p.controlUseTile = K("use_tile");
        p.controlQuickHeal = K("quick_heal"); p.controlQuickMana = K("quick_mana"); p.controlHook = K("hook");
        p.controlMount = p.controlThrow = p.controlSmart = p.controlTorch = false;
        if (K("quick_buff")) p.QuickBuff();
        if (on && h.Aim)
        {
            Main.mouseX = (int)Math.Round((h.Wx - Main.screenPosition.X) * Main.GameZoomTarget);
            Main.mouseY = (int)Math.Round((h.Wy - Main.screenPosition.Y) * Main.GameZoomTarget);
        }
        else if (on && (K("use") || K("use_tile")))
        {
            // Default cursor: two tiles in front of the player at chest height.
            Main.mouseX = (int)Math.Round((p.Center.X + p.direction * 32 - Main.screenPosition.X) * Main.GameZoomTarget);
            Main.mouseY = (int)Math.Round((p.Center.Y - Main.screenPosition.Y) * Main.GameZoomTarget);
        }
        if (on) h.Applied++;
    }

    static Dictionary<string, object> No(string why) => new() { ["ok"] = false, ["why"] = why };

    static int FindItem(Player p, JsonElement a, int maxSlot = 50)
    {
        if (a.TryGetProperty("slot", out var s) && s.ValueKind == JsonValueKind.Number) return s.GetInt32();
        string name = S(a, "item");
        for (int i = 0; i < maxSlot; i++)
            if (!p.inventory[i].IsAir && string.Equals(p.inventory[i].Name, name, StringComparison.OrdinalIgnoreCase)) return i;
        return -1;
    }

    // Hotbar keys select slots 0-9; an item elsewhere in the inventory is first dragged to the hotbar slot 9.
    static Dictionary<string, object> Select(Player p, JsonElement a)
    {
        if (p.itemAnimation > 0) return No("cannot switch items mid-swing");
        int slot = FindItem(p, a);
        if (slot < 0 || slot >= 50 || p.inventory[slot].IsAir) return No("item not in inventory");
        if (slot >= 10) { (p.inventory[9], p.inventory[slot]) = (p.inventory[slot], p.inventory[9]); slot = 9; }
        p.selectedItem = slot;
        return new Dictionary<string, object> { ["ok"] = true, ["slot"] = slot, ["item"] = p.inventory[slot].Name };
    }

    static void FlushMouseItem(Player p)
    {
        if (!Main.mouseItem.IsAir) Main.mouseItem = p.GetItem(p.whoAmI, Main.mouseItem, GetItemSettings.InventoryUIToInventorySettings);
    }

    // Same path as clicking a recipe in the crafting menu: Main.CraftItem (consumes ingredients via Recipe.Create and
    // fires the RecipeItemCreationContext hooks the observer journals), then the cursor item goes into the inventory.
    static Dictionary<string, object> Craft(Player p, string name, int n)
    {
        if (string.IsNullOrWhiteSpace(name)) return No("craft needs an item name");
        FlushMouseItem(p);
        if (!Main.mouseItem.IsAir) return No("inventory full");
        int made = 0, stack = 0;
        string product = name;
        for (int k = 0; k < n; k++)
        {
            p.AdjTiles();
            Recipe.FindRecipes();
            Recipe found = null;
            for (int i = 0; i < Main.numAvailableRecipes && found == null; i++)
            {
                Recipe r = Main.recipe[Main.availableRecipe[i]];
                if (string.Equals(r.createItem.Name, name, StringComparison.OrdinalIgnoreCase)) found = r;
            }
            if (found == null) break;
            Main.CraftItem(found);
            stack += found.createItem.stack;
            product = found.createItem.Name;
            made++;
            FlushMouseItem(p);
            if (!Main.mouseItem.IsAir) break; // inventory full: the product stays on the cursor and the game drops it
        }
        Recipe.FindRecipes();
        if (made == 0) return No(WhyNot(p, name));
        Event("crafted", new Dictionary<string, object> { ["item"] = product, ["times"] = made, ["stack"] = stack });
        return new Dictionary<string, object> { ["ok"] = true, ["item"] = name, ["times"] = made, ["stack"] = stack, ["requested"] = n };
    }

    static string WhyNot(Player p, string name)
    {
        var why = new List<string>();
        for (int n = 0; n < Recipe.numRecipes; n++)
        {
            Recipe r = Main.recipe[n];
            if (r == null || r.Disabled || !string.Equals(r.createItem.Name, name, StringComparison.OrdinalIgnoreCase)) continue;
            var miss = new List<string>();
            foreach (int t in r.requiredTile.Where(t => t >= 0)) if (!p.adjTile[t]) miss.Add("station " + TileName(t));
            foreach (Item req in r.requiredItem.Where(i => !i.IsAir))
            {
                int have = p.inventory.Take(58).Where(i => !i.IsAir && (i.type == req.type || r.AcceptedByItemGroups(i.type, req.type))).Sum(i => i.stack);
                if (have < req.stack) miss.Add($"{GroupOrName(r, req)} {have}/{req.stack}");
            }
            foreach (var c in r.Conditions) if (!c.IsMet()) miss.Add("condition " + c.Description.Value);
            why.Add(miss.Count == 0 ? "recipe should be available" : "missing " + string.Join(", ", miss));
        }
        return why.Count == 0 ? $"no recipe makes '{name}'" : $"cannot craft {name}: " + string.Join(" | ", why);
    }

    static Dictionary<string, object> Equip(Player p, JsonElement a)
    {
        int slot = FindItem(p, a);
        if (slot < 0 || slot >= 50 || p.inventory[slot].IsAir) return No("item not in inventory");
        string name = p.inventory[slot].Name;
        Item before = p.inventory[slot];
        ItemSlot.SwapEquip(p.inventory, ItemSlot.Context.InventoryItem, slot);
        bool ok = !ReferenceEquals(p.inventory[slot], before) || p.inventory[slot].IsAir;
        return ok ? new Dictionary<string, object> { ["ok"] = true, ["item"] = name } : No($"{name} cannot be equipped");
    }

    static Dictionary<string, object> Take(Player p, string name, int n)
    {
        if (p.chest < 0) return No("no chest open (open one with use_tile on it first)");
        Item[] items = Main.chest[p.chest].item;
        if (name == null)
        {
            int before = items.Count(i => i != null && !i.IsAir);
            ChestUI.LootAll();
            return new Dictionary<string, object> { ["ok"] = true, ["moved_stacks"] = before - items.Count(i => i != null && !i.IsAir) };
        }
        int moved = 0;
        for (int s = 0; s < items.Length && moved < n; s++)
        {
            Item i = items[s];
            if (i == null || i.IsAir || !string.Equals(i.Name, name, StringComparison.OrdinalIgnoreCase)) continue;
            int want = Math.Min(n - moved, i.stack);
            Item part = i.Clone(); part.stack = want;
            Item left = p.GetItem(p.whoAmI, part, GetItemSettings.LootAllSettingsRegularChest);
            int got = want - (left.IsAir ? 0 : left.stack);
            i.stack -= got; moved += got;
            if (i.stack <= 0) i.TurnToAir();
            if (got < want) break;
        }
        return moved > 0 ? new Dictionary<string, object> { ["ok"] = true, ["moved"] = moved } : No("item not in chest or inventory full");
    }

    static Dictionary<string, object> Put(Player p, string name, int n)
    {
        if (p.chest < 0) return No("no chest open");
        Item[] items = Main.chest[p.chest].item;
        int moved = 0;
        for (int s = 0; s < 50 && moved < n; s++)
        {
            Item src = p.inventory[s];
            if (src.IsAir || src.favorited || !string.Equals(src.Name, name, StringComparison.OrdinalIgnoreCase)) continue;
            for (int c = 0; c < items.Length && !src.IsAir && moved < n; c++)
            {
                Item dst = items[c];
                int room = dst.IsAir ? src.maxStack : dst.type == src.type ? dst.maxStack - dst.stack : 0;
                int move = Math.Min(Math.Min(room, src.stack), n - moved);
                if (move <= 0) continue;
                if (dst.IsAir) { items[c] = src.Clone(); items[c].stack = move; }
                else dst.stack += move;
                src.stack -= move; moved += move;
                if (src.stack <= 0) src.TurnToAir();
            }
        }
        return moved > 0 ? new Dictionary<string, object> { ["ok"] = true, ["moved"] = moved } : No("item not in inventory or chest full");
    }

    static Dictionary<string, object> CloseChest(Player p)
    {
        // Same as pressing Escape / the inventory key with a chest open.
        p.chest = -1;
        Main.playerInventory = false;
        Recipe.FindRecipes();
        return new Dictionary<string, object> { ["ok"] = true };
    }
}

public sealed class BotSystem : ModSystem
{
    public override void OnWorldLoad() { Api.Tick = 0; Server.InWorld = true; Api.Event("world_loaded"); }
    public override void OnWorldUnload() { Server.InWorld = false; Api.Reset(); }

    public override void PostUpdateEverything()
    {
        if (!Server.Enabled || Main.gameMenu || Main.netMode != NetmodeID.SinglePlayer || !Main.LocalPlayer.active) return;
        Api.Update();
    }

    public override void PreUpdatePlayers()
    {
        if (!Server.Enabled || Main.gameMenu || Main.netMode != NetmodeID.SinglePlayer || !Main.LocalPlayer.active) return;
        Api.Drain(Main.LocalPlayer);
    }
}

public sealed class BotPlayer : ModPlayer
{
    public override void SetControls()
    {
        if (Server.Enabled && Player.whoAmI == Main.myPlayer) Api.ApplyControls(Player);
    }

    public override void OnHurt(Player.HurtInfo info)
    {
        if (!Server.Enabled || Player.whoAmI != Main.myPlayer) return;
        int npc = info.DamageSource.SourceNPCIndex;
        Api.Event("hurt", new Dictionary<string, object> { ["damage"] = info.Damage, ["life"] = Player.statLife,
            ["by"] = npc >= 0 && npc < Main.maxNPCs ? Main.npc[npc].TypeName : null });
    }

    public override void Kill(double damage, int hitDirection, bool pvp, PlayerDeathReason damageSource)
    {
        if (!Server.Enabled || Player.whoAmI != Main.myPlayer) return;
        Api.Event("death", new Dictionary<string, object> { ["text"] = damageSource.GetDeathText(Player.name).ToString() });
    }

    public override void OnRespawn()
    {
        if (Server.Enabled && Player.whoAmI == Main.myPlayer) Api.Event("respawn", new Dictionary<string, object> { ["x"] = Player.Center.X / 16f, ["y"] = Player.Center.Y / 16f });
    }
}

public sealed class BotItem : GlobalItem
{
    public override bool OnPickup(Item item, Player player)
    {
        if (Server.Enabled && player.whoAmI == Main.myPlayer)
            Api.Event("pickup", new Dictionary<string, object> { ["item"] = item.Name, ["stack"] = item.stack });
        return true;
    }
}

public sealed class BotNpc : GlobalNPC
{
    public override void OnKill(NPC npc)
    {
        if (Server.Enabled && npc.playerInteraction[Main.myPlayer])
            Api.Event("killed", new Dictionary<string, object> { ["name"] = npc.TypeName, ["x"] = npc.Center.X / 16f, ["y"] = npc.Center.Y / 16f });
    }

    public override void OnSpawn(NPC npc, IEntitySource source)
    {
        // The game announces boss arrivals in chat ("... has awoken!"), so this is visible information.
        if (Server.Enabled && npc.boss) Api.Event("boss_awoke", new Dictionary<string, object> { ["name"] = npc.TypeName });
    }
}

public sealed class BotTile : GlobalTile
{
    public override void KillTile(int i, int j, int type, ref bool fail, ref bool effectOnly, ref bool noItem)
    {
        if (!Server.Enabled || fail || effectOnly || Main.gameMenu) return;
        Player p = Main.LocalPlayer;
        if (p.itemAnimation > 0 && Vector2.Distance(p.Center, new Vector2(i * 16 + 8, j * 16 + 8)) < 20 * 16)
            Api.Event("tile_broken", new Dictionary<string, object> { ["x"] = i, ["y"] = j, ["kind"] = Api.TileName(type) });
    }

    public override void PlaceInWorld(int i, int j, int type, Item item)
    {
        if (Server.Enabled) Api.Event("placed", new Dictionary<string, object> { ["x"] = i, ["y"] = j, ["kind"] = Api.TileName(type), ["item"] = item?.Name });
    }
}
