"""Catalogue-recovery API entrypoint. Offline by default; no scoring-key imports."""
from pathlib import Path
import argparse,hashlib,json,sys
from decimal import Decimal
from agent_loop import run_episode
from model_transport import ModelResponder
from nodata_hidden import HOME,HiddenCatalogueEnvironment,HIDDEN_PROTOCOL

def public_setup(case):
    if case not in ['case-48','case-76']:raise ValueError('Unknown catalogue case')
    source=HOME/'nodata_hidden_pair/datasets'/case
    obj=json.loads((source/'capabilities.json').read_text(encoding='utf-8'))
    if set(obj)!={'catalog_available'} or type(obj['catalog_available']) is not bool:raise ValueError('Invalid capability manifest')
    files=['population.tif','drought.tif','region.geojson','candidate.tif','catalog.json','capabilities.json']
    hashes={n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in files}
    text=HIDDEN_PROTOCOL
    return source,text,{'case':case,'protocol_sha256':hashlib.sha256(text.encode()).hexdigest(),'input_sha256':hashes}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',choices=['case-48','case-76'],required=True)
    p.add_argument('--model-profile',choices=['gpt-sol','sonnet'],default='gpt-sol')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--live',action='store_true')
    p.add_argument('--max-requests',type=int,default=8);p.add_argument('--max-usd',default='0.05')
    a=p.parse_args(argv)
    try:
        if not 1<=a.max_requests<=8:raise ValueError('Requests must be 1..8')
        budget=Decimal(a.max_usd)
        if not budget.is_finite() or not 0<budget<=Decimal('.10'):raise ValueError('Budget must be >0 and <=0.10')
        source,text,meta=public_setup(a.case)
        a.output.mkdir(parents=True,exist_ok=False)
        (a.output/'public_episode_metadata.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
        if not a.live:
            (a.output/'offline-plan.json').write_text(json.dumps({'mode':'offline','protocol':text,'model_profile':a.model_profile,'network_calls':0,'max_requests':a.max_requests,'max_usd_threshold':str(budget)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print('OFFLINE: catalogue plan saved; zero API requests.');return 0
        responder=ModelResponder(a.output/'api',max_requests=a.max_requests,max_usd=str(budget),profile=a.model_profile)
        result=run_episode(source,a.output/'episode',responder,max_turns=a.max_requests,max_calls=7,source_kind='model_api',environment_factory=HiddenCatalogueEnvironment,protocol=text)
        print(json.dumps({'status':result['status'],'final':result['final'],'observed_cost_usd':str(responder.cost),'requests':len(responder.records),'output':str(a.output)},ensure_ascii=False,indent=2))
        return 0 if result['status']=='final' else 1
    except (ValueError,OSError,RuntimeError) as e:
        print('Stopped: '+str(e),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
