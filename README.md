# Reselling assistant — initial service

A Python 3.12+ inventory API for a resale assistant. No third-party packages are required.

**Status:** local development service implemented. Not deployed, not connected to ChatGPT,
Facebook, or Nellis. This is a foundation, not an autonomous Marketplace agent.

## Run and test

From this checkout:

```sh
python -m unittest discover -s tests -v
python run.py
```

The server binds to loopback port 8080. `GET /health` returns `{"status":"ok"}`.
Other endpoints require `Authorization: Bearer <token>`.
`run.py` creates a random token in ignored `data/api-token` with owner-only permissions
on POSIX systems; it never prints the token. Do not upload that file or paste it into chat.
Set `RESELL_API_TOKEN` in your host's secret settings to override the local token.
Database files live in ignored `data/`. Back up this directory securely.

## API

| Method | Route | Behavior |
|---|---|---|
| GET | /health | Public health check |
| GET | /integrations | Reports unsupported/unconnected account integrations |
| GET | /items | Lists inventory, prices stored as integer cents |
| POST | /items | Adds an item from JSON |
| POST | /imports/csv | Imports CSV atomically; each upload adds new items |
| GET | /items/{id}/draft | Returns supplied facts and asking price for manual review |
| POST | /items/{id}/price | JSON `{"asking_price":"40.00"}`; inventory only, audited |
| POST | /items/{id}/publish | Returns 501; no Facebook action occurs |

Item JSON and CSV use `title`, `description`, `cost`, `asking_price`, and `source_url`.
Only `title` is required. Missing monetary fields default to zero; review before posting.
Use decimal dollar amounts, without currency symbols. Reimporting duplicates rows.
Descriptions preserve user-supplied facts; this service does not infer condition or generate
AI copy. Image ingestion and natural-language command handling are not implemented yet.

Example CSV:

```csv
title,description,cost,asking_price,source_url
Desk lamp,Used; condition needs inspection,12.50,30.00,
```

## Always-on cloud deployment

GitHub stores code; it does not run this API continuously. An always-on host is required
for work while your home computer is off. No provider or hosting account is connected yet.

For a single-instance host, use Python 3.12+, set a strong `RESELL_API_TOKEN` through its
secret manager, mount a private persistent volume, and set `RESELL_DB_PATH` to a SQLite
file on that volume. Run `python app.py`. Set `HOST=0.0.0.0` only behind a managed HTTPS
proxy, with `PORT` matching the hosting platform. Restrict access, configure request
timeouts/rate limits at the proxy, and back up the database. The built-in HTTP server is
for development; review the production serving stack before public exposure. Do not
expose the development port directly to the Internet. No hosting deployment was tested.

A later chat integration must expose authenticated tools (for example a supported remote
MCP server) that call this API. A local stdio MCP adapter is included below; a hosted remote adapter is not yet
implemented, so commands in ChatGPT.com cannot currently reach this service.

## Facebook and Nellis connection

There is no Facebook login flow in this version. Do not supply Facebook passwords,
session cookies, or browser profiles to this service. A Meta login button alone would
not grant permission to edit personal Marketplace listings or share to buy/sell groups.
Direct publishing needs verified platform-supported capabilities, appropriate permissions,
and any required app review. No supported Marketplace/group connector has been verified.
Do not present a local price change as an update to a live Facebook listing.

Nellis account browsing is also unimplemented. CSV import is available now; its schema is
our own and is not claimed to match a Nellis export. A supported Nellis API or a permitted,
secure browser workflow must be investigated before unattended purchase retrieval.

## Next work

1. Connect a hosting account and deploy with persistent storage and HTTPS.
2. Add a supported authenticated chat tool adapter and verify it from the intended chat.
3. Verify Nellis account-access options and Facebook Marketplace/group capabilities.
4. Add photo ingestion, AI drafting, and live price edits only where integrations support them.

## Local MCP tools for Codex

A stdio MCP adapter is included for clients that support local MCP servers. Configure it
on the machine where this repository lives. For this cloud checkout, the command is
`python` with argument `/workspace/Reselling-/mcp_server.py`. A local Windows installation
needs its own checkout path and installed Python; this path won't exist on your PC.

Example Codex TOML configuration (merge into your existing settings; don't overwrite them):

```toml
[mcp_servers.reselling_inventory]
command = "python"
args = ["/workspace/Reselling-/mcp_server.py"]
```

Tools: `list_inventory`, `add_inventory_item`, `prepare_listing`, and
`change_inventory_price`. The last tool changes inventory only, never Facebook.
The MCP process accesses the local database directly and needs no HTTP token.
Only grant this process to trusted clients. Stdio protocol tests pass, but an actual
Codex client connection has not been verified. This is not a remote ChatGPT connector:
ChatGPT.com would need a hosted, authenticated MCP transport, which is not implemented.
