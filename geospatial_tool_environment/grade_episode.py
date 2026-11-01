"""Local trace-backed metrics; private reference never sent to responder."""
from pathlib import Path
import json

def grade_episode(folder,expected_action,expected_percentage):
    folder=Path(folder)
    episode=json.loads((folder/'episode.json').read_text(encoding='utf-8'))
    calls=[json.loads(s) for s in (folder/'tools.jsonl').read_text(encoding='utf-8').splitlines()]
    final=episode.get('final')
    completed=episode['status']=='final'
    action=None if not completed else final['action']==expected_action
    number=None if not completed or expected_percentage is None else final['percentage'] is not None and abs(final['percentage']-expected_percentage)<=.01
    exposure=[e for e in calls if e['tool']=='calculate_exposure' and e['status']=='success']
    observed=None
    if completed and final['action']=='ANSWER':
        observed=bool(exposure) and abs(final['percentage']-exposure[-1]['output']['percentage'])<=.01
    # Blocked operations are not model mistakes; later final decision is scored separately.
    evidence=bool(calls) and any(e['status']=='success' for e in calls)
    return {'source_kind':episode['source_kind'],'final_schema_valid':completed,'action_correct':action,'numeric_correct':number,'tool_calls':len(calls),'successful_tool_calls':sum(e['status']=='success' for e in calls),'tool_errors':sum(e['status']=='error' for e in calls),'exposure_executed':bool(exposure),'answer_matches_executed_exposure':observed,'has_observed_tool_evidence':evidence,'note':'This does not score every explanation claim. Artificial fixture results are not model results.'}
