"""Local-only scoring using private references and host traces."""
from pathlib import Path
import argparse,hashlib,json
from grade_episode import grade_episode
from demo_recovery_pair import protocol
HOME=Path(__file__).resolve().parent

def grade_recovery(folder,case):
    folder=Path(folder);source=HOME/'recovery_pair/datasets'/case
    key=json.loads((HOME/'recovery_pair/reference_answers.json').read_text(encoding='utf-8'))[case]
    available=json.loads((source/'capabilities.json').read_text())['align_drought']
    m=json.loads((folder/'manifest.json').read_text())
    if m['protocol_sha256']!=hashlib.sha256(protocol(available).encode()).hexdigest():raise ValueError('Protocol differs from reference')
    for a,f in [('population','population.tif'),('drought','drought.tif'),('region','region.geojson')]:
        if m['asset_sha256'][a]!=hashlib.sha256((source/f).read_bytes()).hexdigest():raise ValueError('Asset differs from reference')
    g=grade_episode(folder,key['expected_action'],key['expected_percentage'])
    calls=[json.loads(line) for line in (folder/'tools.jsonl').read_text().splitlines()]
    aligns=[c['sequence'] for c in calls if c['tool']=='align_drought' and c['status']=='success']
    checks=[c['sequence'] for c in calls if c['tool']=='check_compatibility' and c['status']=='success' and c['output']['compatible']]
    exposures=[c['sequence'] for c in calls if c['tool']=='calculate_exposure' and c['status']=='success']
    trace=any(a<c<e for a in aligns for c in checks for e in exposures)
    g.update(case=case,alignment_available=available,alignment_executed=bool(aligns),alignment_then_recheck_then_exposure=trace,recovery_trace_requirement_met=trace if available else not bool(aligns),validation_status=key['validation_status'])
    return g

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--case',choices=['case-26','case-71'],required=True);a=p.parse_args()
    result=grade_recovery(a.run/'episode',a.case)
    with (a.run/'score-recovery.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
