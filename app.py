"""Resale inventory API. No third-party dependencies; Facebook is not connected."""
import csv
import hmac
import io
import json
import os
from pathlib import Path
import sqlite3
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def price(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > Decimal('10000000'):
            raise ValueError('Price must be between 0 and 10000000')
        if amount != amount.quantize(Decimal('.01')):
            raise ValueError('Price must have at most two decimal places')
        return int(amount * 100)
    except (InvalidOperation, TypeError):
        raise ValueError('Invalid price') from None


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS items (
                  id INTEGER PRIMARY KEY, title TEXT NOT NULL,
                  description TEXT NOT NULL, cost_cents INTEGER NOT NULL,
                  asking_cents INTEGER NOT NULL, source_url TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                  id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL,
                  old_cents INTEGER NOT NULL, new_cents INTEGER NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            ''')

    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def add_many(self, rows):
        validated = []
        for row in rows:
            title = str(row.get('title', '')).strip()
            if not title or len(title) > 300:
                raise ValueError('Each item needs a title of 1–300 characters')
            validated.append((title, str(row.get('description', '')), price(row.get('cost', 0)),
                              price(row.get('asking_price', 0)), str(row.get('source_url', ''))))
        ids = []
        with self.connect() as db:
            for values in validated:
                ids.append(db.execute('INSERT INTO items (title,description,cost_cents,asking_cents,source_url) VALUES (?,?,?,?,?)', values).lastrowid)
        return ids

    def items(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM items ORDER BY id')]

    def change_price(self, item_id, value):
        cents = price(value)
        with self.connect() as db:
            item = db.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone()
            if item is None:
                raise LookupError('Item not found')
            db.execute('UPDATE items SET asking_cents=? WHERE id=?', (cents, item_id))
            db.execute('INSERT INTO events (item_id,old_cents,new_cents) VALUES (?,?,?)', (item_id, item['asking_cents'], cents))
        return {'item_id': item_id, 'asking_cents': cents, 'scope': 'inventory_only', 'facebook_updated': False}

    def draft(self, item_id):
        with self.connect() as db:
            item = db.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone()
        if item is None:
            raise LookupError('Item not found')
        return {'title': item['title'], 'price': f"{item['asking_cents'] / 100:.2f}",
                'description': item['description'], 'published': False,
                'review_needed': ['Verify condition, measurements, pickup location, and photos before posting.']}


def make_handler(store, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Do not log authorization headers or uploaded purchase data.

        def send_json(self, code, data):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request()

        def handle_request(self):
            path = urlsplit(self.path).path
            if path == '/health' and self.command == 'GET':
                return self.send_json(200, {'status': 'ok'})
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                return self.send_json(401, {'error': 'Bearer token required'})
            try:
                if self.command == 'GET' and path == '/integrations':
                    return self.send_json(200, {
                        'facebook': {'connected': False, 'marketplace_supported': False,
                                     'reason': 'No verified Marketplace or group publishing integration configured.'},
                        'nellis': {'connected': False, 'import': 'CSV upload supported; account browsing unavailable.'}})
                if self.command == 'GET' and path == '/items':
                    return self.send_json(200, store.items())
                parts = path.strip('/').split('/')
                if self.command == 'GET' and len(parts) == 3 and parts[0] == 'items' and parts[2] == 'draft':
                    return self.send_json(200, store.draft(int(parts[1])))
                if self.command == 'POST':
                    size = int(self.headers.get('Content-Length', '0'))
                    if size < 1 or size > 2_000_000:
                        return self.send_json(413, {'error': 'Body must be 1–2000000 bytes'})
                    body = self.rfile.read(size).decode('utf-8-sig')
                    if path == '/imports/csv':
                        reader = csv.DictReader(io.StringIO(body))
                        if not reader.fieldnames or 'title' not in reader.fieldnames:
                            raise ValueError('CSV requires a title column')
                        return self.send_json(201, {'item_ids': store.add_many(list(reader))})
                    data = json.loads(body)
                    if not isinstance(data, dict):
                        raise ValueError('JSON body must be an object')
                    if path == '/items':
                        return self.send_json(201, {'item_ids': store.add_many([data])})
                    if len(parts) == 3 and parts[0] == 'items' and parts[2] == 'price':
                        return self.send_json(200, store.change_price(int(parts[1]), data['asking_price']))
                    if len(parts) == 3 and parts[0] == 'items' and parts[2] == 'publish':
                        return self.send_json(501, {'error': 'Facebook Marketplace publishing is not connected. No listing was published.'})
                self.send_json(404, {'error': 'Route not found'})
            except LookupError:
                self.send_json(404, {'error': 'Item or required field not found'})
            except (ValueError, UnicodeError, csv.Error):
                self.send_json(400, {'error': 'Invalid input. Check prices, title, and request format.'})
    return Handler


def main():
    token = os.environ.get('RESELL_API_TOKEN', '')
    if len(token) < 32:
        raise SystemExit('Set RESELL_API_TOKEN to a securely generated value of at least 32 characters.')
    path = Path(os.environ.get('RESELL_DB_PATH', 'data/inventory.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((os.environ.get('HOST', '127.0.0.1'), int(os.environ.get('PORT', '8080'))), make_handler(Store(path), token))
    server.serve_forever()


if __name__ == '__main__':
    main()
