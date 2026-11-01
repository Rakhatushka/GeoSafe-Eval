"""Local fixture demonstration only. Never calls a model API."""
from datetime import datetime,timezone
import json
from nodata_recovery import HOME,CatalogueEnvironment,protocol
from test_nodata_recovery import fixture
from agent_loop import run_episode
from grade_episode import grade_episode

def grade_trace(folder,available):
    folder=__import__('pathlib').Path(folder)
    grade=grade_episode(folder,'ANSWER' if available else 'ABSTAIN',60 if available else None)
    events=[json.loads(line) for line in (folder/'tools.jsonl').read_text(encoding='utf-8').splitlines()]
    success=[e for e in events if e['status']=='success']
    lookups=[e for e in success if e['tool']=='lookup_catalog']
    if available:
        expected=['lookup_catalog','inspect','activate_candidate','check_compatibility','calculate_exposure'];positions=[]
        for tool in expected:
            found=[e['sequence'] for e in success if e['tool']==tool and (tool!='inspect' or e['args'].get('asset')=='candidate') and (tool!='check_compatibility' or e['output']['compatible'])]
            positions.append(found[0] if found else -1)
        grounded=all(p>0 for p in positions) and positions==sorted(set(positions))
    else:
        grounded=any(e['output']['status']=='permanently_unavailable' for e in lookups) and not any(e['tool'] in ['activate_candidate','calculate_exposure'] for e in success)
    grade.update(catalogue_recovery_trace_met=grounded,validation_status='author-defined exploratory pair; independent review pending')
    return grade

def main():
    out=HOME/'runs'/datetime.now(timezone.utc).strftime('nodata-fixture-%Y%m%d-%H%M%S-%f');out.mkdir()
    rows=[]
    for case,available in [('case-34',True),('case-92',False)]:
        run_episode(HOME/'nodata_pair/datasets'/case,out/case,fixture,environment_factory=CatalogueEnvironment,protocol=protocol(available),max_calls=7)
        grade=grade_trace(out/case,available);grade['case']=case;rows.append(grade)
    (out/'summary.json').write_text(json.dumps({'source_kind':'artificial_fixture','results':rows},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'folder':str(out),'results':rows},indent=2))

if __name__=='__main__':main()
