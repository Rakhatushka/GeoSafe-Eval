"""Four no-cost scripted episodes through the same controlled tool interface."""
from pathlib import Path
from datetime import datetime,timezone
import json
from agent_loop import run_episode,reference_fixture
from grade_episode import grade_episode

HOME=Path(__file__).resolve().parent
def main():
    out=HOME/'runs'/datetime.now(timezone.utc).strftime('fixture-loop-%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True,exist_ok=False)
    results=[]
    # Evaluator-side references are not given to the responder.
    for case,action,pct in [('case-17','ANSWER',60),('case-42','ABSTAIN',None),('case-63','ABSTAIN',None),('case-85','ANSWER',60)]:
        run_episode(HOME/'datasets'/case,out/case,reference_fixture)
        result=grade_episode(out/case,action,pct);result['case']=case;results.append(result)
    (out/'summary.json').write_text(json.dumps({'source_kind':'artificial_fixture','results':results},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'folder':str(out),'source_kind':'artificial_fixture','results':results},indent=2))
if __name__=='__main__':main()
