using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace TerrariaBenchObserver;

public sealed class TerrariaBenchObserver : Mod { }

// Observes existing state only. It never accepts agent commands, changes tiles,
// spawns items, writes world/player data, or feeds hidden state to an agent.
public sealed class ProgressObserver : ModSystem
{
    private StreamWriter journal;
    private Stopwatch timer;
    private HashSet<string> seen;
    private string runId;
    private long tick;
    private bool wasDead;
    private bool disabled;

    public override void OnWorldLoad()
    {
        disabled = false;
        tick = 0;
    }

    public override void PostUpdateEverything()
    {
        if (ReferenceMode.Active)
            return;
        if (disabled || Main.gameMenu || Main.netMode != NetmodeID.SinglePlayer)
            return;
        Player player = Main.LocalPlayer;
        if (!player.active)
            return;
        string directory = Environment.GetEnvironmentVariable("TERRARIABENCH_TELEMETRY_DIR");
        if (string.IsNullOrWhiteSpace(directory))
            return;
        try
        {
            var facts = Facts(player).Where(pair => pair.Value).Select(pair => pair.Key).ToHashSet();
            if (journal == null)
            {
                Directory.CreateDirectory(directory);
                runId = Guid.NewGuid().ToString("N");
                journal = new StreamWriter(new FileStream(Path.Combine(directory, runId + ".jsonl"),
                    FileMode.CreateNew, FileAccess.Write, FileShare.Read)) { AutoFlush = true };
                timer = Stopwatch.StartNew();
                seen = facts;
                wasDead = player.dead;
                Emit("session_start", new Dictionary<string, object> {
                    ["catalog"] = "progress-v0.1", ["baseline"] = seen.OrderBy(x => x).ToArray(),
                    ["synthetic"] = false, ["world_id"] = Main.worldID,
                    ["observer_version"] = "0.2", ["net_mode"] = Main.netMode
                });
            }
            else
            {
                tick++;
                foreach (string fact in facts.OrderBy(x => x))
                    if (seen.Add(fact))
                        Emit("checkpoint", new Dictionary<string, object> { ["milestone"] = fact });
                if (player.dead && !wasDead)
                    Emit("death");
                wasDead = player.dead;
                if (tick % 60 == 0)
                    Emit("heartbeat", new Dictionary<string, object> {
                        ["life"] = player.statLife, ["dead"] = player.dead,
                        ["position"] = new float[] { player.position.X, player.position.Y },
                        ["inventory"] = player.inventory.Where(item => !item.IsAir)
                            .Select(item => new { type = item.type, stack = item.stack }).ToArray()
                    });
            }
        }
        catch (Exception error)
        {
            disabled = true;
            journal?.Dispose();
            journal = null;
            Mod.Logger.Error("TerrariaBench telemetry stopped; journal may be incomplete.", error);
        }
    }

    private void Emit(string kind, Dictionary<string, object> extra = null)
    {
        var data = extra ?? new Dictionary<string, object>();
        data["schema"] = 1;
        data["source"] = "TerrariaBenchObserver";
        data["run_id"] = runId;
        data["event"] = kind;
        data["tick"] = tick;
        data["elapsed_seconds"] = timer.Elapsed.TotalSeconds;
        journal.WriteLine(JsonSerializer.Serialize(data));
    }

    public override void OnWorldUnload() => Close();
    public override void Unload() => Close();

    private void Close()
    {
        if (journal == null) return;
        try { Emit("session_end"); }
        catch (Exception error) { Mod.Logger.Error("TerrariaBench journal did not close cleanly.", error); }
        finally { journal.Dispose(); journal = null; }
    }

    private static Dictionary<string, bool> Facts(Player p)
    {
        // Inventory possession is deliberately not described as crafting.
        int Count(params int[] types) => p.inventory.Where(item => types.Contains(item.type)).Sum(item => item.stack);
        return new Dictionary<string, bool> {
            ["wood_25"] = Count(ItemID.Wood) >= 25,
            ["stone_25"] = Count(ItemID.StoneBlock) >= 25,
            ["possess_torch"] = Count(ItemID.Torch) > 0,
            ["possess_workbench"] = Count(ItemID.WorkBench) > 0,
            ["possess_furnace"] = Count(ItemID.Furnace) > 0,
            ["possess_anvil"] = Count(ItemID.IronAnvil, ItemID.LeadAnvil) > 0,
            ["life_upgrade"] = p.statLifeMax > 100,
            ["mana_upgrade"] = p.statManaMax > 20,
            ["king_slime"] = NPC.downedSlimeKing,
            ["eye_of_cthulhu"] = NPC.downedBoss1,
            ["evil_boss"] = NPC.downedBoss2,
            ["queen_bee"] = NPC.downedQueenBee,
            ["skeletron"] = NPC.downedBoss3,
            ["deerclops"] = NPC.downedDeerclops,
            ["wall_of_flesh"] = Main.hardMode,
            ["queen_slime"] = NPC.downedQueenSlime,
            ["destroyer"] = NPC.downedMechBoss1,
            ["twins"] = NPC.downedMechBoss2,
            ["skeletron_prime"] = NPC.downedMechBoss3,
            ["plantera"] = NPC.downedPlantBoss,
            ["golem"] = NPC.downedGolemBoss,
            ["duke_fishron"] = NPC.downedFishron,
            ["empress_of_light"] = NPC.downedEmpressOfLight,
            ["lunatic_cultist"] = NPC.downedAncientCultist,
            ["solar_pillar"] = NPC.downedTowerSolar,
            ["vortex_pillar"] = NPC.downedTowerVortex,
            ["nebula_pillar"] = NPC.downedTowerNebula,
            ["stardust_pillar"] = NPC.downedTowerStardust,
            ["moon_lord"] = NPC.downedMoonlord,
        };
    }
}
