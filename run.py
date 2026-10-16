"""Local startup helper. Keeps generated authentication outside tracked files."""
import os
from pathlib import Path
import secrets
from app import main

if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    os.chdir(root)
    if not os.environ.get('RESELL_API_TOKEN'):
        directory = root / 'data'
        directory.mkdir(mode=0o700, exist_ok=True)
        token_file = directory / 'api-token'
        try:
            fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'w') as stream:
                stream.write(secrets.token_urlsafe(48))
        os.environ['RESELL_API_TOKEN'] = token_file.read_text().strip()
    main()
