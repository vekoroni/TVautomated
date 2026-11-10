import hashlib
import pytest
from contracts.macro_preview_checkpoint import merge_preview_frame

RAW=b'{\n  "x": 1\n}\n'
IDENTITY={'source_chat':'producer','source_message':'message',
          'expected_sha256':hashlib.sha256(RAW).hexdigest(),'expected_bytes':len(RAW)}
ROWS=[[1,'{'],[2,'  "x": 1'],[3,'}'],[4,'\n']]
def frame(rows,last=4):return dict(IDENTITY,lines=rows,last_line=last)

def test_overlapping_frames_resume_without_losing_earlier_lines():
    p=merge_preview_frame({},frame(ROWS[1:3]))
    assert p['missing_ranges']==[[1,1],[4,4]]
    p=merge_preview_frame(p,frame(ROWS[:2]))
    assert p['captured_lines']==3 and p['status']=='INCOMPLETE'
    assert merge_preview_frame(p,frame(ROWS[2:]))['status']=='COMPLETE'

def test_complete_capture_requires_original_checksum_and_byte_length():
    assert merge_preview_frame({},frame(ROWS))['status']=='COMPLETE'
    wrong=frame(ROWS);wrong['expected_sha256']='0'*64
    with pytest.raises(ValueError,match='CHECKSUM'):merge_preview_frame({},wrong)

def test_conflicts_and_identity_changes_do_not_mutate_checkpoint():
    p=merge_preview_frame({},frame(ROWS[:1]));before=repr(p)
    with pytest.raises(ValueError,match='CONFLICTING'):merge_preview_frame(p,frame([[1,'}']]))
    changed=frame(ROWS[1:]);changed['source_message']='other'
    with pytest.raises(ValueError,match='IDENTITY'):merge_preview_frame(p,changed)
    assert repr(p)==before

def test_stagnation_is_visible_not_infinite_success():
    p=merge_preview_frame({},frame(ROWS[:1]))
    for _ in range(3):p=merge_preview_frame(p,frame(ROWS[:1]))
    assert p['status']=='STOPPED_NO_PROGRESS'
    assert merge_preview_frame(p,frame(ROWS[1:2]))['no_progress_runs']==0

@pytest.mark.parametrize('rows',[[[True,'x']],[[0,'x']],[[100,'x']],[[1,None]]])
def test_invalid_lines_fail_closed(rows):
    with pytest.raises(ValueError):merge_preview_frame({},frame(rows))

def test_terminal_change_and_oversize_fail_closed():
    p=merge_preview_frame({},frame(ROWS[:1]))
    with pytest.raises(ValueError,match='TERMINAL'):merge_preview_frame(p,frame([],last=3))
    with pytest.raises(ValueError,match='BYTE_LENGTH'):merge_preview_frame({},frame(ROWS),max_bytes=2)
