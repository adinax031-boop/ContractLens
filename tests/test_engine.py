import copy
import unittest
from contractlens import compare, InvalidSpec
from contractlens.report import render


def spec(schema=None, direction='response'):
    op = {'responses': {'200': {'description': 'OK'}}}
    if schema is not None:
        body = {'content': {'application/json': {'schema': schema}}}
        if direction == 'request':
            op['requestBody'] = body
        else:
            op['responses']['200'].update(body)
    return {'openapi': '3.0.3', 'info': {'title': 'Test', 'version': '1'}, 'paths': {'/users': {'get': op}}}


def codes(old, new, severity=None):
    return {f.code for f in compare(old, new) if severity is None or f.severity == severity}


class EngineTests(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(compare(spec(), spec()), [])

    def test_removed_endpoint(self):
        new = spec(); new['paths'] = {}
        self.assertIn('OPERATION_REMOVED', codes(spec(), new, 'breaking'))

    def test_added_endpoint(self):
        old = spec(); old['paths'] = {}
        self.assertEqual(codes(old, spec(), 'info'), {'OPERATION_ADDED'})

    def test_request_enum_narrowing(self):
        self.assertIn('ENUM_CHANGED', codes(spec({'enum': ['a', 'b']}, 'request'), spec({'enum': ['a']}, 'request'), 'breaking'))

    def test_request_enum_expansion(self):
        self.assertFalse(codes(spec({'enum': ['a']}, 'request'), spec({'enum': ['a', 'b']}, 'request'), 'breaking'))

    def test_response_enum_expansion(self):
        self.assertIn('ENUM_CHANGED', codes(spec({'enum': ['a']}), spec({'enum': ['a', 'b']}), 'breaking'))

    def test_response_enum_narrowing(self):
        self.assertFalse(codes(spec({'enum': ['a', 'b']}), spec({'enum': ['a']}), 'breaking'))

    def test_request_new_enum(self):
        self.assertIn('ENUM_CHANGED', codes(spec({}, 'request'), spec({'enum': [1]}, 'request'), 'breaking'))

    def test_response_removed_enum(self):
        self.assertIn('ENUM_CHANGED', codes(spec({'enum': [1]}), spec({}), 'breaking'))

    def test_type_change(self):
        self.assertIn('TYPE_CHANGED', codes(spec({'type': 'string'}), spec({'type': 'integer'}), 'breaking'))

    def test_required_request(self):
        self.assertIn('REQUIRED_CHANGED', codes(spec({'type': 'object'}, 'request'), spec({'type': 'object', 'required': ['id']}, 'request'), 'breaking'))

    def test_required_response(self):
        self.assertIn('REQUIRED_CHANGED', codes(spec({'required': ['id']}), spec({}), 'breaking'))

    def test_optional_response_removal(self):
        self.assertIn('PROPERTY_REMOVED', codes(spec({'properties': {'id': {'type': 'string'}}}), spec({}), 'breaking'))

    def test_array_items(self):
        self.assertIn('TYPE_CHANGED', codes(spec({'type': 'array', 'items': {'type': 'string'}}), spec({'type': 'array', 'items': {'type': 'integer'}})))

    def test_response_nullable(self):
        self.assertIn('NULLABILITY_CHANGED', codes(spec({'type': 'string'}), spec({'type': 'string', 'nullable': True}), 'breaking'))

    def test_request_nullable(self):
        self.assertIn('NULLABILITY_CHANGED', codes(spec({'nullable': True}, 'request'), spec({}, 'request'), 'breaking'))

    def test_constraints(self):
        self.assertIn('CONSTRAINT_CHANGED', codes(spec({'minimum': 0}), spec({'minimum': 1}), 'warning'))

    def test_composition_warning(self):
        self.assertIn('SCHEMA_REVIEW', codes(spec({'oneOf': []}), spec({'oneOf': []}), 'warning'))

    def test_refs(self):
        a = spec({'$ref': '#/components/schemas/User'}); b = copy.deepcopy(a)
        a['components'] = {'schemas': {'User': {'type': 'string'}}}
        b['components'] = {'schemas': {'User': {'type': 'integer'}}}
        self.assertIn('TYPE_CHANGED', codes(a, b))

    def test_recursive_schema(self):
        a = spec({'$ref': '#/components/schemas/Node'})
        a['components'] = {'schemas': {'Node': {'type': 'object', 'properties': {'next': {'$ref': '#/components/schemas/Node'}}}}}
        self.assertEqual(compare(a, copy.deepcopy(a)), [])

    def test_missing_ref(self):
        with self.assertRaises(InvalidSpec):
            compare(spec({'$ref': '#/missing'}), spec())

    def test_external_ref(self):
        with self.assertRaises(InvalidSpec):
            compare(spec({'$ref': 'https://example.com/schema'}), spec())

    def test_ref_cycle(self):
        a = spec({'$ref': '#/components/schemas/A'})
        a['components'] = {'schemas': {'A': {'$ref': '#/components/schemas/A'}}}
        with self.assertRaises(InvalidSpec):
            compare(a, a)

    def test_version_rejected(self):
        a = spec(); a['openapi'] = '3.1.0'
        with self.assertRaises(InvalidSpec):
            compare(a, spec())

    def test_required_parameter(self):
        a, b = spec(), spec(); b['paths']['/users']['get']['parameters'] = [{'in': 'query', 'name': 'q', 'required': True, 'schema': {'type': 'string'}}]
        self.assertIn('PARAMETER_REQUIRED', codes(a, b, 'breaking'))

    def test_inherited_override(self):
        a = spec(); a['paths']['/users']['parameters'] = [{'in': 'query', 'name': 'q', 'required': True}]
        a['paths']['/users']['get']['parameters'] = [{'in': 'query', 'name': 'q', 'required': False}]
        b = copy.deepcopy(a); b['paths']['/users']['get']['parameters'][0]['required'] = True
        self.assertIn('PARAMETER_REQUIRED', codes(a, b))

    def test_security_inheritance(self):
        a, b = spec(), spec(); b['security'] = [{'token': []}]
        self.assertIn('SECURITY_CHANGED', codes(a, b, 'warning'))

    def test_request_body_required(self):
        a, b = spec(), spec({}, 'request'); b['paths']['/users']['get']['requestBody']['required'] = True
        self.assertIn('BODY_REQUIRED', codes(a, b))

    def test_removed_media(self):
        self.assertIn('MEDIA_REMOVED', codes(spec({}), spec(), 'breaking'))

    def test_removed_status(self):
        b = spec(); b['paths']['/users']['get']['responses'] = {}
        self.assertIn('RESPONSE_REMOVED', codes(spec(), b))

    def test_deterministic_no_mutation(self):
        a, b = spec({'enum': ['a']}), spec({'enum': ['a', 'b']})
        original = copy.deepcopy((a, b))
        self.assertEqual(compare(a, b), compare(a, b)); self.assertEqual((a, b), original)

    def test_html_escapes_untrusted_data(self):
        a = spec(); a['paths']['<script>alert(1)</script>'] = a['paths'].pop('/users')
        b = spec(); b['paths'] = {}
        html = render(compare(a, b), '<img src=x onerror=alert(1)>')
        self.assertNotIn('<script>alert(1)', html)
        self.assertIn('&lt;img', html)

    def test_empty_report(self):
        self.assertIn('No changes detected', render([]))


if __name__ == '__main__':
    unittest.main()
