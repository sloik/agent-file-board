import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import boardctl
from message_extensions import validate_extensions

ROOT=Path(boardctl.__file__).parent


class FormTests(unittest.TestCase):
    def test_shared_form_contract_and_refusals(self):
        cases=json.loads((ROOT/'tests/fixtures/form-metadata.json').read_text())
        for case in cases:
            with self.subTest(case=case['name']):
                if case['valid']:
                    validate_extensions(case['headers'],case.get('source'))
                else:
                    with self.assertRaises(ValueError):
                        validate_extensions(case['headers'],case.get('source'))

    def test_cli_typed_form_and_cell_patch_roundtrip_refusals_preserve_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'board';output=io.StringIO()
            def cli(*args):
                output.seek(0);output.truncate()
                with contextlib.redirect_stdout(output),contextlib.redirect_stderr(io.StringIO()):
                    code=boardctl.main(list(map(str,args)))
                return code,output.getvalue().strip()
            self.assertEqual(cli('init',root,'--project-id','forms','--project-name','Forms')[0],0)
            for who,kind in [('alpha-agent','agent'),('owner-human','human')]:
                self.assertEqual(cli('join',who,'--kind',kind,'--path',root)[0],0)
            examples=ROOT/'examples/openui-report'
            args=['post','--path',root,'--from','alpha-agent','--to','owner-human','--scope','room','--room','general','--thread','T001','--slug','form','--question-file',examples/'form-question.json','--body','Synthetic form. Submit a new reply.']
            code,rel=cli(*args);self.assertEqual(code,0,rel)
            source=root/rel;original=source.read_bytes()
            answer_args=['post','--path',root,'--from','owner-human','--to','alpha-agent','--scope','room','--room','general','--thread','T001','--slug','typed-answer','--reply-to',source.name,'--answer-file',examples/'form-answer.json','--body','Synthetic typed response: schema estimate1, viewer approved.']
            code,answer_path=cli(*answer_args);self.assertEqual(code,0,answer_path)
            self.assertEqual(json.loads(boardctl.parse_message(root/answer_path)['ANSWER']),json.loads((examples/'form-answer.json').read_text()))
            self.assertEqual(source.read_bytes(),original)
            self.assertEqual(boardctl.validate(root),[])
            before={str(p.relative_to(root)):p.read_bytes()for p in root.rglob('*')if p.is_file()}
            bad=Path(directory)/'bad.json';value=json.loads((examples/'form-answer.json').read_text());value['values']['tasks']['changes'][0]['value']='not a number';bad.write_text(json.dumps(value))
            answer_args[answer_args.index('--answer-file')+1]=bad
            self.assertEqual(cli(*answer_args)[0],2)
            args[-1]=' '
            self.assertEqual(cli(*args)[0],2)
            self.assertEqual({str(p.relative_to(root)):p.read_bytes()for p in root.rglob('*')if p.is_file()},before)
            # A message with a form and no report still needs its readable body.
            source.write_bytes(original.split(b'\n---\n')[0]+b'\n---\n \n')
            self.assertTrue(any('fallback' in issue for issue in boardctl.validate(root)))
            answer_args[answer_args.index('--answer-file')+1]=examples/'form-answer.json'
            answer_args[answer_args.index('--slug')+1]='invalid-source-reply'
            self.assertEqual(cli(*answer_args)[0],2)
