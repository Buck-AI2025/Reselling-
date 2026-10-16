"""Local stdio MCP adapter. Runs where the checkout and database are available."""
import json
import os
from pathlib import Path
import sys
from app import Store

TOOLS = [
    {'name': 'list_inventory', 'description': 'List resale inventory. Does not read Facebook or Nellis.', 'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'add_inventory_item', 'description': 'Add user-supplied item facts to local inventory.', 'inputSchema': {'type': 'object', 'properties': {'title': {'type': 'string'}, 'description': {'type': 'string'}, 'cost': {'type': 'string'}, 'asking_price': {'type': 'string'}, 'source_url': {'type': 'string'}}, 'required': ['title'], 'additionalProperties': False}},
    {'name': 'prepare_listing', 'description': 'Prepare a listing draft from inventory facts; does not publish.', 'inputSchema': {'type': 'object', 'properties': {'item_id': {'type': 'integer'}}, 'required': ['item_id'], 'additionalProperties': False}},
    {'name': 'change_inventory_price', 'description': 'Change inventory asking price only. This does NOT change a live Facebook listing.', 'inputSchema': {'type': 'object', 'properties': {'item_id': {'type': 'integer'}, 'asking_price': {'type': 'string'}}, 'required': ['item_id', 'asking_price'], 'additionalProperties': False}},
]


def main():
    path = Path(os.environ.get('RESELL_DB_PATH', str(Path(__file__).resolve().parent / 'data/inventory.sqlite3')))
    path.parent.mkdir(parents=True, exist_ok=True)
    store = Store(path)
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            print(json.dumps({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}), flush=True)
            continue
        if not isinstance(message, dict) or 'id' not in message:
            continue
        response = {'jsonrpc': '2.0', 'id': message['id']}
        method = message.get('method')
        if method == 'initialize':
            response['result'] = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'reselling-inventory', 'version': '0.1.0'}}
        elif method == 'ping':
            response['result'] = {}
        elif method == 'tools/list':
            response['result'] = {'tools': TOOLS}
        elif method == 'tools/call':
            try:
                params = message.get('params', {})
                name = params['name']
                args = params.get('arguments', {})
                if name == 'list_inventory':
                    result = store.items()
                elif name == 'add_inventory_item':
                    result = {'item_ids': store.add_many([args])}
                elif name == 'prepare_listing':
                    result = store.draft(int(args['item_id']))
                elif name == 'change_inventory_price':
                    result = store.change_price(int(args['item_id']), args['asking_price'])
                else:
                    raise ValueError('Unknown tool')
                response['result'] = {'content': [{'type': 'text', 'text': json.dumps(result)}], 'isError': False}
            except (ValueError, LookupError, TypeError, AttributeError):
                response['result'] = {'content': [{'type': 'text', 'text': 'Invalid tool arguments or item not found. No Facebook action was performed.'}], 'isError': True}
        else:
            response['error'] = {'code': -32601, 'message': 'Method not found'}
        print(json.dumps(response), flush=True)


if __name__ == '__main__':
    main()
