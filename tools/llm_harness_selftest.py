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
    from terraria_lite.llm_bench import config, parse_response, run, verify, read_journal, score
    from terraria_lite.llm_providers import OpenRouter, ProviderError
    c = config({"max_steps": 8, "max_calls": 8, "max_actions_per_call": 2})
    for raw in ({"max_calls": True}, {"seeds": [True]}, {"seeds": [19000001]}, {"seeds": [17000001]}, {"unexpected": 1}):
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
        # A modified journal cannot silently pass replay verification.
        journal.write_text(journal.read_text().replace('"seed":31000001','"seed":31000009',1))
        try: verify(output,root)
        except AssertionError: pass
        else: raise AssertionError('Tampered transcript accepted')
    print(f'v{SPEC.version} LLM harness passed: exact inventory decoding, strict batches, budgets, frozen provenance, exclusive claims, mocked high reasoning, accounting, no retries/secret logs and transition/tape verification; no APIs/SSH used')


if __name__ == '__main__':
    main()
