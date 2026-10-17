"""Small reporting/claim regression tests; never evaluates reserved worlds."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import numpy as np

def module(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    diagnostic=module('crafting_diagnostics');study=module('footprint_study');reserved=module('evaluate_reserved')
    rows=np.zeros((16,18),np.int32)
    for code,row in enumerate(rows):row[0]=4 if code&1 else 3;row[1]=20 if code&2 else 19;row[2]=3 if code&4 else 2;row[6]=bool(code&8)
    assert np.array_equal(diagnostic.gate_code(rows),np.arange(16))
    assert study.interval([0,0,0,0,0])['paired_t_95_interval']==[0,0]
    assert study.interval([-2,-1,0,1,2])['mean']==0
    with tempfile.TemporaryDirectory(prefix='terraria-claim-test-') as directory:
        d=Path(directory);checkpoint=d/'fake.pt';checkpoint.write_bytes(b'fixture, not a policy')
        out=d/'fake-result.json'
        argv=['evaluate_reserved',str(checkpoint),'--out',str(out),'--seed-start','123','--version',str(reserved.SPEC.version)]
        with patch.object(sys,'argv',argv),patch.object(reserved,'load_agent',return_value=None),patch.object(reserved,'evaluate',return_value={'mean_achievements':0,'death_rate':0}) as evaluate:
            reserved.main();assert evaluate.call_count==1
            try:reserved.main()
            except ValueError:pass
            else:raise AssertionError('Consumed output was not protected')
            assert evaluate.call_count==1
        out2=d/'interrupted.json';out2.with_suffix('.claim.json').write_text(json.dumps({'fixture':True}))
        argv[argv.index('--out')+1]=str(out2)
        with patch.object(sys,'argv',argv),patch.object(reserved,'evaluate') as evaluate:
            try:reserved.main()
            except FileExistsError:pass
            else:raise AssertionError('Ambiguous claim was not protected')
            assert evaluate.call_count==0
    print('All 16 diagnostic gate codes, paired reporting intervals, consumed and interrupted test guards passed. No real policy or reserved world evaluated.')

if __name__=='__main__':main()
