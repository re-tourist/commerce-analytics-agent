"""Owner-side, dataset-only construction of the Phase II frozen candidate.

Test authoring and QA live only under ignored local storage. This command never
imports an Agent, selects a model, or performs a model inference.
"""

import argparse
from collections import Counter
from copy import deepcopy
import csv
from datetime import date, datetime
from decimal import Decimal
import hashlib
import importlib.metadata
import io
import json
from functools import lru_cache
from pathlib import Path
from urllib.request import urlretrieve
from zipfile import ZipFile

import duckdb
import pyarrow as pa
import pyarrow.parquet as parquet
import sqlglot
from sqlglot import exp

from benchmarks.audit_olist import audit, FILES
from benchmarks.databench import SUBSET_FILES, SUBSET_ROOTS, pinned_manifest, selected_cases, verify_hash
from benchmarks.olist_cases import cases
from benchmarks.phase2_registry import (
    ROOT, canonical, digest, duplicate_candidates, file_digest, near_questions,
    normalize_question, read_json, validate_catalog, validate_reference, write_json, grade_rows, text_digest,
    artifact_bytes, enforce_freeze,
)
from benchmarks.review_olist import ABSTENTION_CHECKS, SAMPLE_DIGEST
from commercelens.infrastructure.retrieval.knowledge import DOCUMENTS
from scripts.fetch_olist import SHA256

REVISION = 'e75d53add267d2f9cfa32efd65ad77f0807adfad'
SOURCE = 'https://huggingface.co/datasets/cardiffnlp/databench'
SEED = 20261115
TYPES = ['boolean', 'number', 'category', 'list[category]', 'list[number]']
# Feasible, predeclared quotas: macro Boolean/Number/Category/List = 10 each in
# Validation and 15 each in Test. Gestational has no official Category questions.
PLAN = {
    'validation': {
        '052_Professional': [3, 2, 2, 2, 1], '053_Patents': [2, 3, 3, 1, 1],
        '054_Joe': [3, 2, 2, 1, 2], '055_German': [2, 3, 3, 1, 1],
    },
    'test': {
        '067_TripAdvisor': [2, 3, 1, 2, 2], '068_WorldBank_Awards': [2, 2, 4, 1, 1],
        '069_Taxonomy': [2, 2, 4, 1, 1], '070_OpenFoodFacts': [2, 2, 3, 2, 1],
        '077_Gestational': [4, 3, 0, 0, 3], '078_Fires': [3, 3, 3, 1, 0],
    },
}


def encode(value):
    if isinstance(value, Decimal):
        return {'decimal': str(value)}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 9)
    return value


def reference_rows(db, sql):
    return [[encode(v) for v in row] for row in db.execute(sql).fetchall()]


@lru_cache(maxsize=512)
def sql_template(sql):
    tree = sqlglot.parse_one(sql, read='duckdb')
    return digest(tree.transform(lambda node: exp.Literal.string('VALUE')
                                if isinstance(node, exp.Literal) else node).sql(dialect='duckdb'))


def require_raw_sql(sql):
    tree = sqlglot.parse_one(sql, read='duckdb')
    if not isinstance(tree, exp.Query) or len(sqlglot.parse(sql, read='duckdb')) != 1:
        raise ValueError('References must be single read queries')
    aliases = {cte.alias for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if table.db == 'source' and table.name in FILES:
            continue
        if not table.db and table.name in aliases:
            continue
        raise ValueError(f'Reference reads a non-source relation: {table.sql()}')


def archive_database(archive, retained):
    """Read publisher CSVs independently of production views and database build SQL."""
    db = duckdb.connect(':memory:', config={'threads': '1'})
    db.execute('CREATE SCHEMA source')
    hashes = {}
    with ZipFile(archive) as source:
        for table, filename in FILES.items():
            keys = {'orders': 'order_id', 'customers': 'customer_id', 'items': 'order_id',
                    'payments': 'order_id', 'reviews': 'order_id', 'products': 'product_id',
                    'sellers': 'seller_id', 'categories': 'product_category_name'}
            key = keys[table]
            permitted = {r[0] for r in retained.execute(f'SELECT DISTINCT {key} FROM source.{table}').fetchall()}
            with source.open(filename) as stream:
                reader = csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig', newline=''))
                names = reader.fieldnames
                rows = [{k: v or None for k,v in r.items()} for r in reader if r[key] in permitted]
            arrow = pa.Table.from_pylist(rows, schema=pa.schema([(n,pa.string()) for n in names]))
            db.register('publisher_rows', arrow)
            db.execute(f'CREATE TABLE source.{table} AS SELECT * FROM publisher_rows')
            db.unregister('publisher_rows')
            observed = retained.execute(f'SELECT * FROM source.{table}').fetchall()
            expected = db.execute(f'SELECT * FROM source.{table}').fetchall()
            # A canonical row-multiset commitment tolerates physical DB serialization differences.
            expected_hash = digest(sorted(expected, key=canonical))
            if digest(sorted(observed,key=canonical)) != expected_hash:
                raise ValueError(f'Archive reconstruction mismatch: {table}')
            hashes[table] = {'rows': len(expected), 'logical_sha256': expected_hash}
    db.execute("SET enable_external_access=false")
    return db, hashes


def history_task(case, db):
    if case.sql:
        ref = {'sql': case.sql, 'rows': reference_rows(db,case.sql)}
        rule = {'kind': 'legacy_olist', 'protocol': 'Phase I unchanged: benchmarks.run.score_olist',
                'ordered': case.ordered, 'absolute_relative_tolerance': '0.000001'}
        template = sql_template(case.sql)
    else:
        excerpts = {doc.id: doc.excerpt for doc in DOCUMENTS}
        criteria = ([ABSTENTION_CHECKS[case.id], 'Do not fabricate unavailable evidence or a numerical causal result.',
                     'Any descriptive proxy must be labelled and must not be passed off as the requested metric.']
                    if case.family == 'unsupported' else
                    ['Answer the requested definition using the nominated business excerpt.',
                     'State the units, grain and eligibility where relevant.',
                     'Citations must substantiate the actual answer, not merely share a topic.'])
        ref = {'criteria': criteria, 'citations': list(case.citations),
               'excerpts': {k: excerpts[k] for k in case.citations}}
        rule = {'kind':'human_rubric', 'historical_protocol':'benchmarks.run.score_olist unchanged'}
        template = digest(normalize_question(case.question))
    return {'task_id':case.id,'dataset':'olist','database_id':'olist-15000-v2','split':'development',
            'question':case.question,'task_family':case.family,'semantic_template_id':template,
            'answer_type':'table' if case.sql else 'text','difficulty':'legacy_unrated',
            'reference':ref,'grading_rule':rule,'source_version':'olist-v2-sample741',
            'review_status':'PENDING_HUMAN_REVIEW','legacy':True}


def databench_task(row, index, split, legacy=False):
    identifier=f"{row['dataset']}:{index:03}"
    q=normalize_question(row['question'])
    if any(w in q.split() for w in ('highest','lowest','top','bottom','maximum','minimum','most','least')):
        family='extremum_ranking'
    elif any(w in q.split() for w in ('average','mean','median','sum','total','many','count')):
        family='aggregation'
    elif row['type']=='boolean':
        family='predicate_comparison'
    else:
        family='lookup_selection'
    multi_extremum=row['type']=='boolean' and sum(q.count(w) for w in ('highest','lowest','maximum','minimum','most','average'))>=2
    difficulty='advanced' if multi_extremum else ('intermediate' if family in {'aggregation','extremum_ranking'} or row['type'].startswith('list[') else 'basic')
    return {'task_id':f'DB:{identifier}','official_question_id':identifier,'dataset':'databench',
            'database_id':row['dataset'],'split':split,'question':row['question'],
            'task_family':family,'semantic_template_id':digest(q),'answer_type':row['type'],
            'difficulty':difficulty,'difficulty_basis':'Static question-structure rubric; not model-calibrated or independently human approved.',
            'reference':{'answer':row['answer'],'official_type':row['type']},
            'grading_rule':{'kind':'official_databench','package':'databench-eval','version':'4.0.1'},
            'source_version':f'databench-{REVISION}','review_status':'AUTO_VERIFIED','legacy':legacy}


def source_databench(directory, table, known, fetch):
    directory.mkdir(parents=True,exist_ok=True)
    for filename in ('qa.parquet','all.parquet'):
        path=directory/filename
        if fetch and not path.exists():
            partial=path.with_suffix('.part')
            try:
                urlretrieve(f'{SOURCE}/resolve/{REVISION}/data/{table}/{filename}',partial)
                partial.replace(path)
            finally:
                partial.unlink(missing_ok=True)
        if known:
            verify_hash(path,known['files'][filename])
    rows=parquet.read_table(directory/'qa.parquet').to_pylist()
    if not rows or any(r['dataset']!=table or r['type'] not in TYPES or not r['question'] or r['answer'] is None for r in rows):
        raise ValueError(f'Malformed official QA: {table}')
    meta={'files':{n:file_digest(directory/n) for n in ('qa.parquet','all.parquet')},
          'file_bytes':{n:(directory/n).stat().st_size for n in ('qa.parquet','all.parquet')},
          'rows':parquet.read_metadata(directory/'all.parquet').num_rows,'qa_rows':len(rows),
          'schema_sha256':digest(str(parquet.read_schema(directory/'all.parquet')))}
    return rows,meta


def construct(local, test_authoring, database, archive, output=ROOT, fetch=False, release=None):
    if importlib.metadata.version('databench-eval')!='4.0.1':
        raise ValueError('Use pinned databench-eval==4.0.1')
    from databench_eval import Evaluator

    local,output=Path(local),Path(output)
    ignored_data=Path(__file__).resolve().parents[1]/'data'
    if local.resolve()==output.resolve() or not local.resolve().is_relative_to(ignored_data.resolve()):
        raise ValueError('Private construction output must remain under ignored local data storage')
    existing=read_json(output/'sources.json') if (output/'sources.json').exists() else {}
    previous_manifest=read_json(output/'manifest.json') if (output/'manifest.json').exists() else None
    release=release or (previous_manifest['release'] if previous_manifest else 'phase2-candidate-v1')
    old=audit(database,archive)  # independently checks sample selection and all eight linked tables
    write_json(local/'legacy-olist-audit.json',old)
    with duckdb.connect(str(database.resolve()),read_only=True,config={'enable_external_access':'false','threads':'1'}) as db:
        independent, table_hashes=archive_database(archive,db)
        try:
            tasks=[history_task(case,db) for case in cases()]
            new=read_json(output/'olist-development-validation.json')
            private=read_json(test_authoring)
            private=[t for t in private if t['split']=='test']
            new+=private
            if len(new)!=100:
                raise ValueError('Expected 100 authored Olist additions')
            checks=[]
            for original in new:
                t=deepcopy(original)
                t['source_version']='olist-v2-sample741'
                t['legacy']=False
                t['semantic_template_id']=digest(t['semantic_template_id'])
                sql=t['reference'].get('sql')
                if sql:
                    require_raw_sql(sql)
                    t['sql_template_sha256']=sql_template(sql)
                    t['reference']['rows']=reference_rows(db,sql)
                    rebuilt=reference_rows(independent,sql)
                    observed=[[Decimal(v['decimal']) if isinstance(v,dict) else v for v in row]
                              for row in rebuilt]
                    if not grade_rows(observed,t['reference'],t['grading_rule']):
                        raise ValueError(f"Independent source reference mismatch: {t['task_id']}")
                    # Gold is materialized from publisher-file order, on the single-thread
                    # source-only reconstruction, so retained DB physical/parallel scan
                    # order cannot perturb floating aggregate commitments.
                    t['reference']['rows']=rebuilt
                    # This verifies computation from source, not independent human interpretation.
                    checks.append({'task_id':t['task_id'],'archive_sql_match':True,
                                   'rows_sha256':digest(rebuilt),'rows':len(rebuilt)})
                else:
                    t['reference']={'criteria':t['grading_rule'].pop('criteria')}
                validate_reference(t,t['reference'])
                tasks.append(t)
        finally:
            independent.close()
    sources={'olist-v2-sample741':{'source':'https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce',
             'revision':'2','license':'CC BY-NC-SA 4.0','archive_sha256':SHA256,
             'sample_order_ids_sha256':SAMPLE_DIGEST,'sample_size':15000,'seed':741,
             'sampling':'Monthly proportional largest remainder, ties by month; lowest SHA-256(seed:order_id)',
             'source_tables':table_hashes},
             f'databench-{REVISION}':{'source':SOURCE,'revision':REVISION,'license':'MIT',
             'databases':{}}}
    databases=sources[f'databench-{REVISION}']['databases']
    history_hashes={}
    for split,filename in SUBSET_FILES.items():
        pinned=pinned_manifest(split)
        if pinned['revision']!=REVISION:
            raise ValueError('Historical revision changed')
        history_hashes[f'docs/{filename}']=text_digest(Path('docs')/filename)
        for table,rows in selected_cases(SUBSET_ROOTS[split],split).items():
            if table in databases:
                raise ValueError('Legacy tables overlap')
            _,entry=source_databench(SUBSET_ROOTS[split]/'raw'/table,table,pinned['tables'][table],False)
            entry['question_ids']=pinned['tables'][table]['question_ids']
            entry['split']='development'
            entry['official_split']='dev' if split=='dev' else 'test'
            entry['selection']={'method':pinned['sampling'],'seed':pinned['seed'],'legacy_manifest':filename}
            databases[table]=entry
            tasks.extend(databench_task(r,int(r['id'].split(':')[-1]),'development',True) for r in rows)
    if sum(t['dataset']=='databench' for t in tasks)!=152 or len(databases)!=11:
        raise ValueError('Historical DataBench cohort changed')
    skipped=[]
    known_databases=existing.get(f'databench-{REVISION}',{}).get('databases',{})
    for split,tables in PLAN.items():
        for table,quotas in tables.items():
            if table in databases:
                raise ValueError('New database was previously exposed')
            rows,entry=source_databench(local/'databench'/table,table,known_databases.get(table),fetch)
            chosen=[]
            for semantic,quota in zip(TYPES,quotas,strict=True):
                ranked=sorted(((i,r) for i,r in enumerate(rows) if r['type']==semantic),
                              key=lambda pair:hashlib.sha256(f'{SEED}:{table}:{pair[0]:03}'.encode()).digest())
                for i,row in ranked:
                    if sum(t['answer_type']==semantic for t in chosen)>=quota:
                        break
                    candidate=databench_task(row,i,split)
                    collisions=[t['task_id'] for t in tasks+chosen if t['dataset']=='databench'
                                and near_questions(t['question'],candidate['question'])]
                    if collisions:
                        skipped.append({'id':candidate['task_id'],'reason':'duplicate_question','against':collisions})
                        continue
                    chosen.append(candidate)
                if sum(t['answer_type']==semantic for t in chosen)!=quota:
                    raise ValueError(f'Insufficient distinct official {semantic} QA in {table}; do not pad quotas')
            chosen.sort(key=lambda t:t['task_id'])
            entry.update({'question_ids':[t['official_question_id'] for t in chosen], 'split':split,
                          'official_split':'dev' if split=='validation' else 'test',
                          'selection':{'seed':SEED,'method':'per-type quotas then lowest SHA-256(seed:table:zero-padded-row); reject near duplicates against retained/selected questions',
                                       'quotas':dict(zip(TYPES,quotas,strict=True))}})
            databases[table]=entry
            tasks+=chosen
    # Safe evaluator checks are reference round-trips, never model outputs or accuracy evidence.
    official_checks=Counter()
    for t in tasks:
        if t['dataset']=='databench':
            if not Evaluator.default_compare(None,t['reference']['answer'],t['reference']['answer'],t['answer_type']):
                raise ValueError(f"Official scorer reference round-trip failed: {t['task_id']}")
            official_checks[t['split']]+=1
    duplicates=duplicate_candidates(tasks)
    cross=[d for d in duplicates if d['cross_split']]
    by_id={t['task_id']:t for t in tasks}
    new_duplicates=[d for d in duplicates if not (by_id[d['left']]['legacy'] and by_id[d['right']]['legacy'])]
    # Literal-normalized SQL is an additional defense against month/state-only Olist variants.
    sql_collisions=[]
    for i,t in enumerate(tasks):
        if t['dataset']!='olist' or not t['reference'].get('sql'):
            continue
        for previous in tasks[:i]:
            if previous['dataset']=='olist' and previous['reference'].get('sql'):
                if sql_template(previous['reference']['sql'])==sql_template(t['reference']['sql']) and not (previous.get('legacy') and t.get('legacy')):
                    sql_collisions.append({'left':previous['task_id'],'right':t['task_id'],'reason':'sql_literal_template'})
    write_json(local/'duplicate-audit.json',{'candidates':duplicates,'cross_split':cross,
                                           'sql_collisions':sql_collisions,'databench_rejections':skipped})
    if new_duplicates or cross or sql_collisions:
        raise ValueError(f'Unresolved duplicate candidates: {len(new_duplicates)} new, {len(cross)} cross-split, {len(sql_collisions)} SQL templates; see private audit')
    full=deepcopy(tasks)
    references={s:{} for s in ('development','validation','test')}
    for t in tasks:
        ref=t.pop('reference')
        references[t['split']][t['task_id']]=ref
        t['reference']={'resource':f"{t['split']}.references.json" if t['split']!='test' else 'OWNER_CONTROLLED',
                        'key':t['task_id'],'sha256':digest(ref)}
        t['question_sha256']=digest(t['question'])
        if t['split']=='test':
            # Do not leak SQL, rubrics, detailed business definitions or readable semantic labels.
            t['question']=None
            t.pop('business_definition',None)
    result=validate_catalog(tasks,sources,{**references['development'],**references['validation']})
    history_hashes['benchmarks/olist_cases.py']=text_digest(Path('benchmarks/olist_cases.py'))
    for path in ('reports/olist-summary.json','reports/databench-summary.json','reports/olist-reference-audit.json'):
        history_hashes[path]=text_digest(path)
    if previous_manifest and history_hashes!=previous_manifest['historical_files']:
        raise ValueError('Historical references/manifests/results changed; preserve the original artifacts')
    owner_values={'test.tasks.json':[t for t in full if t['split']=='test'],
                  'test.references.json':references['test'],'olist-test-authoring.json':private,
                  'README.json':{'status':'FROZEN_CANDIDATE_NOT_BLIND',
               'construction_scope':'Dataset-only; no model inference or performance result.',
               'handoff':'Owner must transfer this directory and pinned table files to restricted storage, remove developer access, review references independently, lock method and run final evaluation separately.',
               'publicly_available_official_gold':True}}
    artifact_values={'tasks.json':tasks,'sources.json':sources,
                     'duplicate-audit.json':{'legacy_development_pairs':duplicates,
                                             'rejected_official_candidates':skipped,
                                             'cross_split_candidates':cross,'new_sql_template_collisions':sql_collisions},
                     'development.references.json':references['development'],
                     'validation.references.json':references['validation']}
    report={**result,'new_tasks':200,'retained_tasks':197,'new_olist_source_sql_checks':len(checks),
            'new_olist_rubric_tasks':100-len(checks),'new_olist_human_approved':0,
            'all_olist_formal_acceptance':'PENDING_HUMAN_REVIEW',
            'databench_official_reference_roundtrips':dict(official_checks),
            'cross_split_duplicate_candidates':len(cross),'new_sql_template_collisions':len(sql_collisions),
            'legacy_within_development_duplicate_candidates':len(duplicates),
            'databench_selection_rejections':len(skipped),
            'difficulty':{d:dict(Counter(t['difficulty'] for t in tasks if t['dataset']==d)) for d in ('olist','databench')},
            'new_olist_family_distribution':{s:dict(Counter(t['task_family'] for t in tasks if t['dataset']=='olist' and not t['legacy'] and t['split']==s)) for s in ('development','validation','test')},
            'databench_answer_types':{s:dict(Counter(t['answer_type'] for t in tasks if t['dataset']=='databench' and t['split']==s)) for s in ('development','validation','test')},
            'limitations':['Automated lexical/SQL/template checks are not a proof of semantic independence; independent review remains required.',
                          'Official answers/types are preserved, not independently corrected; round-trips only validate scorer compatibility.',
                          'Test builder has seen candidate content; public upstream DataBench answers are reconstructible.',
                          'No independent human approval or true OS/account isolation has been established.']}
    artifact_values['audit.json']=report
    hashes={name:hashlib.sha256(artifact_bytes(value)).hexdigest() for name,value in artifact_values.items()}
    hashes['olist-development-validation.json']=file_digest(output/'olist-development-validation.json')
    owner_files={name:hashlib.sha256(artifact_bytes(value)).hexdigest() for name,value in owner_values.items()}
    write_json(local/'reproduction-check.json',{
        'changed_public_files':[n for n,h in hashes.items() if previous_manifest and previous_manifest['files'].get(n)!=h],
        'changed_protected_files':[n for n,h in owner_files.items() if previous_manifest and previous_manifest['protected_test_files'].get(n)!=h],
    })
    enforce_freeze(previous_manifest,hashes,owner_files,release)
    for name,value in artifact_values.items():
        write_json(output/name,value)
    for name,value in owner_values.items():
        write_json(local/'owner'/name,value)
    manifest={'schema_version':1,'release':release,'status':'FROZEN_CANDIDATE_NOT_BLIND',
              'date':'2026-11-15','counts':result['counts'],'files':hashes,
              'protected_test_files':owner_files,'historical_files':history_hashes,
              'generator':'python -m benchmarks.build_phase2','seed':SEED,
              'runtime':{'python':'3.12','duckdb':duckdb.__version__,'pyarrow':pa.__version__,
                         'sqlglot':importlib.metadata.version('sqlglot'),'databench-eval':importlib.metadata.version('databench-eval')}}
    write_json(output/'manifest.json',manifest)
    write_json(local/'reference-checks.json',checks)
    print(json.dumps(report,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-root',type=Path,default=Path('data/phase2'))
    parser.add_argument('--olist-test-authoring',type=Path,required=True)
    parser.add_argument('--db',type=Path,default=Path('data/olist.duckdb'))
    parser.add_argument('--archive',type=Path,default=Path('data/raw/olist-v2.zip'))
    parser.add_argument('--fetch',action='store_true')
    parser.add_argument('--release',help='A new release name is required when frozen content changes')
    args=parser.parse_args()
    construct(args.local_root,args.olist_test_authoring,args.db,args.archive,fetch=args.fetch,release=args.release)


if __name__=='__main__':
    main()
