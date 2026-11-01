"""New recovery protocol; keys are not read here. Offline unless --live."""
from pathlib import Path
from functools import partial
import argparse,hashlib,json,sys
from agent_loop import run_episode
from recovery_tools import RecoveryEnvironment
from demo_recovery_pair import protocol
from model_transport import ModelResponder
HOME=Path(__file__).resolve().parent

def capability(case_root):
    obj=json.loads((Path(case_root)/'capabilities.json').read_text(encoding='utf-8'))
    if set(obj)!={'align_drought'} or type(obj['align_drought']) is not bool:raise ValueError('Invalid host capability manifest')
    return obj['align_drought']

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-profile',choices=['gpt-sol','sonnet'],default='gpt-sol')
    p.add_argument('--case',choices=['case-26','case-71'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--live',action='store_true')
    p.add_argument('--max-requests',type=int,default=8);p.add_argument('--max-usd',default='0.05')
    a=p.parse_args()
    try:
        if not 1<=a.max_requests<=8:raise ValueError('Requests must be 1..8')
        case_root=HOME/'recovery_pair/datasets'/a.case
        available=capability(case_root);task_protocol=protocol(available)
        a.output.mkdir(parents=True,exist_ok=False)
        (a.output/'public_episode_metadata.json').write_text(json.dumps({'case':a.case,'align_drought':available,'protocol_sha256':hashlib.sha256(task_protocol.encode()).hexdigest()},indent=2)+'\n',encoding='utf-8')
        if not a.live:
            (a.output/'offline-plan.json').write_text(json.dumps({'mode':'offline','case':a.case,'protocol':task_protocol,'network_calls':0,'max_requests':a.max_requests,'max_usd_threshold':a.max_usd},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print('OFFLINE: recovery episode plan saved; no network calls or model results.');return 0
        responder=ModelResponder(a.output/'api',max_requests=a.max_requests,max_usd=a.max_usd,profile=a.model_profile)
        result=run_episode(case_root,a.output/'episode',responder,max_turns=a.max_requests,max_calls=7,source_kind='model_api',environment_factory=partial(RecoveryEnvironment,allow_alignment=available),protocol=task_protocol)
        print(json.dumps({'status':result['status'],'final':result['final'],'observed_cost_usd':str(responder.cost),'requests':len(responder.records),'output':str(a.output)},ensure_ascii=False,indent=2))
        return 0 if result['status']=='final' else 1
    except (ValueError,OSError,RuntimeError) as e:
        print('Stopped: '+str(e),file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
