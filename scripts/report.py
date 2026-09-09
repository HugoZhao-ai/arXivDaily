"""Write a concise GitHub Actions summary without printing secrets."""
import os
from common import ROOT, read_json

state = read_json(ROOT / 'data/state.json', {})
enrichment = read_json(ROOT / 'data/enrichment.json', {})
last = state.get('last_run') or {}
lines = ['## Quant Research Daily', '', f"- Sync step: {os.getenv('SYNC_OUTCOME', 'unknown')}",
         f"- Enrichment step: {os.getenv('ENRICH_OUTCOME', 'unknown')}",
         f"- Saved papers: {last.get('paper_count', 0)}",
         f"- Last complete sync (UTC): {state.get('last_success') or 'not yet'}",
         f"- Latest data status: {last.get('status', 'not yet')}",
         f"- Summary generation failures: {len(enrichment.get('errors', []))}", '']
lines += [f'- {message}' for message in last.get('errors', []) + last.get('warnings', [])]
report = '\n'.join(lines) + '\n'
if os.getenv('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
        handle.write(report)
print(report)
