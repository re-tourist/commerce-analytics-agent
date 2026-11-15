"""Separate owner-controlled candidate-Test export/grading. No model execution.

An explicit path/acknowledgment is an operational boundary, not an access-control
or blindness guarantee. The project owner must supply the real access boundary.
"""

import argparse
import json
from pathlib import Path

from benchmarks.phase2_registry import (
    ROOT, digest, file_digest, grade_rows, read_json, validate_reference, write_json,
)


def load_owner_tasks(owner_root, public_root=ROOT):
    owner_root,public_root=Path(owner_root),Path(public_root)
    manifest=read_json(public_root/'manifest.json')
    for name,checksum in manifest['protected_test_files'].items():
        if file_digest(owner_root/name)!=checksum:
            raise ValueError(f'Protected resource changed: {name}')
    if file_digest(public_root/'tasks.json')!=manifest['files']['tasks.json']:
        raise ValueError('Public catalog commitment changed')
    public={t['task_id']:t for t in read_json(public_root/'tasks.json') if t['split']=='test'}
    private=read_json(owner_root/'test.tasks.json')
    refs=read_json(owner_root/'test.references.json')
    if len(private)!=len(public) or {t['task_id'] for t in private}!=set(public) or set(refs)!=set(public):
        raise ValueError('Protected task IDs differ from frozen Test')
    for t in private:
        p=public[t['task_id']]
        for key,value in p.items():
            if key=='question':
                if digest(t['question'])!=p['question_sha256']:
                    raise ValueError('Protected question commitment mismatch')
            elif key=='reference':
                if digest(refs[t['task_id']])!=value['sha256'] or t['reference']!=refs[t['task_id']]:
                    raise ValueError('Protected reference commitment mismatch')
            elif key!='question_sha256' and t.get(key)!=value:
                raise ValueError(f'Protected metadata changed: {key}')
        validate_reference(t,refs[t['task_id']])
    return private


def grade_prediction(task, value):
    kind=task['grading_rule']['kind']
    if kind=='rows':
        correct=isinstance(value,list) and all(isinstance(row,list) for row in value) and grade_rows(value,task['reference'],task['grading_rule'])
    elif kind=='official_databench':
        import importlib.metadata
        if importlib.metadata.version('databench-eval')!='4.0.1':
            raise ValueError('Official evaluator version drift')
        from databench_eval import Evaluator
        correct=bool(Evaluator.default_compare(None,value,task['reference']['answer'],task['answer_type']))
    elif kind=='human_rubric':
        return {'status':'PENDING_HUMAN_REVIEW','correct':None}
    else:
        raise ValueError('Unsupported final grading rule')
    return {'status':'MACHINE_GRADED','correct':correct}


def grade_submission(tasks, predictions):
    if len(predictions)!=len(tasks) or {p['task_id'] for p in predictions}!={t['task_id'] for t in tasks}:
        raise ValueError('Require exactly one prediction for every frozen Test task')
    indexed={p['task_id']:p for p in predictions}
    grades=[{'task_id':t['task_id'],**grade_prediction(t,indexed[t['task_id']]['answer'])} for t in tasks]
    machine=[g for g in grades if g['correct'] is not None]
    return {'status':'INCOMPLETE_PENDING_HUMAN_GRADING' if len(machine)!=len(tasks) else 'GRADED',
            'test_isolation':'FROZEN_CANDIDATE_NOT_BLIND',
            'total_tasks':len(tasks),'machine_graded':len(machine),
            'machine_correct':sum(g['correct'] for g in machine),
            'pending_human':len(tasks)-len(machine),'grades':grades}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-root',type=Path,required=True)
    parser.add_argument('--acknowledge-candidate-not-blind',action='store_true',required=True)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--export-questions',action='store_true')
    action.add_argument('--predictions',type=Path)
    args=parser.parse_args()
    tasks=load_owner_tasks(args.owner_root)
    if args.export_questions:
        # Export only questions/database identity to the locked candidate runner.
        write_json(args.owner_root/'final.questions.json',[
            {k:t[k] for k in ('task_id','dataset','database_id','question')} for t in tasks])
    else:
        write_json(args.owner_root/'final.grades.json',grade_submission(tasks,read_json(args.predictions)))


if __name__=='__main__':
    main()
