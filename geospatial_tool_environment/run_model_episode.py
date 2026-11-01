"""One explicitly selected case, offline unless --live. Never reads reference answers."""
import argparse,json,sys
from pathlib import Path
from agent_loop import run_episode,PROTOCOL
from model_transport import ModelResponder

HOME=Path(__file__).resolve().parent
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',choices=['case-17','case-42','case-63','case-85'],default='case-17')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--live',action='store_true')
    p.add_argument('--max-requests',type=int,default=6)
    p.add_argument('--max-usd',default='0.10')
    a=p.parse_args()
    try:
        if not a.live:
            a.output.mkdir(parents=True,exist_ok=False)
            (a.output/'offline-plan.json').write_text(json.dumps({'mode':'offline','case':a.case,'model':'openai/gpt-6.1-sol','provider':'openai','max_requests':a.max_requests,'max_usd_threshold':a.max_usd,'protocol':PROTOCOL,'network_calls':0,'has_model_results':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print('OFFLINE: episode plan saved; no network calls or model results.');return 0
        # Reserve a new folder for API records, never merge with an earlier episode.
        a.output.mkdir(parents=True,exist_ok=False)
        responder=ModelResponder(a.output/'api',max_requests=a.max_requests,max_usd=a.max_usd)
        result=run_episode(HOME/'datasets'/a.case,a.output/'episode',responder,max_turns=6,max_calls=5,source_kind='model_api')
        print(json.dumps({'status':result['status'],'final':result['final'],'observed_cost_usd':str(responder.cost),'requests':len(responder.records),'output':str(a.output)},ensure_ascii=False,indent=2))
        return 0 if result['status']=='final' else 1
    except (OSError,ValueError,RuntimeError) as e:
        print('Stopped: '+str(e),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
