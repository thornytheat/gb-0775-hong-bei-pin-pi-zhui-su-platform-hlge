from fractions import Fraction

from app.errors import RoastError

UNKNOWN='UNKNOWN'


def _ticket_source(row):
    kind=row.get('source_kind')
    source=row.get('source')
    if kind in ('origin','return') and source:
        return kind,source
    raw=row.get('raw')
    if isinstance(raw,dict):
        kind=raw.get('source_kind')
        source=(raw.get('source') or '').strip()
        if kind in ('origin','return') and source:
            return kind,source
    return None


def _possible_sets(supply, lineage):
    jobs=lineage['jobs']
    coupons=supply['return_lots']
    origins=supply['origins']
    memo={}

    def visit(work, stack):
        if work in memo:
            return memo[work]
        job=jobs[work]
        if not job['codes']:
            memo[work]=frozenset(job['composition_g'])
            return memo[work]
        if work in stack:
            return frozenset({UNKNOWN})
        found=set()
        identifiable=Fraction()
        for row in [*job['reported_inputs'],*(r for r in job['input_issues'] if r.get('sheet')=='inputs')]:
            source=_ticket_source(row)
            if source is None:
                found.add(UNKNOWN)
            elif source[0]=='origin':
                found.add(source[1] if source[1] in origins else UNKNOWN)
            elif source[1] in coupons:
                found|=visit(coupons[source[1]]['work'],stack|{work})
            else:
                found.add(UNKNOWN)
            if 'g' in row:
                identifiable+=Fraction(row['g'])
        codes=set(job['codes'])
        if codes&{'OUTPUT_DISPUTE','NEGATIVE_REMAINDER'}:
            found.add(UNKNOWN)
        if 'INTAKE_MISMATCH' in codes and identifiable<Fraction(job['input_g']):
            found.add(UNKNOWN)
        memo[work]=frozenset(found)
        return memo[work]

    return {work:visit(work,frozenset()) for work in jobs}


def assess(reports, origin):
    supply=reports['supply']
    if origin not in supply['origins']:
        raise RoastError('NO_ORIGIN','该产地批未登记',404)
    lineage=reports['lineage']
    packing=reports['packing']
    warehouse=reports['balance']['warehouse']
    possible=_possible_sets(supply,lineage)

    def implicated(work):
        marks=possible[work]
        return origin in marks or UNKNOWN in marks

    packages={}
    for key,row in packing['outputs'].items():
        if row['kind']!='pack':
            continue
        if row['status']=='certified':
            grams=Fraction(row['origin_g'].get(origin,'0'))
            status='confirmed' if grams else 'released'
            basis='构成已核' if grams else '构成已核·不含该产地'
            origin_g=str(grams)
        elif implicated(row['work']):
            status,basis,origin_g='pending','来路待证',None
        else:
            status,basis,origin_g='released','来路已排清·批仍待证',None
        packages[key]=dict(work=row['work'],net_g=row['g'],origin_g=origin_g,status=status,basis=basis,line=row['line'])
    returns={}
    for key,row in packing['returns'].items():
        if row['available_g'] is None:
            stock=Fraction(row['g'])-Fraction(row['drawn_g'])
            if implicated(row['work']):
                status,basis,origin_g='pending','来源待证',None
            else:
                status,basis,origin_g='released','来路已排清',None
        else:
            stock=Fraction(row['available_g'])
            grams=Fraction(row['remaining_origin_g'].get(origin,'0'))
            origin_g=str(grams)
            if not stock:
                status,basis='drawn','已投下游·不算余料'
            elif grams:
                status,basis='confirmed','构成已核'
            else:
                status,basis='released','构成已核·不含该产地'
        returns[key]=dict(work=row['work'],net_g=row['g'],drawn_g=row['drawn_g'],stock_g=str(stock),
                          origin_g=origin_g,status=status,basis=basis,line=row['line'])
    jobs={}
    for work,row in packing['jobs'].items():
        hold=Fraction(row['hold_g'])
        pending=Fraction(row['pending_g'])
        if pending:
            status='pending' if implicated(work) else 'released'
            jobs[work]=dict(label=supply['jobs'][work]['label'],hold_g='0',pending_g=row['pending_g'],origin_g=None,
                            status=status,basis='来路待证' if status=='pending' else '来路已排清',
                            codes=lineage['jobs'][work]['codes'])
        elif hold:
            grams=Fraction(row['hold_origin_g'].get(origin,'0'))
            jobs[work]=dict(label=supply['jobs'][work]['label'],hold_g=row['hold_g'],pending_g='0',origin_g=str(grams),
                            status='confirmed' if grams else 'released',basis='构成已核',codes=[])
    def bucket(status):
        rows=[row for row in packages.values() if row['status']==status]
        return dict(count=len(rows),net_g=str(sum((Fraction(row['net_g']) for row in rows),Fraction())))
    totals={status:bucket(status) for status in ('confirmed','pending','released')}
    totals['confirmed']['origin_g']=str(sum((Fraction(row['origin_g']) for row in packages.values()
                                             if row['status']=='confirmed'),Fraction()))
    account=warehouse['origins'].get(origin,{'used_g':'0','distributed_g':'0'})
    used=Fraction(account['used_g'])
    distributed=Fraction(account['distributed_g'])
    pack_o=sum((Fraction(row['origin_g']) for row in packages.values() if row['origin_g'] is not None),Fraction())
    loss_o=sum((Fraction(row['origin_g'].get(origin,'0')) for row in packing['outputs'].values()
                if row['kind']=='loss' and row['status']=='certified'),Fraction())
    hold_o=sum((Fraction(row['origin_g']) for row in jobs.values() if row['origin_g'] is not None),Fraction())
    return_o=sum((Fraction(row['origin_g']) for row in returns.values() if row['origin_g'] is not None),Fraction())
    detained=hold_o+return_o
    warehouse_stock=distributed-pack_o-loss_o
    stock_delta=detained-warehouse_stock
    flow_delta=used-pack_o-loss_o-detained
    detained_physical=sum((Fraction(row['stock_g']) for row in returns.values() if row['status']=='confirmed'),Fraction())
    detained_physical+=sum((Fraction(row['hold_g']) for row in jobs.values() if row['status']=='confirmed'),Fraction())
    pending_stock=sum((Fraction(row['stock_g']) for row in returns.values() if row['status']=='pending'),Fraction())
    pending_stock+=sum((Fraction(row['pending_g']) for row in jobs.values() if row['status']=='pending'),Fraction())
    reconcile=dict(origin_used_g=str(used),confirmed_pack_origin_g=str(pack_o),loss_origin_g=str(loss_o),
                   detained_stock_origin_g=str(detained),warehouse_stock_origin_g=str(warehouse_stock),
                   stock_delta_g=str(stock_delta),flow_delta_g=str(flow_delta),
                   detained_stock_g=str(detained_physical),pending_stock_g=str(pending_stock),
                   balanced=stock_delta==0 and flow_delta==0)
    return dict(origin=origin,label=supply['origins'][origin]['label'],
                packages=packages,returns=returns,jobs=jobs,totals=totals,reconcile=reconcile)
