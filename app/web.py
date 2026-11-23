from fractions import Fraction

from flask import Blueprint,render_template,request

from app.api import cabinet,recall_book
from app.config import RULE_VERSION
from app.errors import RoastError
from app.modules.proof.recall import recall
from app.modules.proof.service import verify_and_export
from app.modules.recall.scope import assess
from app.pipeline import compute
from app.reasons import REASONS
from app.source import receive

station=Blueprint('roast_station',__name__)
PANELS={'balance':'重量守恒追溯','weighins':'批次秤单采信','supply':'投入来源核验','lineage':'拼批图比例传递',
        'packing':'灌装与返料归并','runs':'批次留档复跑','proof':'配方证据签发','recall':'产地批召回联'}
DEST={'pack':'灌装','loss':'损耗','return':'返料'}
RECALL_STATES={'confirmed':'确认涉及','pending':'尚待排除','released':'可放行','drawn':'已投下游'}


def mass(value):
    if value is None:
        return '待证'
    amount=Fraction(value)
    return str(amount) if amount.denominator==1 else f'{float(amount):.3f}'.rstrip('0').rstrip('.')


@station.get('/')
@station.get('/ledger/<view>')
def counter(view='balance'):
    if view not in PANELS:
        raise RoastError('NO_PHASE','找不到该复核页',404)
    sample=request.args.get('sample','dirty')
    key=request.args.get('run')
    document=cabinet().read(key) if key else None
    reports=document['reports'] if document else compute(receive({'sample':sample}))
    work=request.args.get('work') or next(iter(reports['supply']['jobs']))
    if work not in reports['supply']['jobs']:
        raise RoastError('NO_WORK','找不到该工作批',404)
    proof=verify_and_export(document) if document and view=='proof' else None
    packages=proof['packages'] if proof else recall(reports) if view=='proof' else {}
    scope=active=recalls=None
    if view=='recall':
        book=recall_book()
        recall_id=request.args.get('recall','')
        active=book.read(recall_id) if recall_id else None
        origin=request.args.get('origin') or (active['origin'] if active else '')
        if origin not in reports['supply']['origins']:
            origin=next(iter(reports['supply']['origins']))
        scope=assess(reports,origin)
        recalls=book.recent()
    return render_template('base.html',view=view,panels=PANELS,records=reports,codebook=REASONS, sample=sample, key=key,
                           manifest=document['manifest'] if document else None, work=work, rule=RULE_VERSION,
                           proof=proof,packages=packages,dest=DEST,mass=mass,
                           recall_scope=scope,active_recall=active,recalls=recalls,recall_states=RECALL_STATES,
                           history=cabinet().recent() if view=='runs' else [])
