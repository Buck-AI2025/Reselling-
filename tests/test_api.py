import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import Store, make_handler


class API(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'inventory.db'
        self.store = Store(self.db)
        self.token = 'test-token-' * 4
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store, self.token))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, data=None, auth=True, csv=False):
        headers = {'Authorization': 'Bearer ' + self.token} if auth else {}
        if data is not None:
            headers['Content-Type'] = 'text/csv' if csv else 'application/json'
            data = data.encode() if csv else json.dumps(data).encode()
        request = Request(f'http://127.0.0.1:{self.server.server_port}{path}', data=data, headers=headers)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_purchase_to_draft_and_price_persists(self):
        code, body = self.request('/imports/csv', 'title,description,cost,asking_price\nLamp,Used; inspect shade,12.50,30\n', csv=True)
        self.assertEqual(code, 201)
        item_id = body['item_ids'][0]
        code, draft = self.request(f'/items/{item_id}/draft')
        self.assertEqual(code, 200)
        self.assertEqual(draft['description'], 'Used; inspect shade')
        self.assertFalse(draft['published'])
        code, result = self.request(f'/items/{item_id}/price', {'asking_price': '25.99'})
        self.assertEqual(code, 200)
        self.assertFalse(result['facebook_updated'])
        self.assertEqual(Store(self.db).items()[0]['asking_cents'], 2599)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 1)

    def test_auth_and_no_fake_publishing(self):
        self.assertEqual(self.request('/items', auth=False)[0], 401)
        self.assertEqual(self.request('/health', auth=False)[0], 200)
        self.assertFalse(self.request('/integrations')[1]['facebook']['connected'])
        self.assertEqual(self.request('/items/1/publish', {})[0], 501)

    def test_import_is_atomic_and_prices_validated(self):
        self.assertEqual(self.request('/imports/csv', 'title,asking_price\nValid,20\nBad,-1\n', csv=True)[0], 400)
        self.assertEqual(self.store.items(), [])
        for value in ['NaN', 'Infinity', '-1', '1.234']:
            self.assertEqual(self.request('/items', {'title': 'Invalid', 'asking_price': value})[0], 400)
        self.assertEqual(self.request('/items', {'title': 'Valid', 'asking_price': '1.20'})[0], 201)
        self.assertEqual(self.request('/items/999/price', {'asking_price': 3})[0], 404)


if __name__ == '__main__':
    unittest.main()
