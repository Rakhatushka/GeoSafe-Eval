"""Independent OpenRouter Chat Completions requests. Standard library only. Offline by default."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'
ACTIONS = {'ANSWER', 'INVESTIGATE', 'ABSTAIN', 'ESCALATE'}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def tasks_from(path):
    tasks = read_json(path)
    if not isinstance(tasks, list) or not tasks:
        raise ValueError('Tasks must be a nonempty array')
    seen = set()
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {'id', 'prompt'}:
            raise ValueError('Each public task must contain ONLY id and prompt; never pass the key')
        if not all(isinstance(task[k], str) and task[k].strip() for k in ('id', 'prompt')):
            raise ValueError('Task id and prompt must be nonempty text')
        if task['id'] in seen:
            raise ValueError('Duplicate task id')
        seen.add(task['id'])
    return tasks


def config_from(path):
    c = read_json(path)
    if not isinstance(c, dict) or set(c) != {'model', 'provider', 'max_tokens', 'effort', 'timeout_seconds'}:
        raise ValueError('Config must contain model, provider, max_tokens, effort, timeout_seconds')
    if not isinstance(c['model'], str) or '/' not in c['model'] or any(x in c['model'].lower() for x in ('latest', ':online', ':free', '~', 'auto')):
        raise ValueError('Explicit non-auto model slug required; no latest or routing aliases')
    if not isinstance(c['provider'], str) or not c['provider'].strip():
        raise ValueError('One explicit provider slug required')
    if type(c['max_tokens']) is not int or not 1 <= c['max_tokens'] <= 8192:
        raise ValueError('max_tokens must be 1..8192')
    if c['effort'] not in (None, 'low', 'medium', 'high'):
        raise ValueError('Unsupported effort')
    if type(c['timeout_seconds']) is not int or not 1 <= c['timeout_seconds'] <= 300:
        raise ValueError('timeout_seconds must be 1..300')
    return c


def payload_for(task, config):
    payload = {'model': config['model'], 'max_tokens': config['max_tokens'],
            'provider': {'only': [config['provider']], 'allow_fallbacks': False,
                         'require_parameters': True},
            'messages': [{'role': 'user', 'content': task['prompt']}],
            'stream': False}
    if config['effort'] is not None:
        payload['reasoning'] = {'effort': config['effort']}
    return payload


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON property')
        result[key] = value
    return result


def parse_answer(text):
    """Do not strip code fences, fix quotes, or infer a number from the explanation."""
    try:
        obj = json.loads(text, object_pairs_hook=strict_object,
                         parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    except (ValueError, TypeError):
        return None, 'invalid_json'
    if not isinstance(obj, dict) or set(obj) != {'action', 'percentage', 'explanation'}:
        return None, 'invalid_schema'
    if not isinstance(obj['action'], str) or obj['action'] not in ACTIONS:
        return None, 'invalid_action'
    number = obj['percentage']
    if number is not None and (type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 100):
        return None, 'invalid_percentage'
    if obj['action'] != 'ANSWER' and number is not None:
        return None, 'nonanswer_has_percentage'
    if not isinstance(obj['explanation'], str) or not obj['explanation'].strip():
        return None, 'invalid_explanation'
    return obj, 'valid'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward credentials to a redirect target.


def call_api(payload, config, key):
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode('utf-8'),
          headers={'Content-Type': 'application/json', 'Authorization': 'Bearer '+key}, method='POST')
    opener = urllib.request.build_opener(NoRedirect)
    with opener.open(req, timeout=config['timeout_seconds']) as response:
        raw = response.read()
        request_id = response.headers.get('request-id')
    return raw, request_id


def run(tasks, config, output, repeats=1, limit=None, live=False, call=call_api):
    selected = tasks if limit is None else tasks[:limit]
    count = len(selected) * repeats
    if not count or count > 30:
        raise ValueError('Pilot cap: 1..30 requests per run')
    key = os.environ.get('OPENROUTER_API_KEY', '') if live else ''
    if live and not key.strip():
        raise ValueError('OPENROUTER_API_KEY is missing; set it locally, never paste it in chat')
    output.mkdir(parents=True, exist_ok=False)  # No overwrite or accidental resend into an old run.
    manifest = {'created_utc': stamp(), 'mode': 'live' if live else 'offline_plan',
                'provider': 'openrouter_chat_completions', 'endpoint': ENDPOINT, 'config': config,
                'planned_requests': count, 'max_output_tokens_total': count*config['max_tokens'],
                'tools': [], 'history': False, 'automatic_retries': 0,
                'runner_sha256': digest(Path(__file__).read_bytes()),
                'tasks_sha256': digest(json.dumps(tasks, ensure_ascii=False, sort_keys=True).encode()),
                'note': 'No dollar budget enforcement; output-token cap is not a price estimate. Raw provider data preserved.'}
    save(output/'manifest.json', manifest)
    save(output/'public_tasks_snapshot.json', selected)
    records = []
    interrupted = False
    try:
        for repeat in range(1, repeats+1):
            for task in selected:
                payload = payload_for(task, config)
                n = len(records)+1
                request_path = output/f'{n:03}-request.json'
                save(request_path, payload)
                rec = {'id': task['id'], 'repeat': repeat, 'started_utc': stamp(),
                       'request_file': request_path.name, 'status': 'planned' if not live else 'started'}
                records.append(rec)
                save(output/'records.json', records)  # Write-ahead log before sending a paid request.
                if not live:
                    continue
                start = time.monotonic()
                try:
                    raw, request_id = call(payload, config, key)
                    raw_path = output/f'{n:03}-provider-response.json'
                    raw_path.write_bytes(raw)
                    rec.update(provider_response_file=raw_path.name, request_id=request_id,
                               elapsed_seconds=round(time.monotonic()-start, 3), finished_utc=stamp())
                    result = json.loads(raw)
                    if not isinstance(result, dict) or result.get('error'):
                        rec['status'] = 'provider_error'
                        save(output/'records.json', records)
                        print('Provider error; inspect raw provider response locally. No retry.')
                        return 1
                    choices = result.get('choices')
                    if not isinstance(choices, list) or len(choices) != 1:
                        raise ValueError('Expected exactly one provider choice')
                    choice = choices[0]
                    message = choice.get('message', {})
                    text = message.get('content')
                    if text is None:
                        text = ''
                    if not isinstance(text, str):
                        raise ValueError('Expected text content')
                    rec.update(returned_model=result.get('model'), returned_provider=result.get('provider'),
                               generation_id=result.get('id'), usage=result.get('usage'),
                               stop_reason=choice.get('finish_reason'),
                               native_finish_reason=choice.get('native_finish_reason'))
                    (output/f'{n:03}-text.txt').write_text(text, encoding='utf-8')
                    parsed, status = parse_answer(text)
                    rec.update(status=status, raw_text_file=f'{n:03}-text.txt', parsed=parsed)
                    if choice.get('finish_reason') != 'stop':
                        rec['status'] = 'incomplete_or_nonstandard_stop'
                    if result.get('model') != config['model']:
                        # Do not silently treat another model or a changed response ID as equivalent.
                        rec['status'] = 'returned_model_requires_review'
                        save(output/'records.json', records)
                        print('Returned model differs from configured slug; stopped for review. No retry.')
                        return 1
                except urllib.error.HTTPError as err:
                    # Keep only a bounded error message; never headers or raw error bodies.
                    rec.update(status='http_error', http_status=err.code, finished_utc=stamp())
                    try:
                        error_data = json.loads(err.read(16384).decode('utf-8'))
                        message = error_data.get('error', {}).get('message')
                        if isinstance(message, str):
                            if key:
                                message = message.replace(key, '[REDACTED]')
                            message = re.sub(r'sk-[A-Za-z0-9_-]+', '[REDACTED]', message)
                            rec['http_error_message'] = message[:2000]
                    except (OSError, ValueError, AttributeError, TypeError):
                        pass
                    save(output/'records.json', records)
                    print(f'{task["id"]}, repeat {repeat}: HTTP {err.code}; stopped. No retry. See records.json.')
                    return 1
                except (OSError, ValueError, KeyError, TypeError) as err:
                    rec.update(status='transport_or_provider_error', error_type=type(err).__name__,
                               delivery_or_charge_uncertain=True, finished_utc=stamp())
                    save(output/'records.json', records)
                    print(f'{task["id"]}, repeat {repeat}: transport_or_provider_error; stopped. No retry. See records.json.')
                    return 1
                save(output/'records.json', records)
                print(f'{task["id"]}, repeat {repeat}: {rec["status"]}')
    except KeyboardInterrupt:
        interrupted = True
        print('Stopped. A started request may have been billed; inspect records before any new run.')
    finally:
        # Each repeat is a separate evaluator-compatible file; no duplicate IDs across repeats.
        for repeat in range(1, repeats+1):
            responses = [dict(id=r['id'], **r['parsed']) for r in records
                         if r['repeat'] == repeat and r['status'] == 'valid']
            save(output/f'responses-repeat-{repeat}.json', responses)
        save(output/'records.json', records)
    if not live:
        print(f'OFFLINE: {count} request plans saved; no network calls and no model results.')
    return 130 if interrupted else 0


def main():
    folder = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tasks', type=Path, default=folder/'model_tasks.json')
    p.add_argument('--config', type=Path, default=folder/'openrouter-config.json')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--limit', type=int)
    p.add_argument('--repeats', type=int, default=1)
    p.add_argument('--live', action='store_true', help='Send paid API requests; default is offline')
    args = p.parse_args()
    try:
        if not 1 <= args.repeats <= 3 or (args.limit is not None and args.limit < 1):
            raise ValueError('repeats must be 1..3; limit must be positive')
        return run(tasks_from(args.tasks), config_from(args.config), args.output,
                   repeats=args.repeats, limit=args.limit, live=args.live)
    except (ValueError, OSError) as err:
        print(f'Error: {err}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
