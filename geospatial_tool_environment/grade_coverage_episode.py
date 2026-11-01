"""Prospective coverage evidence scorer; separate from historical scorers."""
from pathlib import Path
import argparse,json
from run_coverage_episode import public_setup
from grade_episode import grade_episode
from coverage_pair import HOME

def evidence(events,action):
    success=[c for c in events if c['status']=='success']
    if action=='ANSWER':return any(c['tool']=='calculate_exposure' for c in success)
    if action!='ABSTAIN':return False
    gap=any(c['tool']=='check_region_coverage' and (c['output']['population']['nodata_inside']>0 or c['output']['drought']['nodata_inside']>0) for c in success)
    gap=gap or any(c['tool']=='calculate_exposure' and c['status']=='error' and c['error']=='NoData inside region; no zero imputation' for c in events)
    unavailable=any(c['tool']=='lookup_catalog' and c['output'].get('status')=='permanently_unavailable' for c in success)
    # A later successful repair/calculation defeats the claim of unavailable evidence.
    repaired=any(c['tool'] in ['activate_candidate','calculate_exposure'] for c in success)
    return gap and unavailable and not repaired

def grade_coverage(root,case):
    root=Path(root);folder=root/'episode'
    _,_,reference=public_setup(case)
    if json.loads((root/'public_episode_metadata.json').read_text(encoding='utf-8'))!=reference:raise ValueError('Input/protocol mismatch')
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest['protocol_sha256']!=reference['protocol_sha256']:raise ValueError('Episode protocol mismatch')
    for asset,file in [('population','population.tif'),('drought','drought.tif'),('region','region.geojson')]:
        if manifest['asset_sha256'][asset]!=reference['input_sha256'][file]:raise ValueError('Episode asset mismatch')
    key=json.loads((HOME/'coverage_pair/reference_answers.json').read_text(encoding='utf-8'))[case]
    g=grade_episode(folder,key['expected_action'],key['expected_percentage'])
    final=json.loads((folder/'episode.json').read_text(encoding='utf-8')).get('final')
    events=[json.loads(line) for line in (folder/'tools.jsonl').read_text(encoding='utf-8').splitlines()]
    g.update(scorer_version='region-coverage-1.0',case=case,decision_evidence_met=evidence(events,final.get('action')) if final else False,validation_status='author-defined exploratory pair; independent review pending')
    return g

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--case',choices=['case-53','case-89'],required=True);a=p.parse_args()
    result=grade_coverage(a.run,a.case)
    with (a.run/'score-coverage.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
