"""Dataset integrity/negative tests. These never open real candidate Test resources."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.final_phase2 import grade_submission
from benchmarks.phase2_registry import (
    EXPECTED, ROOT, digest, duplicate_candidates, file_digest, grade_rows, load_tasks,
    near_questions, read_json, validate_catalog, validate_reference, text_digest, enforce_freeze,
    validate_grading_rule,
)


def catalog():
    return read_json(ROOT/'tasks.json'),read_json(ROOT/'sources.json')


def test_public_freeze_and_historical_hashes():
    tasks,sources=catalog()
    manifest=read_json(ROOT/'manifest.json')
    for name,checksum in manifest['files'].items():
        assert file_digest(ROOT/name)==checksum,name
    for name,checksum in manifest['historical_files'].items():
        assert text_digest(ROOT.parents[1]/name)==checksum,name
    refs={**read_json(ROOT/'development.references.json'),**read_json(ROOT/'validation.references.json')}
    result=validate_catalog(tasks,sources,refs)
    assert result['counts']==EXPECTED==manifest['counts']
    assert result['unique_ids']==397
    assert result['databench_databases']=={'development':11,'validation':4,'test':6}
    assert sum(t['legacy'] for t in tasks)==197
    assert manifest['status']=='FROZEN_CANDIDATE_NOT_BLIND'


def test_exposed_official_ids_exactly_preserved():
    tasks,_=catalog()
    expected=set()
    for filename in ('databench-subset.json','databench-dev-subset.json','databench-holdout.json'):
        for table in read_json(ROOT.parents[1]/'docs'/filename)['tables'].values():
            expected.update(table['question_ids'])
    actual={t['official_question_id'] for t in tasks if t['dataset']=='databench' and t['legacy']}
    assert actual==expected and len(actual)==152


@pytest.mark.parametrize('mutation,match',[
    ('id','Duplicate task ID'),('database','database crosses'),
    ('question','Question crosses'),('template','template crosses'),
    ('gold','must be withheld'),('source','Unknown source'),
])
def test_catalog_rejects_leakage(mutation,match):
    tasks,sources=catalog()
    dev=next(t for t in tasks if t['dataset']=='databench' and t['split']=='development')
    test=next(t for t in tasks if t['dataset']=='databench' and t['split']=='test')
    if mutation=='id':
        test['task_id']=dev['task_id']
    elif mutation=='database':
        test['database_id']=dev['database_id']
    elif mutation=='question':
        test['question_sha256']=dev['question_sha256']
    elif mutation=='template':
        test['semantic_template_id']=dev['semantic_template_id']
    elif mutation=='gold':
        test['question']='accidental test content'
    else:
        test['source_version']='unversioned'
    with pytest.raises(ValueError,match=match):
        validate_catalog(tasks,sources,complete=False)


def test_development_loaders_never_open_protected_files(monkeypatch):
    original=Path.read_text
    opened=[]
    def guarded(path,*args,**kwargs):
        opened.append(path.name)
        assert path.name not in {'test.tasks.json','test.references.json','olist-test-authoring.json'}
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',guarded)
    assert len(load_tasks('development'))==237
    assert len(load_tasks('validation'))==60
    before=list(opened)
    with pytest.raises(ValueError,match='owner-controlled'):
        load_tasks('test')
    assert opened==before


def test_public_test_records_are_metadata_only():
    tasks,_=catalog()
    for task in tasks:
        if task['split']=='test':
            assert task['question'] is None
            assert task['reference']['resource']=='OWNER_CONTROLLED'
            assert 'business_definition' not in task
            assert not {'sql','rows','answer','criteria'} & task.keys()
            assert 'criteria' not in task['grading_rule']
    dev=load_tasks('development')
    val=load_tasks('validation')
    assert not [d for d in duplicate_candidates(dev+val) if d['cross_split']]


def test_near_duplicate_screen_masks_literals_and_numbers():
    assert near_questions('How many orders in 2017-03 from SP?', 'How many orders in 2018-06 from SP?')
    assert near_questions("Total price for category 'health'?", "Total price for category 'bed'?")
    assert not near_questions('Median observed delivery days?', 'How many unique sellers had items?')


def test_historical_text_hash_survives_cross_platform_checkout(tmp_path):
    a,b=tmp_path/'lf.json',tmp_path/'crlf.json'
    a.write_bytes(b'{\n}\n')
    b.write_bytes(b'{\r\n}\r\n')
    assert text_digest(a)==text_digest(b)
    assert file_digest(a)!=file_digest(b)


def test_freeze_cannot_silently_rewrite_gold_or_split():
    previous={'release':'v1','files':{'catalog':'old'},'protected_test_files':{'gold':'old'}}
    enforce_freeze(previous,{'catalog':'old'},{'gold':'old'},'v1')
    with pytest.raises(ValueError,match='new --release'):
        enforce_freeze(previous,{'catalog':'old'},{'gold':'changed'},'v1')
    with pytest.raises(ValueError,match='new --release'):
        enforce_freeze(previous,{'catalog':'changed'},{'gold':'old'},'v1')
    enforce_freeze(previous,{'catalog':'changed'},{'gold':'old'},'v2')


def test_reference_completeness_and_approval_status():
    task=load_tasks('validation')[0]
    with pytest.raises(ValueError,match='materialized rows'):
        validate_reference(task,{'sql':'SELECT 1'})
    task['grading_rule']={'kind':'human_rubric'}
    with pytest.raises(ValueError,match='three nonempty'):
        validate_reference(task,{'criteria':['one']})
    with pytest.raises(ValueError,match='await human'):
        validate_reference(task,{'criteria':['one','two','three']})


def test_protected_metadata_still_requires_complete_grading_rules():
    tasks,_=catalog()
    task=next(t for t in tasks if t['split']=='test' and t['dataset']=='olist')
    task['grading_rule']={}
    with pytest.raises(ValueError,match='Unknown grading contract'):
        validate_grading_rule(task)


def test_new_grader_preserves_units_nulls_and_exact_counts():
    ref={'rows':[[{'decimal':'2437930.80'},None,True,7]]}
    rule={'absolute_tolerance':'0.000001'}
    assert grade_rows([[Decimal('2437930.80'),None,True,7]],ref,rule)
    assert not grade_rows([[Decimal('2437930.81'),None,True,7]],ref,rule)
    assert not grade_rows([[Decimal('2437930.80'),0,True,7]],ref,rule)
    assert not grade_rows([[Decimal('2437930.80'),None,1,7]],ref,rule)
    assert not grade_rows([[Decimal('2437930.80'),None,True,8]],ref,rule)
    assert not grade_rows([[float('nan')]],{'rows':[[1]]},rule)
    assert grade_rows([],{'rows':[]},rule)
    assert not grade_rows([[None]],{'rows':[]},rule)


def test_final_grader_synthetic_only_and_no_false_rubric_pass():
    tasks=[{'task_id':'synthetic:1','reference':{'rows':[[2]]},
            'grading_rule':{'kind':'rows','absolute_tolerance':'0'}},
           {'task_id':'synthetic:2','reference':{'criteria':['a','b','c']},
            'grading_rule':{'kind':'human_rubric'}}]
    result=grade_submission(tasks,[{'task_id':'synthetic:1','answer':[[2]]},
                                   {'task_id':'synthetic:2','answer':'unreviewed explanation'}])
    assert result['machine_correct']==1 and result['pending_human']==1
    assert result['status']=='INCOMPLETE_PENDING_HUMAN_GRADING'
    with pytest.raises(ValueError,match='exactly one'):
        grade_submission(tasks,[{'task_id':'synthetic:1','answer':[[2]]}]*2)


def test_official_evaluator_contract_synthetic_only():
    pytest.importorskip('databench_eval')
    from databench_eval import Evaluator
    for value,truth,semantic in ((True,'yes','boolean'),(12.345,'12.34','number'),
                                  ('alpha','alpha','category'),(['b','a'],"['a','b']",'list[category]'),
                                  ([2,1],'[1,2]','list[number]')):
        assert Evaluator.default_compare(None,value,truth,semantic)
    assert not Evaluator.default_compare(None,False,'yes','boolean')


def test_reference_gold_commitments_are_bound_to_task():
    task=load_tasks('validation')[0]
    ref=deepcopy(task['reference'])
    assert digest(ref)
    # Incorrect truth cannot pass its own original task commitment.
    public=next(t for t in read_json(ROOT/'tasks.json') if t['task_id']==task['task_id'])
    ref['rows']=[[999999999]]
    assert digest(ref)!=public['reference']['sha256']
