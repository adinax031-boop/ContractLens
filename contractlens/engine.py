"""Directional compatibility checks for a deliberately bounded OpenAPI subset."""
from dataclasses import asdict, dataclass
from typing import Any

METHODS = {'get', 'put', 'post', 'delete', 'options', 'head', 'patch', 'trace'}


@dataclass(frozen=True, order=True)
class Finding:
    severity: str
    code: str
    location: str
    message: str

    def to_dict(self):
        return asdict(self)


class InvalidSpec(ValueError):
    pass


def validate(spec):
    if not isinstance(spec, dict) or not str(spec.get('openapi', '')).startswith('3.0.'):
        raise InvalidSpec('Expected an OpenAPI 3.0.x JSON object.')
    if not isinstance(spec.get('paths'), dict):
        raise InvalidSpec('paths must be an object.')
    def walk(value):
        if isinstance(value, dict):
            if '$ref' in value:
                ref = value['$ref']
                if not isinstance(ref, str) or not ref.startswith('#/'):
                    raise InvalidSpec('Only local JSON Pointer references are supported.')
                resolve(value, spec)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(spec)


def resolve(value, root):
    seen = set()
    while isinstance(value, dict) and '$ref' in value:
        ref = value['$ref']
        if ref in seen:
            raise InvalidSpec('Cyclic reference chain: ' + ref)
        seen.add(ref)
        try:
            value = root
            for part in ref[2:].split('/'):
                value = value[part.replace('~1', '/').replace('~0', '~')]
        except (KeyError, TypeError):
            raise InvalidSpec('Unresolved reference: ' + ref) from None
    if not isinstance(value, dict):
        raise InvalidSpec('Expected an object after reference resolution.')
    return value


def compare(old: dict[str, Any], new: dict[str, Any]) -> list[Finding]:
    """Compare from the perspective of existing clients. Never mutate inputs."""
    validate(old)
    validate(new)
    findings = set()
    def emit(severity, code, loc, message):
        findings.add(Finding(severity, code, loc, message))
    def schema(a, b, loc, direction, visited=frozenset()):
        a, b = resolve(a, old), resolve(b, new)
        pair = (id(a), id(b), direction)
        if pair in visited:
            return
        visited = visited | {pair}
        unsupported = {'allOf', 'anyOf', 'oneOf', 'not', 'discriminator', 'additionalProperties'}
        if unsupported.intersection(a) or unsupported.intersection(b):
            emit('warning', 'SCHEMA_REVIEW', loc, 'Composition or additionalProperties requires manual review.')
        if a.get('type') != b.get('type'):
            emit('breaking', 'TYPE_CHANGED', loc, f"Type changed from {a.get('type')} to {b.get('type')}.")
        if a.get('format') != b.get('format'):
            emit('warning', 'FORMAT_CHANGED', loc, 'Format changed; review serialization compatibility.')
        if a.get('nullable', False) != b.get('nullable', False):
            bad = a.get('nullable', False) if direction == 'request' else b.get('nullable', False)
            emit('breaking' if bad else 'info', 'NULLABILITY_CHANGED', loc, 'Nullability changed.')
        if a.get('enum') != b.get('enum'):
            ae, be = a.get('enum'), b.get('enum')
            included = lambda left, right: all(x in right for x in left)
            bad = (be is not None and (ae is None or not included(ae, be))) if direction == 'request' else (ae is not None and (be is None or not included(be, ae)))
            emit('breaking' if bad else 'info', 'ENUM_CHANGED', loc, f'{direction.capitalize()} enum changed.')
        for key in ('minimum', 'maximum', 'minLength', 'maxLength', 'minItems', 'maxItems', 'pattern', 'exclusiveMinimum', 'exclusiveMaximum', 'uniqueItems', 'multipleOf'):
            if a.get(key) != b.get(key):
                emit('warning', 'CONSTRAINT_CHANGED', loc + '/' + key, 'Validation constraint changed; requires manual review.')
        ar, br = set(a.get('required', [])), set(b.get('required', []))
        for name in sorted((br-ar) if direction == 'request' else (ar-br)):
            emit('breaking', 'REQUIRED_CHANGED', loc + '/properties/' + name, 'Existing clients lose a required-field guarantee.' if direction == 'response' else 'Existing clients must send a new required field.')
        ap, bp = a.get('properties', {}), b.get('properties', {})
        for name in sorted(ap.keys() - bp.keys()):
            emit('breaking' if direction == 'response' else 'warning', 'PROPERTY_REMOVED', loc + '/properties/' + name, f'{direction.capitalize()} property removed.')
        for name in sorted(bp.keys() - ap.keys()):
            emit('info', 'PROPERTY_ADDED', loc + '/properties/' + name, f'{direction.capitalize()} property added.')
        for name in sorted(ap.keys() & bp.keys()):
            schema(ap[name], bp[name], loc + '/properties/' + name, direction, visited)
        if 'items' in a and 'items' in b:
            schema(a['items'], b['items'], loc + '/items', direction, visited)
        elif ('items' in a) != ('items' in b):
            emit('warning', 'ITEMS_CHANGED', loc, 'Array item schema added or removed.')
    def content(a, b, loc, direction):
        ac, bc = a.get('content', {}), b.get('content', {})
        for media in ac.keys() - bc.keys():
            emit('breaking', 'MEDIA_REMOVED', loc + '/' + media, 'Supported media type removed.')
        for media in ac.keys() & bc.keys():
            sa, sb = ac[media].get('schema'), bc[media].get('schema')
            if sa is not None and sb is not None:
                schema(sa, sb, loc + '/' + media, direction)
            elif sa != sb:
                emit('warning', 'SCHEMA_PRESENCE_CHANGED', loc + '/' + media, 'Schema added or removed; review manually.')
    def operations(root):
        result = {}
        for path, raw in root['paths'].items():
            item = resolve(raw, root)
            for method in METHODS & item.keys():
                result[(path, method)] = (item, resolve(item[method], root))
        return result
    ao, bo = operations(old), operations(new)
    for path, method in sorted(ao.keys() - bo.keys()):
        emit('breaking', 'OPERATION_REMOVED', method.upper() + ' ' + path, 'Endpoint removed.')
    for path, method in sorted(bo.keys() - ao.keys()):
        emit('info', 'OPERATION_ADDED', method.upper() + ' ' + path, 'Endpoint added.')
    for key in sorted(ao.keys() & bo.keys()):
        ai, a = ao[key]; bi, b = bo[key]
        loc = key[1].upper() + ' ' + key[0]
        if a.get('security', old.get('security', [])) != b.get('security', new.get('security', [])):
            emit('warning', 'SECURITY_CHANGED', loc, 'Authentication requirements changed; review manually.')
        def parameters(item, op, root):
            merged = {}
            for raw in item.get('parameters', []) + op.get('parameters', []):
                p = resolve(raw, root)
                merged[(p['in'], p['name'])] = p
            return merged
        pa, pb = parameters(ai, a, old), parameters(bi, b, new)
        for p in pb.keys() - pa.keys():
            if pb[p].get('required'):
                emit('breaking', 'PARAMETER_REQUIRED', loc + '/' + '/'.join(p), 'New required parameter.')
        for p in pa.keys() - pb.keys():
            emit('warning', 'PARAMETER_REMOVED', loc + '/' + '/'.join(p), 'Parameter removed; review existing client behavior.')
        for p in pa.keys() & pb.keys():
            ploc = loc + '/' + '/'.join(p)
            if not pa[p].get('required') and pb[p].get('required'):
                emit('breaking', 'PARAMETER_REQUIRED', ploc, 'Optional parameter is now required.')
            if 'schema' in pa[p] and 'schema' in pb[p]:
                schema(pa[p]['schema'], pb[p]['schema'], ploc, 'request')
            if pa[p].get('style') != pb[p].get('style') or pa[p].get('explode') != pb[p].get('explode'):
                emit('warning', 'SERIALIZATION_CHANGED', ploc, 'Parameter serialization changed.')
        ra = resolve(a['requestBody'], old) if 'requestBody' in a else {}
        rb = resolve(b['requestBody'], new) if 'requestBody' in b else {}
        if not ra.get('required') and rb.get('required'):
            emit('breaking', 'BODY_REQUIRED', loc, 'Request body is now required.')
        content(ra, rb, loc + '/request', 'request')
        for status in a.get('responses', {}).keys() - b.get('responses', {}).keys():
            emit('breaking', 'RESPONSE_REMOVED', loc + '/responses/' + status, 'Documented response removed.')
        for status in b.get('responses', {}).keys() - a.get('responses', {}).keys():
            emit('warning', 'RESPONSE_ADDED', loc + '/responses/' + status, 'New response status; review existing clients.')
        for status in a.get('responses', {}).keys() & b.get('responses', {}).keys():
            content(resolve(a['responses'][status], old), resolve(b['responses'][status], new), loc + '/responses/' + status, 'response')
    return sorted(findings, key=lambda f: ({'breaking': 0, 'warning': 1, 'info': 2}[f.severity], f.location, f.code, f.message))
