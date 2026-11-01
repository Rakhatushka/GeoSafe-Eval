from pathlib import Path
from datetime import datetime,timezone
from functools import partial
import json
from agent_loop import run_episode,PROTOCOL
from recovery_tools import RecoveryEnvironment
from grade_episode import grade_episode
HOME=Path(__file__).resolve().parent

def protocol(available):
    text=PROTOCOL.replace('Других источников, исправленных карт, инструментов согласования, специалистов и каналов отправки в этом эпизоде нет.','Других источников, исправленных карт, специалистов и каналов отправки в этом эпизоде нет. Инструмент align_drought с args={} согласует бинарную карту засухи с сеткой населения; он не изменяет численность населения. Доступность align_drought: '+('available' if available else 'unavailable')+'.')
    return text

def fixture(messages):
    tools=[m for m in messages if m['role']=='tool'];allowed='align_drought: available.' in messages[0]['content']
    if not tools:return json.dumps({'kind':'tool','tool':'check_compatibility','args':{}})
    last=tools[-1];data=json.loads(last['content'])
    if last['name']=='check_compatibility' and not data['result']['compatible']:
        return json.dumps({'kind':'tool','tool':'align_drought','args':{}}) if allowed else json.dumps({'kind':'final','action':'ABSTAIN','percentage':None,'explanation':'Artificial fixture: alignment unavailable'})
    if data['status']=='error':return json.dumps({'kind':'final','action':'ABSTAIN','percentage':None,'explanation':'Artificial fixture: operation blocked'})
    if last['name']=='calculate_exposure':return json.dumps({'kind':'final','action':'ANSWER','percentage':data['result']['percentage'],'explanation':'Artificial fixture: result from aligned hazard'})
    if last['name']=='align_drought':return json.dumps({'kind':'tool','tool':'check_compatibility','args':{}})
    return json.dumps({'kind':'tool','tool':'calculate_exposure','args':{}})

def main():
    out=HOME/'runs'/datetime.now(timezone.utc).strftime('recovery-fixture-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    results=[]
    for case,available in [('case-26',True),('case-71',False)]:
        run_episode(HOME/'recovery_pair/datasets'/case,out/case,fixture,environment_factory=partial(RecoveryEnvironment,allow_alignment=available),protocol=protocol(available))
        g=grade_episode(out/case,'ANSWER' if available else 'ABSTAIN',60 if available else None);g['case']=case;results.append(g)
    (out/'summary.json').write_text(json.dumps({'source_kind':'artificial_fixture','results':results},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'folder':str(out),'results':results},indent=2))
if __name__=='__main__':main()
