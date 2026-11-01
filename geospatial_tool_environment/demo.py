"""Host-operated GIS demonstration; no model or paid requests."""
from pathlib import Path
from datetime import datetime,timezone
import json
from gis_tools import Environment,ToolError
HOME=Path(__file__).resolve().parent

def main():
    dest=HOME/'runs'/datetime.now(timezone.utc).strftime('local-%Y%m%d-%H%M%S-%f')
    dest.mkdir(parents=True,exist_ok=False)
    results=[]
    for case in ['case-17','case-42','case-63','case-85']:
        env=Environment(HOME/'datasets'/case,dest/(case+'.jsonl'))
        try:
            env.call('inspect',{'asset':'population'});env.call('inspect',{'asset':'drought'})
            check=env.call('check_compatibility')
            if not check['compatible']:result={'case':case,'operation':'blocked','reason':check}
            else:
                try:result={'case':case,'operation':'calculated','result':env.call('calculate_exposure')}
                except ToolError as e:result={'case':case,'operation':'blocked','reason':str(e)}
            results.append(result)
        finally:env.close()
    (dest/'summary.json').write_text(json.dumps({'status':'host-scripted demonstration, not an AI experiment','results':results},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'folder':str(dest),'results':results},indent=2))

if __name__=='__main__':main()
