"""Reporting-only audit of an existing eight-attempt study. No API/SSH calls."""
import argparse
import collections
import importlib.util
import json
import math
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();root=args.study.resolve()
    spec=importlib.util.spec_from_file_location('frozen_luna_supervisor',root/'supervisor.py')
    study=importlib.util.module_from_spec(spec);spec.loader.exec_module(study)
    protocol=study.read(root/'study-protocol.json');envroot=Path(protocol['environment_root'])
    harness=study.load_harness(root,envroot);study.verify_sources(root,protocol,harness)
    launch=study.read(root/'launch.json');started=study.read(root/'started.json');status=study.read(root/'status.json')
    assert launch['pid']==started['pid']==status['pid']==9446
    assert study.sha(root/'study-protocol.json')==launch['protocol_sha256']==started['protocol_sha256']
    assert status['stage']=='complete' and not status['active'] and not status['pending'] and not status['failure']
    process=subprocess.run(['ps','-p','9446,9447','-o','command='],capture_output=True,text=True)
    assert process.returncode!=0,'Original run/inhibitor PID still present; check exact identity before proceeding'
    results=study.read(root/'results.json');assert len(results['records'])==len(protocol['jobs'])==8
    assert protocol['seeds']==[32000001,32000002] and protocol['sum_attempt_guards_usd']==2.8
    expected={(a,s) for a in protocol['arms'] for s in protocol['seeds']}
    assert {(r['arm'],r['seed']) for r in results['records']}==expected
    total=collections.Counter();finishes=collections.Counter();providers=collections.Counter();audited=[]
    arm_totals={a:collections.Counter() for a in protocol['arms']}
    for job,record in zip(protocol['jobs'],results['records']):
        out=root/'runs'/job['name'];cfg=study.read(root/'configs'/(job['name']+'.json'))
        manifest=study.read(out/'manifest.json');assert manifest['config']==cfg
        assert cfg['seeds']==[job['seed']] and cfg['max_cost_usd_total']==.35
        assert cfg['model']=='openai/gpt-6-luna' and cfg['reasoning_effort']=='high'
        for k,v in protocol['arms'][job['arm']].items():assert cfg[k]==v
        assert cfg['max_steps']==3000 and cfg['max_calls']==1000 and cfg['replicates']==1
        assert harness.verify(out,envroot)['verified_episodes']==1
        assert study.metrics(root,job,harness,envroot)==record
        directory=out/f"world-{job['seed']}-rep-0";rows=harness.read_journal(directory/'events.jsonl')
        responses=[r for r in rows if r['event']=='response_received']
        requests=[r for r in rows if r['event']=='request_started']
        assert len(requests)==len(responses)==record['calls']
        charged=reported=0.;usage=collections.Counter();current=None;chosen=None;executed=[];interruptions=discarded=0
        for row in rows:
            if row['event']=='request_started':
                current=row;payload=row['payload']
                assert payload['model']=='openai/gpt-6-luna' and payload['reasoning']=={'effort':'high','exclude':True}
                assert not payload['provider']['allow_fallbacks'] and payload['provider']['require_parameters']
                assert charged+row['reserved_cost_usd']<=.35+1e-9
            elif row['event']=='response_received':
                reply=row['response'];u=reply['usage']
                assert reply['model']=='openai/gpt-6-luna' and u['total_tokens']==u['prompt_tokens']+u['completion_tokens']
                assert u['prompt_tokens']<=current['input_token_bound'] and u['completion_tokens']<=cfg['max_output_tokens']
                expected_charge=max(u['prompt_tokens']*cfg['input_usd_per_token_ceiling']+u['completion_tokens']*cfg['output_usd_per_token_ceiling'],u['cost'])
                assert math.isclose(expected_charge,row['accounted_cost_usd'],abs_tol=1e-12)
                assert row['accounted_cost_usd']<=current['reserved_cost_usd']+1e-9
                charged+=row['accounted_cost_usd'];reported+=u['cost']
                for k in ('prompt_tokens','completion_tokens','total_tokens'):usage[k]+=u[k]
                usage['reasoning_tokens_in_completion']+=(u.get('completion_tokens_details') or {}).get('reasoning_tokens',0) or 0
                finishes[reply['finish_reason']]+=1;providers[reply.get('provider')]+=1
                chosen,_,valid=harness.parse_response(reply['text'],cfg)
                if reply['finish_reason'] not in ('stop','tool_calls'):chosen=[None]
                executed=[]
            elif row['event']=='step':
                executed.append(row['action']);assert executed==chosen[:len(executed)]
            elif row['event']=='batch_interrupted':
                assert cfg['batch_interrupt']=='illegal' and row['reason']=='illegal_attempt_after_paid_tick'
                assert row['discarded_actions']==len(chosen)-len(executed)
                interruptions+=1;discarded+=row['discarded_actions']
            elif row['event']=='batch_end':
                assert row['submitted_actions']==len(chosen) and row['executed_actions']==len(executed)
                assert math.isclose(row['accounted_cost_usd'],charged,abs_tol=1e-12)
        assert interruptions==record['interrupted_batches'] and discarded==record['discarded_actions']
        assert math.isclose(charged,record['accounted_cost_usd'],abs_tol=1e-12) and charged<=.35
        assert math.isclose(reported,record['provider_reported_cost_usd'],abs_tol=1e-12)
        assert usage['total_tokens']==record['tokens']
        tape=directory/'actions.tape'
        text=subprocess.check_output([str(envroot/'terraria-px'),'--watch',str(tape),'--verify'],text=True)
        native=json.loads(text.splitlines()[-1]);info=record['native_info']
        assert all(native[k]==info[k] for k in ('steps','health','achievement_mask','episode_return'))
        assert native['environment_version']==7 and native['achievement_mask'].bit_count()==record['score']
        values={**usage,'calls':record['calls'],'steps':record['steps'],'illegal_attempts':record['illegal_attempts'],
                'invalid_requests':record['invalid_requests'],'discarded_actions':discarded,'interrupted_batches':interruptions,
                'provider_reported_cost_usd':reported,'accounted_cost_usd':charged}
        total.update(values);arm_totals[job['arm']].update(values)
        audited.append({**job,'score':record['score'],'steps':record['steps'],'calls':record['calls'],'stop':record['status'],
                        'native_SDL_verified':native,'first_achievement_steps':record['first_achievement_steps'],
                        'score_at_action_budget':record['score_at_action_budget'],'usage':dict(usage),
                        'accounted_cost_usd':charged,'provider_reported_cost_usd':reported,
                        'events_sha256':study.sha(directory/'events.jsonl'),'tape_sha256':study.sha(tape)})
    assert math.isclose(total['provider_reported_cost_usd'],results['actual_cost_usd'],abs_tol=1e-12)
    assert math.isclose(total['accounted_cost_usd'],results['accounted_cost_usd'],abs_tol=1e-12)
    assert total['accounted_cost_usd']<=2.8 and total['provider_reported_cost_usd']<3
    for arm,value in results['arms'].items():
        rows=[r for r in results['records'] if r['arm']==arm]
        assert [r['score'] for r in rows]==value['scores']
        assert sum(r['score'] for r in rows)/2==value['mean_score']
        assert sum(r['died'] for r in rows)==value['deaths']
        for k,name in [('bench_worlds','craft workbench'),('furnace_worlds','craft furnace'),('anvil_worlds','craft anvil')]:assert value[k]==sum(name in r['achievements'] for r in rows)
    actual_pairs={a:{str(s):next(r['score'] for r in results['records'] if r['arm']==a and r['seed']==s)-next(r['score'] for r in results['records'] if r['arm']=='compact16' and r['seed']==s) for s in protocol['seeds']} for a in protocol['arms'] if a!='compact16'}
    assert actual_pairs==results['paired_score_minus_compact16']
    study.verify_sources(root,protocol,harness)
    result={'study_root':str(root),'protocol_sha256':study.sha(root/'study-protocol.json'),
            'results_sha256':study.sha(root/'results.json'),'completed_attempts':8,'model':'openai/gpt-6-luna',
            'reasoning_effort_requested':'high','model_and_high_request_matches':total['calls'],
            'source_config_catalog_native_hashes_verified':True,'all_python_request_transition_replays_verified':True,
            'all_SDL_replays_verified':True,'all_claims_unique_and_manifest_matched':True,
            'guard_reservations_usage_and_tails_verified':True,'no_automatic_retries_or_replacements':True,
            'api_calls_during_audit':0,'original_runner_and_inhibitor_absent':True,'PPO_reserved_or_validation_worlds_used':False,
            'totals':dict(total),'finish_reasons':dict(finishes),'providers':dict(providers),
            'arms':results['arms'],'arm_totals':{a:dict(v) for a,v in arm_totals.items()},
            'paired_score_minus_compact16':actual_pairs,'attempts':audited,
            'interpretation':'Two-world exploratory dollar-guard comparison. Three alive cost-censored attempts; no full3000-action episode. Death is absorbing, censoring is null. No reliable significance/ranking or equal-prior PPO claim.'}
    study.write(args.out,result,exclusive=True)
    print(json.dumps({'totals':dict(total),'finish_reasons':dict(finishes),'providers':dict(providers),
                      'arm_totals':{a:dict(v) for a,v in arm_totals.items()}},indent=2))


if __name__=='__main__':main()
