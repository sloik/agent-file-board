import contextlib
import io
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest

import answer_state as A
import boardctl
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'formal'))
from collect_answers import records, DIGEST, AUTHOR


class AnswerStateTests(unittest.TestCase):
    def test_permutations_reload_forks_resolution_and_trust(self):
        rows = records()
        for names, expected in [([], 'none'), (['h'], 'legacy'), (['a','h'], 'accepted'),
                                (['a','b'], 'conflict'), (['a','b','ra'], 'accepted'),
                                (['a','b','ra','rb'], 'conflict'),
                                (['a','b','ra','rb','merge'], 'accepted'),
                                (['a','u'], 'blocked'), (['merge','a'], 'blocked')]:
            for permutation in itertools.permutations(names):
                result = A.resolve(DIGEST, [rows[n] for n in permutation], AUTHOR)
                self.assertEqual(result['status'], expected, permutation)
                if expected == 'accepted':
                    self.assertEqual(result['winner'], A.reference(rows['a']))
        excluded = dict(rows['a'], eligible=False)
        self.assertEqual(A.resolve(DIGEST, [excluded, rows['h']], AUTHOR)['status'], 'blocked')
        changed = dict(rows['a'], state={**rows['a']['state'], 'questionDigest':'e'*64})
        self.assertEqual(A.resolve(DIGEST, [changed,rows['h']], AUTHOR)['status'], 'blocked')

    def test_shared_contract_fixtures(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/answer-acceptance.json').read_text())
        for case in fixture['cases']:
            rows = [dict(fixture['records'][name], eligible=name not in case.get('excluded', [])) for name in case['visible']]
            result = A.resolve(fixture['questionDigest'], rows, fixture['author'])
            self.assertEqual(result['status'],case['status'],case['name'])
            self.assertEqual(result['winner']['file'] if result['winner'] else None,
                             fixture['records'][case['winner']]['file'] if case['winner'] else None,case['name'])

    def test_graph_limits_are_independent_of_enumeration_and_memoization(self):
        import hashlib
        a = records()['a']
        self.assertEqual(A.resolve(DIGEST,[a]*4097,AUTHOR)['status'],'blocked')
        deep = [a]
        for i in range(130):
            deep.append(dict(file='depth'+str(i)+'.txt',sha256=hashlib.sha256(str(i).encode()).hexdigest(),
                             author=AUTHOR,answer=False,eligible=True,state=dict(version=1,questionDigest=DIGEST,
                             parents=[A.reference(deep[-1])],winner=A.reference(a))))
        for rows in [deep,list(reversed(deep))]:
            self.assertEqual(A.resolve(DIGEST,rows,AUTHOR)['status'],'blocked')
        for rows in [deep[:129],list(reversed(deep[:129]))]:
            self.assertEqual(A.resolve(DIGEST,rows,AUTHOR)['status'],'accepted')

    def test_closed_metadata_refusals(self):
        s = records()['a']['state']
        for invalid in [{**s, 'version': True}, {**s, 'extra': 1}, {**s, 'parents': [dict(file='../bad.txt',sha256=DIGEST)]},
                        {**s, 'parents': [A.reference(records()['a'])]}, {**s,'questionDigest': []}]:
            with self.assertRaises(ValueError):
                A.validate(invalid)

    def test_cli_first_claim_backdate_fork_and_guarded_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'project'
            output, errors = io.StringIO(), io.StringIO()
            def cli(*args):
                output.seek(0); output.truncate(); errors.seek(0); errors.truncate()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    code = boardctl.main(list(map(str, args)))
                return code, output.getvalue().strip(), errors.getvalue()
            self.assertEqual(cli('init',root,'--project-id','acceptance','--project-name','Acceptance')[0],0)
            for who in ['owner-human','respondent-human']:
                self.assertEqual(cli('join',who,'--kind','human','--path',root)[0],0)
            question=Path(directory)/'question.json';question.write_text(json.dumps(dict(id='pick',type='single',prompt='Pick one',options=[dict(id='a',label='A'),dict(id='b',label='B')])) )
            answer=Path(directory)/'answer.json';answer.write_text('{"question":"pick","selected":["a"]}')
            common=['--path',root,'--to','owner-human','--scope','room','--room','general','--thread','T001','--body','Readable choice']
            code,rel,err=cli('post',*common,'--from','owner-human','--slug','question','--question-file',question);self.assertEqual(code,0,err)
            qpath=root/rel;original=qpath.read_bytes()
            code,rel,err=cli('post',*common,'--from','respondent-human','--slug','first','--reply-to',qpath.name,'--answer-file',answer);self.assertEqual(code,0,err)
            first=root/rel;state=json.loads(boardctl.parse_message(first)['ANSWER-STATE'])
            qrel=qpath.relative_to(root/'.agent-board')
            code,raw,err=cli('answers','inspect','--path',root,'--question',qrel);self.assertEqual(code,0,err);accepted=json.loads(raw)
            self.assertEqual(accepted['winner']['file'],first.name)
            code,rel,err=cli('post',*common,'--from','respondent-human','--slug','backdated','--at','2026-01-01T12:00','--reply-to',qpath.name,'--answer-file',answer);self.assertEqual(code,0,err)
            self.assertNotIn('ANSWER-STATE',boardctl.parse_message(root/rel))
            self.assertEqual(json.loads(cli('answers','inspect','--path',root,'--question',qrel)[1])['winner'],accepted['winner'])
            claim=Path(directory)/'claim.json';claim.write_text(json.dumps(state))
            code,rel,err=cli('post',*common,'--from','respondent-human','--slug','offline','--reply-to',qpath.name,'--answer-file',answer,'--answer-state-file',claim);self.assertEqual(code,0,err)
            fork=json.loads(cli('answers','inspect','--path',root,'--question',qrel)[1]);self.assertEqual(fork['status'],'conflict')
            args=['answers','accept','--path',root,'--question',qrel,'--from','owner-human','--winner',first.name]
            self.assertNotEqual(cli(*args,'--expected-heads','[]')[0],0)
            self.assertEqual(cli(*args,'--expected-heads',json.dumps(fork['heads']))[0],0)
            resolved=json.loads(cli('answers','inspect','--path',root,'--question',qrel)[1]);self.assertEqual(resolved['winner'],accepted['winner'])
            self.assertEqual(qpath.read_bytes(),original)
            self.assertEqual(boardctl.validate(root),[])
