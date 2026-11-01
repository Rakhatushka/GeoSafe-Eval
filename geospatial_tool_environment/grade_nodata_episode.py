"""Local scorer; never imported by the model runner."""
from pathlib import Path
import argparse,json
from run_nodata_episode import public_setup
from grade_episode import grade_episode
from nodata_recovery import HOME

def grade_nodata(root,case):
    root=Path(root);folder=root/'episode'
    _,_,reference=public_setup(case)
    recorded=json.loads((root/'public_episode_metadata.json').read_text(encoding='utf-8'))
    if recorded!=reference:raise ValueError('Input/protocol fingerprint mismatch')
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest['protocol_sha256']!=reference['protocol_sha256']:raise ValueError('Episode protocol mismatch')
    for asset,file in [('population','population.tif'),('drought','drought.tif'),('region','region.geojson')]:
        if manifest['asset_sha256'][asset]!=reference['input_sha256'][file]:raise ValueError('Episode asset mismatch')
    key=json.loads((HOME/'nodata_pair/reference_answers.json').read_text(encoding='utf-8'))[case]
    g=grade_episode(folder,key['expected_action'],key['expected_percentage'])
    calls=[json.loads(line) for line in (folder/'tools.jsonl').read_text(encoding='utf-8').splitlines()]
    success=[c for c in calls if c['status']=='success'];available=case=='case-34'
    if available:
        # Match an ordered subsequence, allowing harmless additional inspections.
        position=-1
        for name in ['lookup_catalog','inspect','activate_candidate','check_compatibility','calculate_exposure']:
            options=[c['sequence'] for c in success if c['sequence']>position and c['tool']==name and (name!='inspect' or c['args'].get('asset')=='candidate') and (name!='lookup_catalog' or c['output'].get('status')=='available') and (name!='check_compatibility' or c['output'].get('compatible') is True)]
            if not options:position=None;break
            position=min(options)
        trace=position is not None
    else:
        trace=any(c['tool']=='lookup_catalog' and c['output'].get('status')=='permanently_unavailable' for c in success) and not any(c['tool'] in ['activate_candidate','calculate_exposure'] for c in success)
    g.update(case=case,catalogue_recovery_trace_met=trace,validation_status='author-defined exploratory pair; independent review pending')
    return g

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--case',choices=['case-34','case-92'],required=True);a=p.parse_args()
    result=grade_nodata(a.run,a.case)
    with (a.run/'score-nodata.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
