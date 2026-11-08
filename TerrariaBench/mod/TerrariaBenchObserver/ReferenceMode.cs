using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

namespace TerrariaBenchObserver;

// Explicit scenario policy. Disabled entirely for the historical/default mode.
public static class ReferenceMode
{
    public static bool Active => Environment.GetEnvironmentVariable("TERRARIABENCH_PROFILE") == "reference-reconstructed-v1";
    public static bool PveDisabled => Active && Environment.GetEnvironmentVariable("TERRARIABENCH_PVE") != "enabled";
    // Declared variant (observer 0.7): hostiles spawn, fight and drop loot, but cannot hit the player.
    public static bool HostileContactDisabled => Active && Environment.GetEnvironmentVariable("TERRARIABENCH_HOSTILE_DAMAGE") == "off";
    public static int SuppressedNpcs;
    public static int SuppressedProjectiles;
}

public sealed class ReferenceNpcPolicy : GlobalNPC
{
    public override bool InstancePerEntity => true;
    public bool DiagnosticTarget;

    public override void OnSpawn(NPC npc, Terraria.DataStructures.IEntitySource source) => DiagnosticTarget = false;

    public override void OnHitByItem(NPC npc, Player player, Item item, NPC.HitInfo hit, int damageDone)
    {
        // OnKill can precede this callback for a lethal hit. The per-spawn tag
        // includes that hit without attributing later reuse of the NPC slot.
        if (DiagnosticTarget && player.whoAmI == Main.myPlayer)
            ExperimentSetup.PlayerDamage += damageDone;
    }

    public override void OnHitByProjectile(NPC npc, Projectile projectile, NPC.HitInfo hit, int damageDone)
    {
        if (DiagnosticTarget && projectile.owner == Main.myPlayer)
            ExperimentSetup.PlayerDamage += damageDone;
    }

    public override void OnKill(NPC npc)
    {
        if (DiagnosticTarget) ExperimentSetup.TargetKilled = true;
    }

    public override bool PreAI(NPC npc)
    {
        if (ReferenceMode.PveDisabled && !npc.friendly && !npc.townNPC && !npc.CountsAsACritter)
        {
            // Deactivation is scenario setup, not a kill: no loot or defeat flags.
            npc.active = false;
            ReferenceMode.SuppressedNpcs++;
            return false;
        }
        return true;
    }
}

public sealed class ReferenceProjectilePolicy : GlobalProjectile
{
    public override bool PreAI(Projectile projectile)
    {
        if (ReferenceMode.PveDisabled && projectile.hostile)
        {
            projectile.active = false;
            ReferenceMode.SuppressedProjectiles++;
            return false;
        }
        return true;
    }
}

public sealed class ReferenceObserver : ModSystem
{
    private StreamWriter journal;
    private Stopwatch timer;
    private HashSet<string> seen;
    private string runId;
    private long tick;
    private bool disabled, wasDead, probeDone, stateDisabled;

    internal static ReferenceObserver Instance;

    // Extended evidence (observer 0.7): crafts and station placements, never scored by the public subset.
    internal static void Record(string kind, Dictionary<string, object> data)
    {
        var self = Instance;
        if (self == null || self.journal == null || self.disabled || !ReferenceMode.Active) return;
        try { self.Emit(kind, data); }
        catch (Exception error) { self.Mod.Logger.Error("Extended evidence write failed.", error); }
    }

    public override void OnWorldLoad()
    {
        Instance = this;
        tick = 0;
        disabled = false;
        probeDone = stateDisabled = false;
        ReferenceMode.SuppressedNpcs = ReferenceMode.SuppressedProjectiles = 0;
        ExperimentSetup.Reset();
    }

    public override void PostUpdateEverything()
    {
        if (!ReferenceMode.Active || disabled || Main.gameMenu || Main.netMode != NetmodeID.SinglePlayer || !Main.LocalPlayer.active)
            return;
        string directory = Environment.GetEnvironmentVariable("TERRARIABENCH_TELEMETRY_DIR");
        if (string.IsNullOrWhiteSpace(directory)) return;
        try
        {
            Player p = Main.LocalPlayer;
            ExperimentSetup.Update(p);
            var facts = Facts(p).Where(x => x.Value).Select(x => x.Key).ToHashSet();
            if (journal == null)
            {
                bool resetPrefixes = false;
                if (Environment.GetEnvironmentVariable("TERRARIABENCH_REFERENCE_STARTER_PREFIXES") == "plain")
                {
                    int[] starter = { ItemID.CopperShortsword, ItemID.CopperPickaxe, ItemID.CopperAxe };
                    if (p.inventory.Count(item => !item.IsAir) != 3 ||
                        !starter.Select((type, slot) => p.inventory[slot].type == type && p.inventory[slot].stack == 1).All(value => value))
                        throw new InvalidOperationException("Reference prefix setup requires exactly the fresh three starter items.");
                    for (int slot = 0; slot < starter.Length; slot++) p.inventory[slot].SetDefaults(starter[slot]);
                    resetPrefixes = true;
                }
                ExperimentSetup.Apply(p);
                facts = Facts(p).Where(x => x.Value).Select(x => x.Key).ToHashSet();
                Directory.CreateDirectory(directory);
                runId = Guid.NewGuid().ToString("N");
                journal = new StreamWriter(new FileStream(Path.Combine(directory, runId + ".jsonl"), FileMode.CreateNew, FileAccess.Write, FileShare.Read)) { AutoFlush = true };
                timer = Stopwatch.StartNew();
                seen = facts;
                wasDead = p.dead;
                Emit("start", new Dictionary<string, object> {
                    ["baseline"] = seen.OrderBy(x => x).ToArray(), ["catalog"] = "public_reference_manifest_v1",
                    ["world_id"] = Main.worldID, ["hostile_mobs_enabled"] = !ReferenceMode.PveDisabled,
                    ["pve_enabled"] = !ReferenceMode.PveDisabled, ["observer_version"] = "0.7",
                    ["hostile_contact_damage"] = !ReferenceMode.HostileContactDisabled,
                    ["scenario"] = ExperimentSetup.Scenario,
                    ["trusted_setup"] = ExperimentSetup.Scenario != "fresh",
                    ["starter_prefixes_reset"] = resetPrefixes
                });
                Diagnostic("held_weapon", p.HeldItem.damage > 0);
            }
            else
            {
                tick++;
                foreach (string fact in facts.OrderBy(x => x))
                    if (seen.Add(fact))
                        Emit("checkpoint", new Dictionary<string, object> { ["milestone"] = fact, ["category"] = "progress" });
                Diagnostic("held_weapon", p.HeldItem.damage > 0);
                Diagnostic("held_axe", p.HeldItem.axe > 0);
                Diagnostic("held_pickaxe", p.HeldItem.pick > 0);
                Diagnostic("inventory_opened", Main.playerInventory);
                if (p.dead && !wasDead) Emit("death");
                wasDead = p.dead;
                if (tick % 60 == 0)
                    Emit("heartbeat", new Dictionary<string, object> {
                        ["life"] = p.statLife, ["dead"] = p.dead,
                        ["position"] = new float[] { p.position.X, p.position.Y },
                        ["inventory"] = p.inventory.Select((item, slot) => new { item, slot }).Where(entry => !entry.item.IsAir).Select(entry => new { type = entry.item.type, stack = entry.item.stack, name = entry.item.Name, slot = entry.slot }).ToArray(),
                        ["target"] = ExperimentSetup.TargetState(),
                        ["damage_received"] = ExperimentSetup.DamageReceived,
                        ["hits_received"] = ExperimentSetup.HitsReceived,
                        ["hostile_npcs_active"] = Main.npc.Count(n => n.active && !n.friendly && !n.townNPC && !n.CountsAsACritter),
                        ["hostile_projectiles_active"] = Main.projectile.Count(projectile => projectile.active && projectile.hostile),
                        ["suppressed_npcs"] = ReferenceMode.SuppressedNpcs,
                        ["suppressed_projectiles"] = ReferenceMode.SuppressedProjectiles
                    });
                if (tick % AgentState.Interval == 0 && !stateDisabled)
                {
                    // A state-writer fault must not end the scoring journal.
                    try { AgentState.Write(p, tick); }
                    catch (Exception error) { stateDisabled = true; Emit("agent_state_failed"); Mod.Logger.Error("Agent state output stopped.", error); }
                }
                // A plumbing-only test probe. Never enabled for model evaluations.
                if (!probeDone && tick >= 120 &&
                    Environment.GetEnvironmentVariable("TERRARIABENCH_CALIBRATION_ONLY") == "1" &&
                    Environment.GetEnvironmentVariable("TERRARIABENCH_TEST_PVE") == "1")
                {
                    probeDone = true;
                    NPC.NewNPC(new Terraria.DataStructures.EntitySource_Misc("TerrariaBench calibration probe"),
                        (int)p.position.X + 100, (int)p.position.Y, NPCID.BlueSlime);
                    Emit("calibration_probe", new Dictionary<string, object> { ["type"] = "hostile_NPC_suppression" });
                }
            }
        }
        catch (Exception error)
        {
            disabled = true;
            journal?.Dispose(); journal = null;
            Mod.Logger.Error("Reference telemetry stopped; evidence is incomplete.", error);
        }
    }

    private void Diagnostic(string name, bool condition)
    {
        if (condition && seen.Add(name))
            Emit("checkpoint", new Dictionary<string, object> { ["milestone"] = name, ["category"] = "non_scoring" });
    }

    private void Emit(string kind, Dictionary<string, object> extra = null)
    {
        var data = extra ?? new Dictionary<string, object>();
        data["schema"] = 1; data["profile"] = "reference-reconstructed-v1";
        data["source"] = "TerrariaBenchReferenceObserver"; data["run_id"] = runId;
        data["event"] = kind; data["task"] = "open_ended";
        data["game_updates"] = tick; data["elapsed_seconds"] = timer.Elapsed.TotalSeconds;
        data["unix_seconds"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
        data["timestamp_utc"] = DateTimeOffset.UtcNow.ToString("O");
        journal.WriteLine(JsonSerializer.Serialize(data));
        if ((kind == "start" || kind == "checkpoint") && Environment.GetEnvironmentVariable("TERRARIABENCH_CHECKPOINT_CHAT") != "disabled")
        {
            string message = "TERRARIABENCH_CHECKPOINT " + (kind == "start" ? "start task=open_ended" : "checkpoint task=open_ended milestone=" + data["milestone"]);
            Main.NewText(message, 100, 255, 100);
            if (kind == "checkpoint") Main.NewText("elapsed_ticks=" + tick, 100, 255, 100);
        }
    }

    public override void OnWorldUnload() => Close();
    public override void Unload() => Close();
    private void Close()
    {
        if (journal == null) return;
        try { Emit("end"); }
        catch (Exception error) { Mod.Logger.Error("Reference journal close failed.", error); }
        finally { journal.Dispose(); journal = null; }
    }

    private static Dictionary<string, bool> Facts(Player p)
    {
        int Count(params int[] types) => p.inventory.Where(item => types.Contains(item.type)).Sum(item => item.stack);
        int wood = Count(ItemID.Wood);
        return new Dictionary<string, bool> {
            ["wood_1"] = wood >= 1, ["wood_10"] = wood >= 10,
            ["wood_25"] = wood >= 25, ["wood_100"] = wood >= 100,
            ["workbench_1"] = Count(ItemID.WorkBench) >= 1,
            ["torch_10"] = Count(ItemID.Torch) >= 10,
            ["furnace_1"] = Count(ItemID.Furnace) >= 1,
            ["early_bar_5"] = Count(ItemID.CopperBar, ItemID.TinBar, ItemID.IronBar, ItemID.LeadBar, ItemID.SilverBar, ItemID.TungstenBar, ItemID.GoldBar, ItemID.PlatinumBar) >= 5,
            ["max_life_160"] = p.statLifeMax >= 160,
            ["biome_jungle"] = p.ZoneJungle,
            ["boss_eye_of_cthulhu_defeated"] = NPC.downedBoss1,
            ["biome_underworld"] = p.ZoneUnderworldHeight,
            ["boss_wall_of_flesh_defeated"] = Main.hardMode,
        };
    }
}

// Trusted initial conditions for explicitly labeled diagnostic tasks only.
// Applied before baseline/timer; never exposed as an agent action or campaign credit.
public static class ExperimentSetup
{
    public static string Scenario => Environment.GetEnvironmentVariable("TERRARIABENCH_SCENARIO") ?? "fresh";
    public static int TargetSlot = -1, PlayerDamage, DamageReceived, HitsReceived;
    public static bool TargetKilled;
    public static void Reset() { TargetSlot = -1; PlayerDamage = DamageReceived = HitsReceived = 0; TargetKilled = false; }
    public static void Apply(Player player)
    {
        if (Scenario == "crafting")
        {
            int[] types = { ItemID.Wood, ItemID.StoneBlock, ItemID.Gel };
            int[] amounts = { 50, 50, 5 };
            for (int i = 0; i < types.Length; i++)
            { player.inventory[i+3].SetDefaults(types[i]); player.inventory[i+3].stack = amounts[i]; }
        }
        else if (Scenario == "slime")
        {
            // Keep the Guide from solving this isolated encounter for the agent.
            // This is a declared scenario setup, not the natural fresh-world track.
            foreach (NPC npc in Main.npc) if (npc.active && npc.type == NPCID.Guide) npc.active = false;
        }
        else if (Scenario != "fresh") throw new InvalidOperationException("Unknown diagnostic scenario");
    }
    public static void Update(Player player)
    {
        string armFile = Environment.GetEnvironmentVariable("TERRARIABENCH_SCENARIO_ARM");
        if (Scenario == "slime" && TargetSlot < 0 && !string.IsNullOrEmpty(armFile) && File.Exists(armFile))
        {
            int slot = NPC.NewNPC(new Terraria.DataStructures.EntitySource_Misc("TerrariaBench diagnostic scenario"),
                (int)player.Center.X + 160, (int)player.Bottom.Y - 16, NPCID.BlueSlime);
            if (slot >= 0 && slot < Main.maxNPCs)
            {
                TargetSlot = slot;
                Main.npc[slot].GetGlobalNPC<ReferenceNpcPolicy>().DiagnosticTarget = true;
            }
        }
    }
    public static object TargetState()
    {
        NPC target = TargetSlot >= 0 && TargetSlot < Main.maxNPCs ? Main.npc[TargetSlot] : null;
        return new { slot = TargetSlot, active = !TargetKilled && (target?.active ?? false), type = target?.type ?? 0,
                     life = TargetKilled ? 0 : target?.life ?? 0, killed = TargetKilled, player_damage = PlayerDamage };
    }
}

public sealed class ReferenceDamageObserver : ModPlayer
{
    public override void OnHurt(Player.HurtInfo info)
    {
        if (ReferenceMode.Active && Player.whoAmI == Main.myPlayer)
        { ExperimentSetup.DamageReceived += info.Damage; ExperimentSetup.HitsReceived++; }
    }

    public override bool CanBeHitByNPC(NPC npc, ref int cooldownSlot) => !ReferenceMode.HostileContactDisabled;

    public override bool CanBeHitByProjectile(Projectile proj) => !(ReferenceMode.HostileContactDisabled && proj.hostile);
}

public sealed class ReferenceCraftObserver : GlobalItem
{
    public override void OnCreated(Item item, ItemCreationContext context)
    {
        if (context is RecipeItemCreationContext)
            ReferenceObserver.Record("crafted", new Dictionary<string, object> {
                ["item_type"] = item.type, ["stack"] = item.stack, ["name"] = item.Name });
    }
}

public sealed class ReferencePlacementObserver : GlobalTile
{
    // Stations, light, furniture and storage; ordinary blocks and walls are not journaled.
    private static readonly HashSet<int> Journaled = new() {
        TileID.Torches, TileID.ClosedDoor, TileID.Tables, TileID.Chairs, TileID.Containers, TileID.Bottles,
        TileID.Anvils, TileID.Furnaces, TileID.WorkBenches, TileID.Hellforge, TileID.Loom, TileID.Sawmill,
        TileID.Campfire, TileID.Beds, TileID.CookingPots, TileID.TinkerersWorkbench, TileID.MythrilAnvil };

    public override void PlaceInWorld(int i, int j, int type, Item item)
    {
        if (Journaled.Contains(type))
            ReferenceObserver.Record("placed", new Dictionary<string, object> {
                ["tile_type"] = type, ["tile"] = new[] { i, j }, ["item_type"] = item?.type ?? 0 });
    }
}
