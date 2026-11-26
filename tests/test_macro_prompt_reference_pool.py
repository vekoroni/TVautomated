import copy
from contracts.macro_prompt_projection import deduplicate, encode, columnar_records


def expand(document):
    def dereference(pointer):
        target=document
        for key in pointer[2:].split('/'):
            key=key.replace('~1','/').replace('~0','~')
            target=target[int(key)] if isinstance(target,list) else target[key]
        return walk(target)
    def walk(value):
        if isinstance(value,dict):
            if set(value)=={'$ref'}:return dereference(value['$ref'])
            return {k:walk(v) for k,v in value.items()}
        if isinstance(value,list):return [walk(v) for v in value]
        return value
    return walk(document['document']) if set(document)=={'defs','document'} else walk(document)


def test_short_reference_pool_is_lossless_and_preserves_unknowns_and_risks():
    shared={'observation':'source-specific observation '*15,'counterevidence':'risk '*35,
            'unknown':None,'zero':0,'false':False,'quote_clock':'2026-11-25T19:03:04Z'}
    document={'sources':{'long_repeated_evidence_namespace_'+str(i):{
        'deep_context':{'row_'+str(j):dict(shared,unique_measurement=i*40+j)
                        for j in range(40)}} for i in range(25)}}
    frozen=copy.deepcopy(document)
    encoded=deduplicate(document)
    assert 'defs' in encoded
    assert expand(encoded)==document==frozen
    assert len(encode(encoded)) < len(encode(document))*.75
    for index,definition in enumerate(encoded['defs']):
        def check(value):
            if isinstance(value,dict):
                if set(value)=={'$ref'}:
                    assert int(value['$ref'].rsplit('/',1)[1]) < index
                else:
                    for child in value.values():check(child)
            elif isinstance(value,list):
                for child in value:check(child)
        check(definition)


def test_existing_small_reference_layout_and_columnar_semantics_remain():
    shared={'note':'evidence '*100}
    value={'first':shared,'again':shared}
    packed=deduplicate(value)
    assert packed['again']=={'$ref':'#/first'}
    assert expand(packed)==value
    rows=[{'id':i,'actual':None} for i in range(5)]
    packed=columnar_records(rows)
    assert [dict(zip(packed['columns'],row)) for row in packed['rows']]==rows
