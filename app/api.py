from flask import Blueprint,current_app,jsonify,request

from app.errors import RoastError
from app.modules.proof.service import verify_and_export
from app.modules.recall.service import register,summarize
from app.modules.runs.service import seal_run
from app.pipeline import PHASES,compute
from app.source import receive

api=Blueprint('roast_api',__name__,url_prefix='/api')


def cabinet():
    return current_app.extensions['lot_cabinet']


def recall_book():
    return current_app.extensions['recall_book']


@api.route('/lots/<phase>',methods=['GET','POST'])
def check(phase):
    if phase not in PHASES:
        raise RoastError('NO_PHASE','未知称签模块',404)
    run=request.args.get('run')
    if request.method=='GET' and run:
        result=cabinet().read(run)['reports']
    else:
        body=request.get_json(silent=True) if request.method=='POST' else {'sample':request.args.get('sample','dirty')}
        result=compute(receive(body),phase)
    return jsonify(result[phase])


@api.get('/runs')
def files():
    return jsonify(runs=cabinet().recent())


@api.post('/runs')
def new_run():
    result=seal_run(cabinet(),receive(request.get_json(silent=True)))
    return jsonify(result),200 if result['reused'] else 201


@api.get('/runs/<key>')
def original(key):
    data=cabinet().read(key)
    return jsonify(id=key,manifest=data['manifest'],balance=data['reports']['balance'])


@api.post('/runs/<key>/rerun')
def rerun(key):
    old=cabinet().read(key)
    return jsonify(seal_run(cabinet(),old['files'],old['manifest']))


@api.get('/export/<key>')
def export(key):
    proof=verify_and_export(cabinet().read(key))
    response=jsonify(proof)
    response.headers['Content-Disposition']=f'attachment; filename="roast-proof-{key[:12]}.json"'
    return response


@api.get('/recalls')
def recalls():
    return jsonify(recalls=[summarize(row) for row in recall_book().recent()])


@api.post('/recalls')
def new_recall():
    body=request.get_json(silent=True)
    if not isinstance(body,dict):
        raise RoastError('BAD_INPUT','请提交召回登记信息')
    run=body.get('run')
    origin=body.get('origin')
    reference=body.get('reference','')
    if not isinstance(run,str) or not isinstance(origin,str) or not origin.strip():
        raise RoastError('BAD_INPUT','召回需指明归档与产地批')
    if not isinstance(reference,str) or len(reference.strip())>120:
        raise RoastError('BAD_INPUT','召回文号格式有误')
    result=register(recall_book(),cabinet().read(run),run,origin.strip(),reference.strip())
    return jsonify(result),201 if result['created'] else 200


@api.get('/recalls/<key>')
def recall_record(key):
    return jsonify(recall_book().read(key))
