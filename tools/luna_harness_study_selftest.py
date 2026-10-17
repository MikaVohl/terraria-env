"""Entire eight-job supervisor/report pipeline using fake replies; no SSH/API."""
import argparse
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch


def main():
    import luna_harness_study as study
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment-root',type=Path,required=True)
    args=parser.parse_args()
    model={'id':'openai/gpt-6-luna','supported_parameters':['reasoning','structured_outputs'],
           'pricing':{'prompt':'0.0000001','completion':'0.0000005','input_cache_write':'0.000000125'}}
    with tempfile.TemporaryDirectory(prefix='terraria-luna-supervisor-test-') as temporary:
        root=Path(temporary)
        with patch.object(study,'urlopen',return_value=io.BytesIO(json.dumps({'data':[model]}).encode())):
            study.prepare(root,args.environment_root.resolve())
        protocol=study.read(root/'study-protocol.json')
        assert len(protocol['jobs'])==8 and protocol['sum_attempt_guards_usd']==2.8
        # Only synthetic test snapshots: bound to64 native actions total.
        for f in (root/'configs').glob('*.json'):
            c=study.read(f);c.update(max_steps=8,max_calls=2)
            study.write(f,c);protocol['source_sha256'][str(f.relative_to(root))]=study.sha(f)
        study.write(root/'study-protocol.json',protocol)
        def reply(self,payload,timeout):
            assert self._key=='unit-test-only' and payload['model']=='openai/gpt-6-luna'
            n=payload['response_format']['json_schema']['schema']['properties']['actions']['maxItems']
            return {'model':'openai/gpt-6-luna','provider':'fixture','finish_reason':'stop',
                    'text':json.dumps({'actions':[0]*n,'memory':'fixture'}),
                    'usage':{'prompt_tokens':10,'completion_tokens':10,'total_tokens':20,'cost':.0001}}
        with patch('terraria_lite.llm_providers.hermes_key',return_value=('unit-test-only',{'method':'synthetic, no SSH'})), \
             patch('terraria_lite.llm_providers.OpenRouter.call',reply), \
             patch('terraria_lite.llm_providers.post_json',side_effect=AssertionError('No HTTP')):
            study.run(root,True)
        result=study.read(root/'results.json')
        assert study.read(root/'status.json')['stage']=='complete'
        assert len(result['records'])==8 and all(r['steps']==8 for r in result['records'])
        assert set(result['arms'])==set(study.ARMS)
        assert all(v==0 for pairs in result['paired_score_minus_compact16'].values() for v in pairs.values())
        assert result['accounted_cost_usd']<2.8 and result['actual_cost_usd']<.01
        assert all(r['score_at_action_budget']['3000'] is None for r in result['records'])
    print('Eight-job Luna supervisor, independent guards, frozen hashes, threading, verification and paired report passed; no SSH/model API used')


if __name__=='__main__':main()
