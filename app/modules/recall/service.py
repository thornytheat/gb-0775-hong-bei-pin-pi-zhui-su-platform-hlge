from datetime import UTC,datetime

from app.config import RULE_VERSION
from app.errors import RoastError
from app.modules.runs.fingerprint import checksum,encode

from .scope import assess


def _now():
    return datetime.now(UTC).isoformat(timespec='seconds')


def recall_key(origin, reference):
    return checksum(encode([RULE_VERSION,'recall',origin,reference]))


def register(book, document, run, origin, reference=''):
    scope=assess(document['reports'],origin)
    key=recall_key(origin,reference)
    with book.lock:
        try:
            record=book.read(key)
        except RoastError as error:
            if error.code!='NO_RECALL':
                raise
            record=None
        if record is not None and any(row['run']==run for row in record['assessments']):
            return dict(id=key,reused=True,created=False,recall=record)
        created=record is None
        if created:
            record=dict(id=key,origin=origin,label=scope['label'],reference=reference,
                        registered_at=_now(),assessments=[])
        record['assessments'].append(dict(run=run,assessed_at=_now(),scope=scope))
        book.publish(record)
        return dict(id=key,reused=False,created=created,recall=record)


def summarize(record):
    latest=record['assessments'][-1]
    return dict(id=record['id'],origin=record['origin'],label=record['label'],reference=record['reference'],
                registered_at=record['registered_at'],assessments=len(record['assessments']),
                run=latest['run'],assessed_at=latest['assessed_at'])
