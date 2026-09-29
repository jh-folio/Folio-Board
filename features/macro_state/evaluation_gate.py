"""Durable stage ordering and one-attempt holdout protection, outside the user DB."""
import hashlib
import json
from pathlib import Path

from features.common.atomic_replace import write_bytes_atomic


def code_hash(directory):
    root = Path(directory)
    digest = hashlib.sha256()
    paths = list(root.glob('*.py'))
    paths += [root.parent / 'common' / 'macro_data' / name for name in ('registry.py', 'schema.py', 'transforms.py')]
    for path in sorted(paths):
        digest.update(str(path.relative_to(root.parent)).replace('\\', '/').encode('utf-8') + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()


def write_json(path, value):
    write_bytes_atomic(Path(path), (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8'))


class EvaluationGate:
    def __init__(self, directory):
        self.directory = Path(directory)

    def begin(self, stage, identity):
        if stage not in {'development', 'validation', 'final'}:
            raise ValueError('invalid_evaluation_stage')
        self.directory.mkdir(parents=True, exist_ok=True)
        if stage != 'development':
            frozen = json.loads((self.directory / 'freeze.json').read_text(encoding='utf-8'))
            if frozen['identity'] != identity or not frozen.get('commit'):
                raise ValueError('evaluation_freeze_mismatch')
            prerequisite = 'development' if stage == 'validation' else 'validation'
            previous = json.loads((self.directory / (prerequisite + '.json')).read_text(encoding='utf-8'))
            if previous['status'] != 'completed':
                raise ValueError('evaluation_prerequisite_incomplete')
            prior_identity = previous['identity']
            if stage == 'final' and prior_identity != identity:
                raise ValueError('evaluation_prerequisite_identity_mismatch')
            if stage == 'validation' and any(identity.get(k) != v for k, v in prior_identity.items() if k != 'parameters'):
                raise ValueError('evaluation_prerequisite_identity_mismatch')
        # mkdir is exclusive and atomic across processes. An interrupted attempt
        # keeps the claim; it cannot silently re-use final data in a second run.
        claim = self.directory / (stage + '.claim')
        claim.mkdir()
        write_json(self.directory / (stage + '.json'), {'status': 'started', 'identity': identity})

    def finish(self, stage, identity, report):
        path = self.directory / (stage + '.json')
        prior = json.loads(path.read_text(encoding='utf-8'))
        if prior != {'status': 'started', 'identity': identity}:
            raise ValueError('evaluation_attempt_mismatch')
        write_json(path, {'status': 'completed', 'identity': identity, 'report': str(report)})
