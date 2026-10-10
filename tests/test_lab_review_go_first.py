"""GO display priority is global across pages; source ranks/verdicts stay intact."""
from copy import deepcopy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from contracts.lab_review_projection import publish_review_projection,read_review_rows

def test_go_then_limit_order_is_global_and_keeps_other_source_order(tmp_path):
    rows=[{'ticker':'REVIEW','lab_verdict':'MANUAL_REVIEW','lab_rank':1,'sector':'Technology'},
          {'ticker':'LIMIT2','lab_verdict':'GO_LIMIT','lab_rank':9,'sector':'Technology'},
          {'ticker':'GO2','lab_verdict':'GO','lab_rank':8,'sector':'Energy'},
          {'ticker':'BLOCK','lab_verdict':'BLOCKED','lab_rank':2,'sector':'Technology'},
          {'ticker':'GO1','lab_verdict':'GO','lab_rank':4,'sector':'Technology'},
          {'ticker':'LIMIT1','lab_verdict':'GO_LIMIT','lab_rank':3,'sector':'Technology'}]
    b={'run_id':'TEST','candidate_count':len(rows),'rows':rows};original=deepcopy(b)
    publish_review_projection(b,tmp_path)
    result=[]
    for page in range(1,4):result.extend(read_review_rows(tmp_path,'TEST',page=page,page_size=2)['rows'])
    assert [r['ticker'] for r in result]==['GO1','GO2','LIMIT1','LIMIT2','REVIEW','BLOCK']
    assert {r['ticker']:r['lab_rank'] for r in result}=={r['ticker']:r['lab_rank'] for r in rows}
    assert b==original
    filtered=read_review_rows(tmp_path,'TEST',sector='Information Technology')
    assert [r['ticker'] for r in filtered['rows']]==['GO1','LIMIT1','LIMIT2','REVIEW','BLOCK']
    assert filtered['order_basis']=='GO_THEN_LIMIT_PUBLISHED_RANK'
