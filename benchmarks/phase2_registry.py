"""Dataset-only Phase II contracts. No Agent/model imports or candidate Test loader."""

from collections import Counter
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent / 'phase2'
SPLITS = ('development', 'validation', 'test')
EXPECTED = {'olist': {'development': 85, 'validation': 20, 'test': 40},
            'databench': {'development': 152, 'validation': 40, 'test': 60}}
REVIEW = {'AUTO_VERIFIED', 'PENDING_HUMAN_REVIEW'}
OFFICIAL_TYPES = {'boolean', 'number', 'category', 'list[category]', 'list[number]'}
REQUIRED = {'task_id', 'dataset', 'database_id', 'split', 'question', 'question_sha256',
            'task_family', 'semantic_template_id', 'answer_type', 'reference', 'grading_rule',
            'source_version', 'review_status', 'difficulty'}


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                       allow_nan=False) + '\n').encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def text_digest(path):
    """Historical Git text is LF-normalized without rewriting original artifacts."""
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def artifact_bytes(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(artifact_bytes(value))


def enforce_freeze(previous, files, protected, release):
    if previous and release==previous['release']:
        if previous['files']!=files or previous['protected_test_files']!=protected:
            raise ValueError('Frozen content changed: supply a new --release and disclose review/exposure changes')


def normalize_question(question):
    """Catch literal substitutions; schema/measure words are intentionally retained."""
    value = question.casefold().replace('\u2019', "'")
    value = re.sub(r"'[^']*'|\"[^\"]*\"", ' literal ', value)
    value = re.sub(r'\b\d+(?:[.:-]\d+)*\b', ' number ', value)
    return ' '.join(re.findall(r'[a-z_]+', value))


def near_questions(left, right):
    a, b = normalize_question(left), normalize_question(right)
    if a == b:
        return 'normalized_exact'
    ta, tb = set(a.split()), set(b.split())
    jaccard = len(ta & tb) / max(len(ta | tb), 1)
    if jaccard >= .72 and SequenceMatcher(None, a, b).ratio() >= .84:
        return 'lexical_near'
    return None


def duplicate_candidates(tasks):
    result = []
    for index, right in enumerate(tasks):
        for left in tasks[:index]:
            if left['dataset'] != right['dataset']:
                continue
            reason = near_questions(left['question'], right['question'])
            template = left['semantic_template_id'] == right['semantic_template_id']
            if reason or template:
                result.append({'left': left['task_id'], 'right': right['task_id'],
                               'reason': reason or 'semantic_template',
                               'cross_split': left['split'] != right['split']})
    return result


def validate_grading_rule(task):
    rule=task['grading_rule']
    kind=rule.get('kind')
    if kind=='rows':
        try:
            tolerance=Decimal(rule['absolute_tolerance'])
        except (KeyError,InvalidOperation,TypeError):
            raise ValueError('Missing/invalid numeric tolerance') from None
        if not tolerance.is_finite() or tolerance<0 or rule.get('ordered') is not True:
            raise ValueError('Invalid row grading contract')
    elif kind=='official_databench':
        if task['answer_type'] not in OFFICIAL_TYPES or rule.get('version')!='4.0.1' or rule.get('package')!='databench-eval':
            raise ValueError('Official grading contract/type/version drift')
    elif kind=='human_rubric':
        if task['review_status']!='PENDING_HUMAN_REVIEW':
            raise ValueError('Rubric-only tasks must await human review')
    elif kind=='legacy_olist':
        if not task.get('legacy') or task['split']!='development':
            raise ValueError('Historical grading is Development-only')
    else:
        raise ValueError('Unknown grading contract')


def validate_reference(task, reference):
    if not reference or not isinstance(reference, dict):
        raise ValueError(f"Missing reference: {task['task_id']}")
    rule = task['grading_rule']
    kind = rule.get('kind')
    if kind in {'rows', 'legacy_olist'}:
        if not reference.get('sql') or 'rows' not in reference:
            raise ValueError('SQL reference requires materialized rows')
        if not isinstance(reference['rows'], list) or any(not isinstance(r, list) for r in reference['rows']):
            raise ValueError('Rows must be a list of row lists')
        if kind == 'rows' and (Decimal(rule['absolute_tolerance']) < 0 or not rule.get('ordered')):
            raise ValueError('Phase II rows require nonnegative absolute tolerance and an ordering contract')
    elif kind == 'human_rubric':
        if len(reference.get('criteria', [])) < 3 or any(not c.strip() for c in reference['criteria']):
            raise ValueError('Human rubric requires at least three nonempty criteria')
        if task['review_status'] != 'PENDING_HUMAN_REVIEW':
            raise ValueError('Rubric-only tasks must await human review')
    elif kind == 'official_databench':
        if task['answer_type'] not in OFFICIAL_TYPES or 'answer' not in reference or reference.get('official_type')!=task['answer_type']:
            raise ValueError('Official answer/type missing')
        if rule.get('version') != '4.0.1':
            raise ValueError('Official evaluator version drift')
    else:
        raise ValueError(f'Unknown grading kind: {kind}')


def validate_catalog(tasks, sources, references=None, *, complete=True):
    """Public-only checks never open Test resources, even for a complete catalog."""
    ids, populations, question_splits, templates = set(), {}, {}, {}
    counts = {d: Counter() for d in EXPECTED}
    for t in tasks:
        if REQUIRED - t.keys():
            raise ValueError(f'Missing metadata: {REQUIRED - t.keys()}')
        identifier, dataset, split = t['task_id'], t['dataset'], t['split']
        if identifier in ids:
            raise ValueError(f'Duplicate task ID: {identifier}')
        ids.add(identifier)
        if dataset not in EXPECTED or split not in SPLITS:
            raise ValueError('Unknown dataset/split')
        counts[dataset][split] += 1
        if t['source_version'] not in sources:
            raise ValueError('Unknown source version')
        if t['review_status'] not in REVIEW:
            raise ValueError('Unapproved review status')
        if not all(t.get(k) for k in ('task_family','semantic_template_id','answer_type','difficulty')):
            raise ValueError('Empty task classification')
        validate_grading_rule(t)
        if not re.fullmatch('[0-9a-f]{64}', t['question_sha256']):
            raise ValueError('Invalid question commitment')
        if not re.fullmatch('[0-9a-f]{64}', t['reference'].get('sha256', '')):
            raise ValueError('Invalid reference commitment')
        if split == 'test':
            if t['question'] is not None or t['reference'].get('resource') != 'OWNER_CONTROLLED':
                raise ValueError('Candidate Test content must be withheld')
        elif not t['question'] or digest(t['question']) != t['question_sha256']:
            raise ValueError('Question commitment mismatch')
        key = (dataset, t['question_sha256'])
        if key in question_splits and question_splits[key] != split:
            raise ValueError('Question crosses splits')
        question_splits[key] = split
        key = (dataset, t['semantic_template_id'])
        # Existing Development repetitions are retained. No exact semantic template may cross splits.
        if key in templates and templates[key] != split:
            raise ValueError('Semantic template crosses splits')
        templates[key] = split
        if dataset == 'databench':
            key = t['database_id']
            if key in populations and populations[key] != split:
                raise ValueError('DataBench database crosses splits')
            populations[key] = split
            entry = sources[t['source_version']]['databases'].get(key)
            if not entry or t['official_question_id'] not in entry['question_ids']:
                raise ValueError('Unpinned official question')
        if references is not None and split != 'test':
            ref = references.get(identifier)
            if digest(ref) != t['reference']['sha256']:
                raise ValueError('Reference commitment mismatch')
            validate_reference(t, ref)
    if complete and {d: dict(c) for d, c in counts.items()} != EXPECTED:
        raise ValueError(f'Wrong counts: {counts}')
    for version, source in sources.items():
        if not source.get('source') or not source.get('revision') or not source.get('license'):
            raise ValueError(f'Incomplete provenance: {version}')
        for db in source.get('databases', {}).values():
            if db['rows'] < 1 or set(db['files']) != {'qa.parquet', 'all.parquet'}:
                raise ValueError('Incomplete database provenance')
            if any(not re.fullmatch('[0-9a-f]{64}', h) for h in db['files'].values()):
                raise ValueError('Invalid source file hash')
    if complete:
        legacy_olist={t['task_id'] for t in tasks if t['dataset']=='olist' and t.get('legacy')}
        if legacy_olist != {f'O{i:03}' for i in range(1,46)}:
            raise ValueError('The 45 historical Olist tasks must be preserved')
        legacy_db=[t for t in tasks if t['dataset']=='databench' and t.get('legacy')]
        if len(legacy_db)!=152 or any(t['split']!='development' for t in tasks if t.get('legacy')):
            raise ValueError('All 197 exposed tasks must remain Development')
        for source in sources.values():
            for database_id,db in source.get('databases',{}).items():
                selected={t['official_question_id'] for t in tasks
                          if t['dataset']=='databench' and t['database_id']==database_id}
                if selected!=set(db['question_ids']):
                    raise ValueError('Catalog and pinned question selection differ')
    return {'counts': {d: dict(c) for d,c in counts.items()}, 'unique_ids': len(ids),
            'databench_databases': dict(Counter(populations.values()))}


def load_tasks(split, root=ROOT):
    """Only Development/Validation may be opened by the development workflow."""
    if split not in ('development', 'validation'):
        raise ValueError('Candidate Test requires the separate owner-controlled final evaluation process')
    tasks = read_json(Path(root) / 'tasks.json')
    manifest = read_json(Path(root) / 'manifest.json')
    for name in ('tasks.json', f'{split}.references.json', 'sources.json'):
        if file_digest(Path(root) / name) != manifest['files'][name]:
            raise ValueError(f'Frozen artifact changed: {name}')
    sources = read_json(Path(root) / 'sources.json')
    references = read_json(Path(root) / f'{split}.references.json')
    selected = [t for t in tasks if t['split'] == split]
    validate_catalog(selected, sources, references, complete=False)
    return [{**t, 'reference': references[t['task_id']]} for t in selected]


def grade_rows(actual, reference, rule):
    """New Olist protocol: exact NULL/bool/string, absolute numeric tolerance, positional rows."""
    expected = reference['rows']
    if len(actual) != len(expected):
        return False
    tolerance = Decimal(rule['absolute_tolerance'])
    for a, e in zip(actual, expected, strict=True):
        if len(a) != len(e):
            return False
        for value, truth in zip(a, e, strict=True):
            if truth is None or value is None:
                if value is not truth:
                    return False
            elif isinstance(truth, bool):
                if not isinstance(value, bool) or value != truth:
                    return False
            elif isinstance(truth, (int, float)) or isinstance(truth, dict):
                try:
                    target = Decimal(truth['decimal'] if isinstance(truth, dict) else str(truth))
                    observed = Decimal(str(value))
                    if isinstance(value, bool) or not observed.is_finite() or abs(observed-target)>tolerance:
                        return False
                except (InvalidOperation, ValueError, TypeError):
                    return False
            elif value != truth:
                return False
    return True


def main():
    tasks, sources = read_json(ROOT/'tasks.json'), read_json(ROOT/'sources.json')
    manifest = read_json(ROOT/'manifest.json')
    for name, checksum in manifest['files'].items():
        if file_digest(ROOT/name) != checksum:
            raise ValueError(f'Frozen artifact changed: {name}')
    for name, checksum in manifest['historical_files'].items():
        if text_digest(ROOT.parents[1]/name)!=checksum:
            raise ValueError(f'Historical artifact changed: {name}')
    refs = {**read_json(ROOT/'development.references.json'), **read_json(ROOT/'validation.references.json')}
    print(json.dumps(validate_catalog(tasks, sources, refs), indent=2))


if __name__ == '__main__':
    main()
