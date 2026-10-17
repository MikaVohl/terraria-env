"""Offline harness/provider tests. No SSH, credentials, HTTP or model inference."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.environment_root.resolve()
    os.environ["TERRARIA_LITE_LIB"] = str(root / "python/terraria_lite/libterraria.dylib")
    import numpy as np
    from terraria_lite import SPEC
    from terraria_lite.llm_protocol import Session, canonical
    from terraria_lite.llm_bench import config, parse_response, run, verify, read_journal, score, model_observation, prompt
    from terraria_lite.llm_providers import OpenRouter, ProviderError
    c = config({"max_steps": 8, "max_calls": 8, "max_actions_per_call": 2})
    for raw in ({"max_calls": True}, {"seeds": [True]}, {"seeds": [19000001]}, {"seeds": [17000001]}, {"unexpected": 1},
                {"observation_format":"oracle"}, {"batch_interrupt":"strategy"}):
        try: config(raw)
        except (ValueError, TypeError): pass
        else: raise AssertionError("Invalid config accepted")
    for raw in ('{}', '{"actions":[true],"memory":""}', '{"actions":[0,999],"memory":""}',
                '{"actions":[0,1,2],"memory":""}', '```json\n{}\n```', '__import__("os").system("bad")'):
        assert parse_response(raw, c) == ([None], "", False)
    assert parse_response('{"actions":[0,1],"memory":"note"}', c) == ([0,1], "note", True)
    session = Session(9, 8, root)
    try:
        offset = SPEC.cells*(SPEC.tile_kinds+1) + SPEC.status_inv0
        original = session.obs.copy()
        for count in (0,1,4,10,20,101,999):
            session.obs[offset] = np.sqrt(np.float32(count/999))
            assert session.packet()["inventory"][SPEC.item_names[0]] == count
        session.obs[:] = original
        packet=session.packet(); compact=model_observation(packet,config({'observation_format':'compact'}))
        assert 'status' not in compact and compact['selected_placeable_one_hot']==packet['status'][17:SPEC.status_inv0]
        assert {k:v for k,v in compact.items() if k!='selected_placeable_one_hot'}=={k:v for k,v in packet.items() if k!='status'}
        # Reconstruct the compact status prefix, including exact native inventory float32 encoding.
        rebuilt=np.zeros(SPEC.status_entity0,dtype=np.float32)
        rebuilt[:17]=list(compact['scalars'].values());rebuilt[17:SPEC.status_inv0]=compact['selected_placeable_one_hot']
        for i,name in enumerate(SPEC.item_names):rebuilt[SPEC.status_inv0+i]=np.sqrt(np.float32(compact['inventory'][name]/999))
        for i,name in enumerate(SPEC.achievement_names):rebuilt[SPEC.status_ach0+i]=name in compact['achievements']
        np.testing.assert_array_equal(rebuilt,np.array(packet['status'],dtype=np.float32))
    finally: session.close()
    api = config({"provider":"openrouter", "model":"openai/gpt-6.1-sol", "max_steps":8, "max_calls":8,
                  "max_actions_per_call":2,"max_cost_usd_total":2,
                  "input_usd_per_token_ceiling":.000005,"output_usd_per_token_ceiling":.000015,
                  "pricing_source":"synthetic test ceilings, not billing rates"})
    seen = []
    def transport(payload, key, timeout):
        seen.append(payload)
        assert key == 'unit-test-only' and timeout > 0
        return {"id":"fixture", "model":"openai/gpt-6.1-sol", "provider":"fixture",
                "choices":[{"message":{"content":canonical({"actions":[0,0],"memory":"my notes"}),
                                        "reasoning":"private: must not be logged"},"finish_reason":"stop"}],
                "usage":{"prompt_tokens":10,"completion_tokens":10,"total_tokens":20,"cost":.0001}}
    with tempfile.TemporaryDirectory(prefix="terraria-llm-harness-test-") as temporary:
        base = Path(temporary)
        # Socket/API path is forbidden for all offline smoke tests.
        with patch('terraria_lite.llm_providers.post_json', side_effect=AssertionError('No HTTP allowed')):
            output = base/'random'
            report = run({"seeds":[31000001,31000002],"replicates":2,"max_steps":8,"max_calls":8}, root, output)
            assert report["complete"] and report["recorded_episodes"] == 4
            assert verify(output, root)["verified_episodes"] == 4
            try: run({},root,output)
            except FileExistsError: pass
            else: raise AssertionError('Existing run overwritten')
            try: run(api,root,base/'forbidden')
            except ValueError: pass
            else: raise AssertionError('Paid run without opt-in accepted')
        assert not (base/'forbidden').exists()
        for name, override, expected in (
            ('cost', {'max_cost_usd_total': 1e-9}, 'cost_budget'),
            ('tokens', {'max_total_tokens_per_episode': 1}, 'token_budget'),
            ('context', {'max_context_bytes': 1}, 'context_budget')):
            def forbidden(*args): raise AssertionError('Budget guard permitted an HTTP call')
            cfg = {**api, **override}
            guarded = run(cfg, root, base/name, allow_api=True,
                          provider=OpenRouter(cfg,key='unit-test-only',transport=forbidden))
            assert guarded['episodes'][0]['status'] == expected
            assert guarded['episodes'][0]['calls'] == guarded['episodes'][0]['steps'] == 0
        output = base/'mock-provider'
        adapter = OpenRouter(api, key='unit-test-only', transport=transport)
        report = run(api,root,output,allow_api=True,provider=adapter)
        assert report["complete"] and report["episodes"][0]["steps"] == 8 and report["episodes"][0]["calls"] == 4
        assert verify(output,root)["verified_episodes"] == 1
        assert seen[0]["reasoning"] == {"effort":"high","exclude":True}
        assert seen[0]["model"] == 'openai/gpt-6.1-sol'
        assert not seen[0]["provider"]["allow_fallbacks"]
        journal = next(output.glob('world-*/events.jsonl'))
        assert 'unit-test-only' not in journal.read_text() and 'private: must not be logged' not in journal.read_text()
        rows=read_journal(journal);assert len([r for r in rows if r['event']=='step'])==8
        # Ambiguous provider failure: counted once, stops the run, never retries.
        def fail(*args): raise ProviderError('fixture failure')
        failed = run({**api,"seeds":[31000001,31000002]},root,base/'failed',allow_api=True,
                     provider=OpenRouter(api,key='unit-test-only',transport=fail))
        assert not failed["complete"] and failed["charge_uncertain"] and failed["episodes"][0]["calls"]==1
        assert failed["recorded_episodes"]==1 and failed["scoreable_episodes"]==0
        assert score([],1)["mean_achievements"] is None
        def truncated(payload,key,timeout):
            raw = transport(payload,key,timeout)
            raw['choices'][0]['finish_reason'] = 'length'
            return raw
        limited = {**api,'max_calls':2}
        stopped = run(limited,root,base/'length',allow_api=True,
                      provider=OpenRouter(limited,key='unit-test-only',transport=truncated))
        assert stopped['episodes'][0]['status']=='call_budget'
        assert stopped['episodes'][0]['steps']==stopped['episodes'][0]['invalid_requests']==2
        assert verify(base/'length',root)['verified_episodes']==1
        # Illegal action is actually attempted (one paid tick), then remaining list discarded.
        check=Session(31000001,8,root)
        try: illegal=int(np.flatnonzero(check.env.action_mask()==0)[0])
        finally:check.close()
        def illegal_list(payload,key,timeout):
            raw=transport(payload,key,timeout)
            raw['choices'][0]['message']['content']=canonical({'actions':[illegal,0],'memory':''})
            return raw
        for policy,expected_steps in [('never',2),('illegal',1)]:
            cfg={**api,'max_calls':1,'batch_interrupt':policy,'observation_format':'compact','history_turns':2}
            out=base/('interrupt-'+policy)
            result=run(cfg,root,out,allow_api=True,provider=OpenRouter(cfg,key='unit-test-only',transport=illegal_list))['episodes'][0]
            assert result['steps']==expected_steps and result['illegal_attempts']==1
            assert result['discarded_actions']==(policy=='illegal')
            assert verify(out,root)['verified_episodes']==1
            assert 'redundant flat status' in seen[-1]['messages'][0]['content']
            assert 'status' not in json.loads(seen[-1]['messages'][-1]['content'])['observation']
        def substituted(payload,key,timeout):
            raw=transport(payload,key,timeout);raw['model']='another/model';return raw
        try: OpenRouter(api,key='unit-test-only',transport=substituted).call({},1)
        except ProviderError: pass
        else: raise AssertionError('Silent model substitution accepted')
        # A modified journal cannot silently pass replay verification.
        journal.write_text(journal.read_text().replace('"seed":31000001','"seed":31000009',1))
        try: verify(output,root)
        except AssertionError: pass
        else: raise AssertionError('Tampered transcript accepted')
    print(f'v{SPEC.version} LLM harness passed: exact inventory decoding, strict batches, budgets, frozen provenance, exclusive claims, mocked high reasoning, accounting, no retries/secret logs and transition/tape verification; no APIs/SSH used')


if __name__ == '__main__':
    main()
