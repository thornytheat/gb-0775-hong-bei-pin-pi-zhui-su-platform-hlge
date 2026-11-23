import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from app.errors import RoastError
from app.modules.runs.fingerprint import encode

KEY = re.compile(r'[a-f0-9]{64}\Z')


class RecallBook:
    def __init__(self, directory):
        self.path=Path(directory)
        self.path.mkdir(parents=True,exist_ok=True)
        self.lock=Lock()

    def read(self, key):
        try:
            if not KEY.fullmatch(key):
                raise FileNotFoundError()
            return json.loads((self.path / f'{key}.json').read_text(encoding='utf-8'))
        except FileNotFoundError as exc:
            raise RoastError('NO_RECALL','召回记录不存在',404) from exc
        except (json.JSONDecodeError,UnicodeError) as exc:
            raise RoastError('DAMAGED_RECALL','召回记录不可读',409) from exc

    def publish(self, record):
        final=self.path / f"{record['id']}.json"
        part=None
        try:
            with NamedTemporaryFile(mode='w',encoding='utf-8',dir=self.path,prefix='.pending-',delete=False) as stream:
                part=Path(stream.name)
                stream.write(encode(record))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(part,final)
        finally:
            if part is not None:
                part.unlink(missing_ok=True)

    def recent(self, limit=30):
        entries=[]
        for file in self.path.glob('*.json'):
            if KEY.fullmatch(file.stem):
                entries.append((file.stat().st_mtime_ns,file.stem))
        return [self.read(key) for _,key in sorted(entries,reverse=True)[:limit]]
