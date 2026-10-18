from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from terrariabench.experiments import DEFAULT, Ledger, VARIANTS, metrics, target_ready, tools_for, pixel_actions
from tools.analyze_experiments import verify_event_snapshot


class ExperimentTests(unittest.TestCase):
    def test_shutdown_tail_only_accepts_unchanged_heartbeats(self):
        first={'event':'heartbeat','life':100,'inventory':[{'name':'Wood','stack':10}],
               'game_updates':60,'elapsed_seconds':1,'unix_seconds':100,'timestamp_utc':'first'}
        tail=first|{'game_updates':120,'elapsed_seconds':2,'unix_seconds':101,'timestamp_utc':'later'}
        self.assertEqual(verify_event_snapshot([first],[first]),0)
        self.assertEqual(verify_event_snapshot([first],[first,tail]),1)
        with self.assertRaises(AssertionError):verify_event_snapshot([first],[first,tail|{'life':94}])
        with self.assertRaises(AssertionError):verify_event_snapshot([first],[first,tail|{'event':'checkpoint'}])
        with self.assertRaises(AssertionError):verify_event_snapshot([first],[tail])

    def test_normalized_contract_is_declared_and_does_not_mutate_model_output(self):
        config=DEFAULT|VARIANTS['normalized']
        actions=[{'x':1000,'y':500,'ms':100}]
        self.assertEqual(pixel_actions(actions,config),[{'x':1023,'y':512,'ms':100}])
        self.assertEqual(actions[0]['x'],1000)
        with self.assertRaises(ValueError):pixel_actions([{'x':1001,'y':0}],config)
    def test_campaign_reserves_uncertain_cost_across_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger=Ledger(folder,'1')
            ledger.change('failed',reserve=Decimal('.7'))
            with self.assertRaises(RuntimeError):
                ledger.change('other',reserve=Decimal('.4'))
            ledger.change('other',reserve=Decimal('.2'))
            ledger.change('other',charge=Decimal('.1'))
            data=json.loads((Path(folder)/'ledger.json').read_text())
            self.assertEqual(data['pending'],{'failed':'0.7'})
            self.assertEqual(data['spent_usd'],'0.1')

    def test_reservation_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger=Ledger(folder,'1')
            ledger.change('same',reserve=Decimal('.1'))
            with self.assertRaises(RuntimeError):ledger.change('same',reserve=Decimal('.1'))

    def test_inherited_resources_and_npc_only_kill_are_distinct(self):
        events=[{'event':'start','baseline':['wood_1','wood_10','wood_25']},
                {'event':'checkpoint','category':'progress','milestone':'workbench_1','unix_seconds':3},
                {'event':'heartbeat','inventory':[{'name':'Wood','type':9,'stack':40}],
                 'life':100,'hostile_npcs_active':0,'target':{'killed':True,'player_damage':0},'game_updates':120}]
        result=metrics(events,[{'actor':'agent','started_unix':2,'action':{'ms':100}}],60)
        self.assertEqual(result['progress_families'],['workbench_1'])
        self.assertTrue(result['target_killed'])
        self.assertEqual(result['player_damage_to_target'],0)
        self.assertEqual(result['game_updates_during_agent'],60)

    def test_private_state_is_only_exposed_in_declared_variant(self):
        baseline={t['function']['name'] for t in tools_for(DEFAULT)}
        self.assertEqual(baseline,{'look','act'})
        privileged={t['function']['name'] for t in tools_for(DEFAULT|VARIANTS['inventory'])}
        self.assertEqual(privileged,{'look','act','inventory'})

    def test_combat_barrier_waits_for_a_live_spawned_target(self):
        before={'event':'heartbeat','game_updates':60,'target':{'slot':-1,'active':False,'life':0}}
        dead={'event':'heartbeat','game_updates':120,'target':{'slot':4,'active':False,'life':0,'killed':True}}
        live={'event':'heartbeat','game_updates':180,'target':{'slot':4,'active':True,'life':25}}
        self.assertIsNone(target_ready([{'event':'start'},before,dead]))
        self.assertEqual(target_ready([before,live])['game_updates'],180)
