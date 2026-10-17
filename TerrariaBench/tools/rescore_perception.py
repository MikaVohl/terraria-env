"""Offline semantic rescoring with optional code-fence removal; raw records untouched."""
import argparse,json,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();plan=json.loads((a.root/'plan.json').read_text());cases={c['id']:c for c in plan['cases']};rows=[]
for path in sorted(a.root.glob('*/result-probe.json')):
    raw=json.loads(path.read_text());row={k:raw[k] for k in ('case','model','accounting')};case=cases[row['case']]
    response_path=path.parent/'response.json'
    if not response_path.exists():row['status']='transport_failure';rows.append(row);continue
    response=json.loads(response_path.read_text());text=response['choices'][0]['message'].get('content') or ''
    row['finish_reason']=response['choices'][0].get('finish_reason')
    row['raw_json_valid']=True
    try:body=json.loads(text)
    except json.JSONDecodeError:
        row['raw_json_valid']=False
        try:body=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip(),flags=re.I))
        except json.JSONDecodeError:row['status']='unparseable';rows.append(row);continue
    def inside(pt,box):return isinstance(pt,list) and len(pt)==2 and all(type(v) in (int,float) for v in pt) and box[0]<=pt[0]<=box[2] and box[1]<=pt[1]<=box[3]
    row.update(status='semantically_scored',prediction=body,player_in_box=inside(body.get('player'),case['player_box']),target_in_box=inside(body.get('target'),case['target_box']),answer_correct=str(body.get('answer','')).lower() in case['accepted_answers']);rows.append(row)
(a.root/'rescored.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows,indent=2))
