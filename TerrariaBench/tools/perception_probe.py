"""Small human-annotated screenshot grounding diagnostic; no game interaction."""
import argparse,base64,copy,hashlib,json,sys,time
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from terrariabench.experiments import Ledger,dump
from terrariabench.openrouter import Budget,hermes_key,request


def main():
    p=argparse.ArgumentParser();p.add_argument('--campaign',type=Path,required=True);p.add_argument('--plan',type=Path,required=True)
    a=p.parse_args();plan=json.loads(a.plan.read_text());root=a.campaign/'perception';root.mkdir(exist_ok=False)
    dump(root/'plan.json',plan);ledger=Ledger(a.campaign);key=hermes_key();catalog=request('/models')['data'];results=[]
    for model_id in plan['models']:
        model=next(m for m in catalog if m['id']==model_id);pricing=copy.deepcopy(model['pricing'])
        for override in pricing.get('overrides',[]):
            for k in ('prompt','completion','image','internal_reasoning'):
                if k in override:pricing[k]=str(max(Decimal(pricing.get(k,'0')),Decimal(override[k])))
        for case in plan['cases']:
            name=model_id.split('/')[0]+'-'+case['id'];output=root/name;output.mkdir()
            image=Path(case['image']);data=image.read_bytes();(output/'image.png').write_bytes(data)
            prompt='This is a 1024x1024 Terraria screenshot. Coordinates must be screenshot pixels 0..1023. Return JSON only with player:[x,y] (center of the player character), target:[x,y] ('+case['target_description']+'), and answer:'+case['question']+'.'
            payload={'model':model_id,'messages':[{'role':'user','content':[{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(data).decode()}}]}],
                     'response_format':{'type':'json_object'},'reasoning':{'effort':'low' if model_id.startswith('deepseek/') else 'medium'},'max_tokens':2048,'provider':{'allow_fallbacks':False,'require_parameters':True}}
            saved=copy.deepcopy(payload);saved['messages'][0]['content'][1]['image_url']={'artifact':'image.png','sha256':hashlib.sha256(data).hexdigest()}
            dump(output/'request.json',saved);dump(output/'model.json',model)
            budget=Budget(.1,pricing,input_ceiling=8192,output_ceiling=2048);budget.reserve();ledger.change('perception-'+name,reserve=budget.reservation)
            start=time.monotonic();result={'case':case['id'],'model':model_id}
            try:
                response=request('/chat/completions',key=key,payload=payload,timeout=90);dump(output/'response.json',response)
                usage=response.get('usage')
                try:budget.reconcile(usage)
                finally:
                    if usage and usage.get('cost') is not None:ledger.change('perception-'+name,charge=Budget.decimal(usage['cost']))
                assert response['model']==model_id
                body=json.loads(response['choices'][0]['message']['content'])
                def inside(point,b):return isinstance(point,list) and len(point)==2 and all(type(x) in (int,float) for x in point) and b[0]<=point[0]<=b[2] and b[1]<=point[1]<=b[3]
                result.update(prediction=body,player_in_box=inside(body.get('player'),case['player_box']),target_in_box=inside(body.get('target'),case['target_box']),answer_correct=str(body.get('answer','')).lower() in case['accepted_answers'])
            except Exception as e:result['error']=type(e).__name__+': '+str(e).replace(key,'[redacted]')
            result.update(seconds=time.monotonic()-start,accounting=budget.summary());dump(output/'result-probe.json',result);results.append(result);print(json.dumps(result),flush=True)
            dump(root/'results.json',results)

if __name__=='__main__':main()
