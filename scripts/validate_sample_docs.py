"""Validate reviewed documentation without regenerating or overwriting it."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import re
ROOT=Path(__file__).resolve().parents[1]

def validate(strict=False):
    count=0
    for repo in sorted((ROOT/'sample-repositories').glob('commerce-*')):
        spec=json.loads((repo/'docs/openapi.json').read_text())
        review=json.loads((repo/'docs/source-review.json').read_text())
        assert spec['openapi']=='3.1.0'
        assert spec['security']==[{'CommerceBearer':[]}],f'{repo.name}: global bearer security is missing'
        assert spec['components']['securitySchemes']['CommerceBearer']=={
            'type':'http','scheme':'bearer','bearerFormat':'opaque shared service token'
        }
        for relative,digest in review['files'].items():
            assert hashlib.sha256((repo/relative).read_bytes()).hexdigest()==digest,f'{repo.name}/{relative}: changed since documentation review; review docs and refresh reviewed hash'
        config=json.loads((repo/'config/local.json').read_text())
        dev=json.loads((repo/'config/development.json').read_text())
        assert spec['servers'][0]['url']==f"http://{config['server']['host']}:{config['server']['port']}"
        assert spec['servers'][1]['url']==f"http://{config['service']}:{dev['server']['port']}"
        service=ast.parse(next((repo/'src').glob('*/service.py')).read_text())
        methods={n.name for n in ast.walk(service) if isinstance(n,ast.FunctionDef)}
        expected={('/health','get'),(config['api']['read_path']+'/{id}','get')}
        for path,method in config['api']['write_routes'].items():
            assert method in methods,(repo,method)
            expected.add((path,'post'))
        actual={(path,method) for path,operations in spec['paths'].items() for method in operations}
        assert actual==expected,(repo,actual,expected)
        for path,operations in spec['paths'].items():
            for method,operation in operations.items():
                if path=='/health' and method=='get':
                    assert operation.get('security')==[],f'{repo.name}: health should remain public'
                else:
                    assert operation.get('security')==[{'CommerceBearer':[]}],f'{repo.name}: {method} {path} must require bearer auth'
                    assert '401' in operation['responses'],f'{repo.name}: {method} {path} must document unauthorized response'
        def walk(value):
            if isinstance(value,dict):
                if '$ref' in value:
                    assert value['$ref'].startswith('#/'),value
                    target=spec
                    for key in value['$ref'][2:].split('/'):target=target[key]
                for item in value.values():walk(item)
            elif isinstance(value,list):
                for item in value:walk(item)
        walk(spec)
        for path in repo.rglob('*.md'):
            text=path.read_text()
            assert text.count('```')%2==0,path
            for link in re.findall(r'\]\(([^)]+)\)',text):
                if '://' in link or link.startswith('#'):continue
                assert (path.parent/link.split('#')[0]).exists(),(path,link)
        if strict:
            from openapi_spec_validator import validate as validate_openapi
            from jsonschema import Draft202012Validator
            validate_openapi(spec)
            for operations in spec['paths'].values():
                for operation in operations.values():
                    media=[]
                    if 'requestBody' in operation:
                        media.extend(operation['requestBody']['content'].values())
                    for response in operation['responses'].values():
                        media.extend(response.get('content',{}).values())
                    for item in media:
                        schema={'components':spec['components'],**item['schema']}
                        examples=[]
                        if 'example' in item: examples.append(item['example'])
                        examples.extend(e['value'] for e in item.get('examples',{}).values() if 'value' in e)
                        for example in examples:Draft202012Validator(schema).validate(example)
        count+=1
        print(f'{repo.name}: source review, routes, servers, references and Markdown links verified')
    print(f'{count} reviewed API specifications validated. This checks consistency, not deployment availability or complete runtime schema enforcement.')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--openapi',action='store_true',help='Also validate OpenAPI structure and JSON examples; install scripts/requirements-docs.txt first')
    validate(parser.parse_args().openapi)
