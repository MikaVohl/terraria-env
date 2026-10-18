using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace TerrariaBenchObserver;

// Privileged structured observation for explicitly labeled agent conditions only.
// Reads game state and writes a snapshot file; never changes tiles, entities,
// inventory, input or rules. Disabled unless TERRARIABENCH_STATE_FILE is set.
public static class AgentState
{
    public static string FilePath => Environment.GetEnvironmentVariable("TERRARIABENCH_STATE_FILE");
    public const int Interval = 6; // game updates between snapshots (~10 Hz)

    private static bool Solid(int x, int y)
    {
        if (x < 0 || y < 0 || x >= Main.maxTilesX || y >= Main.maxTilesY) return true;
        Tile t = Main.tile[x, y];
        return t.HasTile && !t.IsActuated && Main.tileSolid[t.TileType] && !Main.tileSolidTop[t.TileType];
    }

    private static bool Standable(int x, int y)
    {
        if (x < 0 || y < 0 || x >= Main.maxTilesX || y >= Main.maxTilesY) return true;
        Tile t = Main.tile[x, y];
        return t.HasTile && !t.IsActuated && (Main.tileSolid[t.TileType] || Main.tileSolidTop[t.TileType]);
    }

    private static bool InToolRange(Player p, Item tool, int tx, int ty)
    {
        // Mirrors the vanilla tool-use range check: tileRange plus the tool's tileBoost.
        int boost = tool?.tileBoost ?? 0;
        return p.position.X / 16f - Player.tileRangeX - boost <= tx
            && (p.position.X + p.width) / 16f + Player.tileRangeX + boost - 1f >= tx
            && p.position.Y / 16f - Player.tileRangeY - boost <= ty
            && (p.position.Y + p.height) / 16f + Player.tileRangeY + boost - 2f >= ty;
    }

    private static (int wall, int drop) Column(int x, int footY)
    {
        // wall: stacked solid tiles from foot level upward; drop: empty tiles below foot level.
        int wall = 0;
        while (wall < 6 && Solid(x, footY - 1 - wall)) wall++;
        int drop = 0;
        while (drop < 10 && !Standable(x, footY + drop)) drop++;
        return (wall, drop);
    }

    public static void Write(Player p, long tick)
    {
        string path = FilePath;
        if (string.IsNullOrWhiteSpace(path)) return;
        Vector2 screen = Main.screenPosition;
        int w = Main.screenWidth, h = Main.screenHeight;
        int px = (int)(p.Center.X / 16f), footY = (int)((p.position.Y + p.height) / 16f);
        (int x, int y) ToScreen(Vector2 world) => ((int)Math.Round(world.X - screen.X), (int)Math.Round(world.Y - screen.Y));
        bool OnScreen((int x, int y) s) => s.x >= 0 && s.y >= 0 && s.x < w && s.y < h;

        var hotbar = Enumerable.Range(0, 10).Select(i => p.inventory[i]).Select((item, i) => new {
            slot = i + 1, key = ((i + 1) % 10).ToString(), name = item.IsAir ? "" : item.Name, stack = item.stack,
            axe = item.axe > 0, pick = item.pick > 0, melee = item.damage > 0 && item.CountsAsClass(DamageClass.Melee)
        }).ToArray();
        Item axe = p.inventory.Take(10).FirstOrDefault(i => i.axe > 0);

        int x0 = Math.Max(1, (int)(screen.X / 16f)), x1 = Math.Min(Main.maxTilesX - 2, (int)((screen.X + w) / 16f));
        int y0 = Math.Max(1, (int)(screen.Y / 16f)), y1 = Math.Min(Main.maxTilesY - 2, (int)((screen.Y + h) / 16f));
        var trees = new List<(int dx, object entry)>();
        for (int x = x0; x <= x1; x++)
            for (int y = y0; y <= y1; y++)
            {
                Tile t = Main.tile[x, y];
                if (!t.HasTile || t.TileType != TileID.Trees) continue;
                Tile below = Main.tile[x, y + 1];
                if (below.HasTile && below.TileType == TileID.Trees) continue; // keep only the lowest trunk tile
                int height = 0;
                while (height < 40 && Main.tile[x, y - height].HasTile && Main.tile[x, y - height].TileType == TileID.Trees) height++;
                if (height < 3) continue; // stumps, roots and saplings
                var s = ToScreen(new Vector2(x * 16 + 8, y * 16 + 8));
                if (!OnScreen(s)) continue;
                trees.Add((x - px, new { sx = s.x, sy = s.y, dx = x - px, dy = y - (footY - 1), height, in_reach = InToolRange(p, axe, x, y) }));
            }

        var hostiles = Main.npc.Where(n => n.active && n.life > 0 && !n.friendly && !n.townNPC && !n.CountsAsACritter
                                         && Math.Abs(n.Center.X - p.Center.X) < 60 * 16 && Math.Abs(n.Center.Y - p.Center.Y) < 40 * 16)
            .OrderBy(n => Vector2.Distance(n.Center, p.Center)).Take(6)
            .Select(n => { var s = ToScreen(n.Center); return new {
                name = n.TypeName, sx = s.x, sy = s.y, on_screen = OnScreen(s), dx = (int)((n.Center.X - p.Center.X) / 16f),
                dy = (int)((n.Center.Y - p.Center.Y) / 16f), life = n.life, life_max = n.lifeMax,
                target = n.GetGlobalNPC<ReferenceNpcPolicy>().DiagnosticTarget }; }).ToArray();

        var items = Main.item.Where(i => i.active && !i.IsAir && Math.Abs(i.Center.X - p.Center.X) < 40 * 16 && Math.Abs(i.Center.Y - p.Center.Y) < 25 * 16)
            .OrderBy(i => Vector2.Distance(i.Center, p.Center)).Take(6)
            .Select(i => { var s = ToScreen(i.Center); return new { name = i.Name, stack = i.stack, sx = s.x, sy = s.y,
                dx = (int)((i.Center.X - p.Center.X) / 16f), dy = (int)((i.Center.Y - p.Center.Y) / 16f) }; }).ToArray();

        int leftX = (int)((p.position.X - 1) / 16f), rightX = (int)((p.position.X + p.width + 1) / 16f);
        var (wallL, dropL) = Column(leftX, footY);
        var (wallR, dropR) = Column(rightX, footY);
        var me = ToScreen(p.Center);
        var snapshot = new {
            schema = "agent-state-v1", tick, unix = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0,
            screen = new { w, h },
            player = new { sx = me.x, sy = me.y, vx = Math.Round(p.velocity.X, 2), vy = Math.Round(p.velocity.Y, 2),
                           on_ground = p.velocity.Y == 0f, facing = p.direction, life = p.statLife, life_max = p.statLifeMax2,
                           dead = p.dead, held_slot = p.selectedItem + 1, held = p.HeldItem.IsAir ? "" : p.HeldItem.Name,
                           inventory_open = Main.playerInventory },
            hotbar, wood = p.inventory.Where(i => i.type == ItemID.Wood).Sum(i => i.stack),
            terrain = new { wall_left = wallL, wall_right = wallR, drop_left = dropL, drop_right = dropR },
            trees = trees.OrderBy(t => Math.Abs(t.dx)).Take(6).Select(t => t.entry).ToArray(),
            hostiles, items
        };
        string tmp = path + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(snapshot));
        File.Move(tmp, path, true);
    }
}
