"""Prepare/seal completion provenance without touching the stopped cohort.

Only complete trials are reused, by verified copies. Interrupted trials are
excluded and restarted from scratch under explicit user authorization. Frozen
gameplay and learner implementations must be byte-identical to the old cohort.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def source_hashes(root):
    return {str(p.relative_to(root)):sha(p) for folder in ('include','src','python/terraria_lite','tools')
            for p in (root/folder).iterdir() if p.suffix in ('.c','.h','.py','.dylib','.so')}
def artifact_hashes(root):
    return {str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}

def prepare(study,original):
    if (study/'completion-plan.json').exists():raise ValueError('Prepared cohort already exists')
    p=read(original/'study-protocol.json')
    assert not (original/'selected').exists(),'Reserved-test/selection directory exists; audit before completing'
    assert sha(original/'runner.py')==p['supervisor_sha256']
    for v,hashes in p['implementation_sha256'].items():
        assert source_hashes(original/'variants'/v)==hashes,'Original frozen source changed'
        shutil.copytree(original/'variants'/v,study/'variants'/v)
        assert source_hashes(study/'variants'/v)==hashes
    reused=[];interrupted=[];untouched=[];records={}
    for stage in ('calibration','main'):
      for v in ('v4','v5'):
       for method in p['methods']:
        for seed in ([77] if stage=='calibration' else p['training_seeds']):
            name=f'{stage}/{v}/{method}-{seed}';source=original/name
            expected=32768 if stage=='calibration' else p['steps_per_run']
            if (source/'summary.json').exists():
                config=read(source/'protocol.json');summary=read(source/'summary.json');curve=read(source/'curve.json')
                assert summary['steps']==config['actual_steps']==curve[-1]['steps']==expected
                assert config['environment_version']==int(v[1:])
                assert config['config']['seed']==seed and config['config']['total_steps']==expected
                assert config['reserved_test_seeds']==p['reserved_test_seeds']
                assert not config['config']['bootstrap_time_limit'] and not config['demonstrations'] and not config['prerequisite_shaping']
                assert all(sha(Path(config['package'])/k)==h for k,h in config['implementation_sha256'].items())
                for row in curve:
                    assert sorted(x['seed'] for x in row['evaluation']['records'])==list(range(10000001,10000005 if stage=='calibration' else 10000129))
                    assert (source/f"step-{row['steps']}.pt").is_file()
                before=artifact_hashes(source);shutil.copytree(source,study/name)
                assert artifact_hashes(study/name)==before
                records[name]={'original':str(source),'artifact_sha256':before}
                if stage=='main':reused.append(name)
            elif stage=='calibration':raise ValueError('Calibration incomplete')
            elif source.exists():interrupted.append(name)
            else:untouched.append(name)
    assert len(reused)==15 and len(interrupted)==3 and len(untouched)==12
    for name in ('isolated-benchmarks.json','preflight.json'):
        shutil.copy2(original/name,study/name)
    shutil.copy2(original/'runner.py',study/'runner.py')
    plan={'date':'2026-10-12','authorization':'Run the rest of the runs',
        'original_study':str(original),'original_protocol_sha256':sha(original/'study-protocol.json'),
        'original_supervisor_sha256':sha(original/'runner.py'),
        'original_partial_report_sha256':sha(original.parent.parent/'docs/reports/FOOTPRINT_LEARNING_PARTIAL_2026_10.json'),
        'completed_main_runs_reused':sorted(reused),'interrupted_runs_restarted_from_scratch':sorted(interrupted),
        'previously_unstarted_runs':sorted(untouched),'additional_main_runs':15,
        'additional_main_transitions':15*p['steps_per_run'],
        'retained_complete_main_transitions':15*p['steps_per_run'],'final_main_transitions':p['main_transitions'],
        'prior_discarded_partial_transitions_at_verified_checkpoints':12582912,
        'compute_note':'Final 503,316,480 is retained full-trial transitions, not total physical compute: the interrupted old trials also consumed at least 12,582,912 checkpoint-backed transitions, excluded from the final result.',
        'exact_training_resume':False,'warm_start':False,'optimizer_state_restored':False,
        'learner_or_gameplay_changed':False,'predeclared_selection_and_test_rules_changed':False,
        'old_time_cutoff_revoked_by_new_request':True,'new_wall_deadline':None,
        'supervisor_change':'Only skip/revalidate verified completed trial directories; fresh exclusive run-start guard and failure preservation remain.',
        'reused_artifacts':records}
    write(study/'completion-plan.json',plan)
    print(json.dumps({k:v for k,v in plan.items() if k!='reused_artifacts'},indent=2))

def seal(study,original):
    if (study/'study-protocol.json').exists():raise ValueError('Already sealed')
    plan=read(study/'completion-plan.json');p=read(original/'study-protocol.json')
    assert sha(original/'study-protocol.json')==plan['original_protocol_sha256']
    assert sha(original/'runner.py')==plan['original_supervisor_sha256']
    for v,h in p['implementation_sha256'].items():assert source_hashes(study/'variants'/v)==h
    for name,record in plan['reused_artifacts'].items():
        assert artifact_hashes(Path(record['original']))==record['artifact_sha256']
        assert artifact_hashes(study/name)==record['artifact_sha256']
    assert not (study/'selected').exists() and not (original/'selected').exists()
    for name in plan['interrupted_runs_restarted_from_scratch']+plan['previously_unstarted_runs']:assert not (study/name).exists()
    p['study']=str(study);p['completion']=plan;p['supervisor_sha256']=sha(study/'runner.py')
    p['completion_protocol_date']='2026-10-12'
    write(study/'study-protocol.json',p)
    print(json.dumps({'sealed':True,'study':str(study),'additional_runs':15,'additional_transitions':plan['additional_main_transitions'],'supervisor_sha256':p['supervisor_sha256']},indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True)
    p.add_argument('--original',type=Path,required=True);p.add_argument('--mode',choices=['prepare','seal'],required=True)
    a=p.parse_args();{'prepare':prepare,'seal':seal}[a.mode](a.study.resolve(),a.original.resolve())

if __name__=='__main__':main()
