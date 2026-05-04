#!/usr/bin/env bash
set -euo pipefail

KEY_FILE="${HOME}/.stealth/api_keys.json"

ACTIVE_KEY=$(python3 -c "
import json, sys
with open('$KEY_FILE') as f: d = json.load(f)
for k in d.get('keys', []):
    if k.get('value') and not k.get('exhausted') and k.get('status') != 'empty':
        print(k['value'])
        exit(0)
print('')
" 2>/dev/null)

case "${1:-}" in
    --status)
        python3 -c "
import json
with open('$KEY_FILE') as f: d = json.load(f)
active_count = sum(1 for k in d['keys'] if k.get('value') and not k.get('exhausted') and k.get('status') != 'empty')
exhausted_count = sum(1 for k in d['keys'] if k.get('exhausted'))
empty_count = sum(1 for k in d['keys'] if not k.get('value') or k.get('status') == 'empty')
print(f'Pool: {active_count} active, {exhausted_count} exhausted, {empty_count} empty')
print(f'Keys:')
for k in d['keys']:
    marker = '✅' if (k.get('value') and not k.get('exhausted')) else ('❌' if k.get('exhausted') else '⬜')
    print(f'  {marker} {k[\"id\"]} | failures={k.get(\"failures\",0)} | added={k.get(\"added\",\"?\")}')
" 2>/dev/null
        ;;
    --add)
        KEY_ID="${2:-}"
        KEY_VALUE="${3:-}"
        if [ -z "$KEY_ID" ] || [ -z "$KEY_VALUE" ]; then
            echo "Usage: opencode_helper.sh --add <key-id> <key-value>"
            exit 1
        fi
        python3 -c "
import json
with open('$KEY_FILE') as f: d = json.load(f)
import sys
for k in d['keys']:
    if not k.get('value') or k.get('status') == 'empty':
        k['id'] = '$KEY_ID'
        k['value'] = '$KEY_VALUE'
        k['added'] = '2026-05-05'
        k['status'] = 'active'
        k['failures'] = 0
        k['exhausted'] = False
        print(f'Added: {k[\"id\"]}')
        break
with open('$KEY_FILE', 'w') as f: json.dump(d, f, indent=2)
" 2>/dev/null
        ;;
    --rotate)
        python3 -c "
import json
with open('$KEY_FILE') as f: d = json.load(f)
keys = [k for k in d['keys'] if k.get('value') and not k.get('exhausted') and k.get('status') != 'empty']
if len(keys) > 1:
    rotated = keys[1:] + [keys[0]]
    active_ids = [k['id'] for k in rotated]
    new_keys = []
    for k in d['keys']:
        if k.get('value') and not k.get('exhausted') and k.get('status') != 'empty':
            if active_ids: new_keys.append(active_ids.pop(0))
        else: new_keys.append(k)
    d['keys'] = new_keys
    with open('$KEY_FILE', 'w') as f: json.dump(d, f, indent=2)
    print('Rotated to next key')
else:
    print('No rotation possible (only 1 or 0 active keys)')
" 2>/dev/null
        ;;
    --exhaust)
        python3 -c "
import json
with open('$KEY_FILE') as f: d = json.load(f)
for k in d['keys']:
    if k.get('value') and not k.get('exhausted') and k.get('status') != 'empty':
        k['failures'] = 10
        k['exhausted'] = True
        k['status'] = 'exhausted'
        print(f'Exhausted: {k[\"id\"]}')
        break
with open('$KEY_FILE', 'w') as f: json.dump(d, f, indent=2)
" 2>/dev/null
        ;;
    *)
        if [ -n "$ACTIVE_KEY" ]; then
            echo "$ACTIVE_KEY"
        fi
        ;;
esac