"""Call the deployed agent endpoint over REST (the `serving-endpoints query` CLI hides `output`).

Run: python -m scripts.query_endpoint "question" ["follow-up" ...]
Prints each answer. Uses the Databricks CLI profile in DATABRICKS_CONFIG_PROFILE.
"""
import json
import os
import subprocess
import sys
import time

ENDPOINT = 'agents_insurance_automation-models-claims_copilot_agent'


def ask(text: str, profile: str | None = None, endpoint: str = ENDPOINT) -> tuple[str, float]:
    profile = profile or os.environ.get('DATABRICKS_CONFIG_PROFILE', 'candiate-analysis')
    body = json.dumps({'input': [{'role': 'user', 'content': text}]})
    started = time.time()
    proc = subprocess.run(
        ['databricks', 'api', 'post', f'/serving-endpoints/{endpoint}/invocations',
         '--json', body, '--profile', profile],
        capture_output=True, text=True, timeout=600, check=False,
    )
    elapsed = time.time() - started
    if proc.returncode != 0:
        return f'ERROR: {(proc.stderr or proc.stdout).strip()[:400]}', elapsed
    reply = json.loads(proc.stdout)
    return reply['output'][0]['content'][0]['text'], elapsed


if __name__ == '__main__':
    for question in sys.argv[1:]:
        answer, seconds = ask(question)
        print(f'\nQ: {question}\n[{seconds:.1f}s]\n{answer}')
