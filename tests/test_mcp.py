import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class MCP(unittest.TestCase):
    def test_stdio_inventory_commands(self):
        calls = [
            ('initialize', {}),
            ('tools/list', {}),
            ('tools/call', {'name': 'add_inventory_item', 'arguments': {'title': 'Chair', 'asking_price': '40'}}),
            ('tools/call', {'name': 'change_inventory_price', 'arguments': {'item_id': 1, 'asking_price': '35'}}),
            ('tools/call', {'name': 'prepare_listing', 'arguments': {'item_id': 1}}),
        ]
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, 'RESELL_DB_PATH': str(Path(directory) / 'test.db')}
            messages = '\n'.join(json.dumps({'jsonrpc': '2.0', 'id': i, 'method': method, 'params': params}) for i, (method, params) in enumerate(calls)) + '\n'
            completed = subprocess.run([sys.executable, 'mcp_server.py'], input=messages, capture_output=True, text=True, env=env, timeout=10, check=True)
        replies = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(len(replies), 5)
        self.assertEqual(len(replies[1]['result']['tools']), 4)
        changed = json.loads(replies[3]['result']['content'][0]['text'])
        self.assertEqual(changed['asking_cents'], 3500)
        self.assertFalse(changed['facebook_updated'])
        draft = json.loads(replies[4]['result']['content'][0]['text'])
        self.assertEqual(draft['price'], '35.00')
