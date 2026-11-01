"""Local scoring v2: preserve strict JSON scoring; separately assess one fenced JSON object."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from run_eval import read_json, save, ACTIONS, parse_answer

SCORER_VERSION = '2.0-fenced-content-separate'


def extract_content(raw):
    obj, strict_status = parse_answer(raw)
    if obj is not None:
        return obj, 'raw_json', strict_status
    match = re.fullmatch(r'\s*```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```\s*', raw)
    if match:
        obj, inner_status = parse_answer(match.group(1))
        if obj is not None:
            return obj, 'single_markdown_json_block', strict_status
        return None, 'unassessable_fenced_'+inner_status, strict_status
    return None, 'unassessable', strict_status


def local_text(run_dir, rec):
    name = rec.get('raw_text_file')
    if not isinstance(name, str) or Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('Invalid raw text filename in records')
    target = (run_dir/name).resolve()
    if not target.is_relative_to(run_dir.resolve()):
        raise ValueError('Raw text outside run directory')
    return target.read_text(encoding='utf-8')


def grade(run_dir, key_path):
    manifest = read_json(run_dir/'manifest.json')
    if manifest['mode'] != 'live':
        raise ValueError('Offline plan contains no model results; cannot score')
    cases = read_json(key_path)
    if not isinstance(cases, list) or not cases:
        raise ValueError('Key must be a nonempty array')
    by_id = {}
    for case in cases:
        if case['id'] in by_id or case['expected_action'] not in ACTIONS:
            raise ValueError('Invalid or duplicate key entry')
        by_id[case['id']] = case
    tasks = read_json(run_dir/'public_tasks_snapshot.json')
    ids = [t['id'] for t in tasks]
    if len(ids) != len(set(ids)) or any(x not in by_id for x in ids):
        raise ValueError('Run tasks do not match key IDs')
    for t in tasks:
        expected_hash = by_id[t['id']].get('public_prompt_sha256')
        if expected_hash and hashlib.sha256(t['prompt'].encode()).hexdigest() != expected_hash:
            raise ValueError('Prompt differs from key snapshot')
    records = read_json(run_dir/'records.json')
    groups = {}
    for r in records:
        token = (r['repeat'], r['id'])
        if token in groups or r['id'] not in ids:
            raise ValueError('Unexpected or duplicate result')
        groups[token] = r
    repeats = manifest['planned_requests']//len(ids)
    reports = []
    model_output_statuses = {'valid', 'invalid_json', 'invalid_schema', 'invalid_action',
        'invalid_percentage', 'nonanswer_has_percentage', 'invalid_explanation'}
    for repeat in range(1, repeats+1):
        details = []
        for case_id in ids:
            c = by_id[case_id]
            r = groups.get((repeat, case_id))
            status = r['status'] if r else 'not_attempted'
            obj = r.get('parsed') if r else None
            valid = status == 'valid'
            expected_number = c.get('expected_percentage')
            item = {'id': case_id, 'status': status,
                'action_correct': valid and obj['action'] == c['expected_action'],
                'numeric_case': expected_number is not None,
                'numeric_correct': None if expected_number is None else
                    valid and obj['percentage'] is not None and abs(obj['percentage']-expected_number)<=0.01,
                'observed_percentage': obj.get('percentage') if obj else None,
                'strict_schema_valid': None, 'content_assessable': False,
                'content_extraction': 'not_eligible', 'content_action_correct': None,
                'content_numeric_correct': None, 'content_percentage': None}
            # Never salvage truncated, rejected, wrong-model, timed-out or unattempted responses.
            if r and status in model_output_statuses:
                raw = local_text(run_dir, r)
                content, method, strict_status = extract_content(raw)
                item.update(strict_schema_valid=strict_status=='valid',
                            strict_parse_status=strict_status, content_extraction=method)
                if content is not None:
                    numeric_ok = None if expected_number is None else (
                        content['percentage'] is not None and abs(content['percentage']-expected_number)<=0.01)
                    item.update(content_assessable=True,
                        content_action_correct=content['action']==c['expected_action'],
                        content_numeric_correct=numeric_ok, content_action=content['action'],
                        content_percentage=content['percentage'])
            details.append(item)
        numbers = [d for d in details if d['numeric_case']]
        complete = [d for d in details if d['strict_schema_valid'] is not None]
        assessable = [d for d in details if d['content_assessable']]
        reports.append({'repeat': repeat, 'planned_cases': len(ids),
            'schema_valid': sum(d['strict_schema_valid'] is True for d in details),
            'completed_model_outputs': len(complete),
            'valid_output_coverage': sum(d['strict_schema_valid'] is True for d in details)/len(ids),
            'status_counts': dict(Counter(d['status'] for d in details)),
            'action_correct': sum(d['action_correct'] for d in details),
            'numeric_cases': len(numbers), 'numeric_correct': sum(d['numeric_correct'] for d in numbers),
            'content_assessable': len(assessable),
            'content_action_correct': sum(d['content_action_correct'] is True for d in details),
            'content_numeric_assessable': sum(d['numeric_case'] and d['content_assessable'] for d in details),
            'content_numeric_correct': sum(d['content_numeric_correct'] is True for d in details),
            'fenced_outputs_assessed': sum(d['content_extraction']=='single_markdown_json_block' for d in details),
            'details': details})
    return {'scorer_version': SCORER_VERSION, 'reports': reports,
        'analysis_type': 'Supplementary content scoring added after observing smoke output; original strict scoring retained.',
        'extraction_rule': 'Only raw valid JSON or one full-response json/unlabeled Markdown fence; no surrounding prose, multiple blocks, quote repair or percentage inference.',
        'note': 'Content correctness means action/percentage key matching, not explanation validity or actual tool behavior. Technical failures and unattempted cases are not model errors. Never replace first responses.'}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--key',type=Path,required=True)
    a=p.parse_args()
    try:
        result=grade(a.run,a.key)
        save(a.run/'score.json',result)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError,TypeError) as error:
        p.exit(1,'Cannot grade: '+str(error)+'\n')
