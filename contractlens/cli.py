"""Command-line interface. Exit 1 for policy failure, 2 for invalid input."""
import argparse
import json
import sys
from pathlib import Path
from .engine import compare, InvalidSpec
from .report import render


def main(argv=None):
    parser = argparse.ArgumentParser(prog='contractlens', description='Catch breaking OpenAPI changes before release.')
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--format', choices=['text', 'json', 'html'], default='text')
    parser.add_argument('--output', '-o', type=Path)
    parser.add_argument('--fail-on', choices=['breaking', 'warning', 'never'], default='breaking')
    args = parser.parse_args(argv)
    try:
        findings = compare(json.loads(args.baseline.read_text(encoding='utf-8')), json.loads(args.candidate.read_text(encoding='utf-8')))
        if args.format == 'json':
            result = json.dumps({'tool': 'ContractLens', 'findings': [f.to_dict() for f in findings]}, indent=2) + '\n'
        elif args.format == 'html':
            result = render(findings, args.baseline.name, args.candidate.name)
        else:
            result = '\n'.join(f'{f.severity.upper():8} {f.code} | {f.location}\n         {f.message}' for f in findings) or 'No changes detected by supported checks.'
            result += '\n'
        if args.output:
            args.output.write_text(result, encoding='utf-8')
        else:
            sys.stdout.write(result)
        failures = {'breaking'} if args.fail_on == 'breaking' else {'breaking', 'warning'} if args.fail_on == 'warning' else set()
        return int(any(f.severity in failures for f in findings))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        print(f'contractlens: invalid input or output: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
