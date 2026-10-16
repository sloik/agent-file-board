import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import boardctl

class RepairsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.board=self.root/'.agent-board'
        self.cli('init',str(self.root),'--project-id','repair','--project-name','Repair')
        self.cli('join','test-human','--kind','human','--path',str(self.root))
        self.room=self.board/'rooms/general';self.bad=self.room/'broken.txt';self.bad.write_bytes(b'not a valid message\xff')
    def cli(self,*args):
        out=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(io.StringIO()): code=boardctl.main(list(args))
        return code,out.getvalue()
    def repair(self,*extra):
        return self.cli('repair','--path',str(self.root),'--message','rooms/general/broken.txt','--by','test-human','--reason','Malformed agent output',*extra)
    def test_invalid_file_does_not_block_post_recent_and_withdraw_restores_validation(self):
        original=self.bad.read_bytes()
        code,_=self.cli('post','--path',str(self.root),'--from','test-human','--to','all','--scope','room','--room','general','--thread','T001','--slug','healthy','--body','Healthy')
        self.assertEqual(code,0)
        code,out=self.cli('recent','--participant','test-human','--path',str(self.root));self.assertEqual(code,0)
        data=json.loads(out);self.assertEqual(len(data['messages']),1);self.assertEqual(data['invalid_count'],1)
        self.assertNotEqual(self.cli('validate','--path',str(self.root))[0],0)
        self.assertEqual(self.repair()[0],0)
        self.assertEqual(self.bad.read_bytes(),original)
        self.assertEqual(self.cli('validate','--path',str(self.root))[0],0)
        self.bad.write_bytes(original+b'changed')
        self.assertNotEqual(self.cli('validate','--path',str(self.root))[0],0)
    def test_correction_is_new_valid_message_and_valid_original_cannot_be_hidden(self):
        raw='FROM: test-human\nTO: all\nSCOPE: ROOM\nROOM: general\nTHREAD: T001-fixed\nDATE: 2026-10-16 12:00\nLANGUAGE: en\nREPLY-TO: -\nSTATUS: INFO\n---\nCorrected content.\n'
        replacement=self.root/'corrected.txt';replacement.write_text(raw)
        self.assertEqual(self.repair('--replacement-file',str(replacement))[0],0)
        record=json.loads(next((self.board/'repairs').glob('*.json')).read_text())
        new=self.board/record['replacement'];self.assertEqual(new.read_text(),raw)
        code,out=self.cli('recent','--participant','test-human','--path',str(self.root));self.assertEqual(code,0);self.assertEqual(json.loads(out)['messages'][0]['repair']['by'],'test-human')
        self.assertEqual(self.cli('validate','--path',str(self.root))[0],0)
        self.assertNotEqual(self.cli('repair','--path',str(self.root),'--message',record['replacement'],'--by','test-human','--reason','hide valid message')[0],0)
    def test_invalid_replacement_and_unsafe_targets_are_refused(self):
        replacement=self.root/'draft.txt';replacement.write_text('broken')
        self.assertNotEqual(self.repair('--replacement-file',str(replacement))[0],0)
        self.assertFalse((self.board/'repairs').exists())
        self.assertNotEqual(self.cli('repair','--path',str(self.root),'--message','../outside.txt','--by','test-human','--reason','test')[0],0)

    def test_strict_loop_skips_quarantined_bad_filename_and_keeps_healthy_messages(self):
        self.cli('post','--path',str(self.root),'--from','test-human','--to','all','--scope','room','--room','general','--thread','T001','--slug','healthy','--body','Healthy')
        healthy=next(self.room.glob('*_healthy.txt'))
        self.bad.write_bytes(healthy.read_bytes())
        self.assertEqual(self.repair()[0],0)
        import importlib.util
        script=Path(boardctl.__file__).parent/'skills/board-loop/scripts/board_loop.py'
        spec=importlib.util.spec_from_file_location('repair_loop',script);loop=importlib.util.module_from_spec(spec);spec.loader.exec_module(loop)
        config=boardctl.board_paths(self.root)[1]
        with contextlib.redirect_stderr(io.StringIO()): found=loop.messages(self.root,self.board,config,{'test-human'},'test-human')
        self.assertEqual(len(found),1)
        self.assertTrue(next(iter(found)).endswith(healthy.name))

    def test_forged_records_cannot_hide_valid_files_and_direct_scope_is_enforced(self):
        self.cli('post','--path',str(self.root),'--from','test-human','--to','all','--scope','room','--room','general','--thread','T001','--slug','healthy','--body','Healthy')
        healthy=next(self.room.glob('*_healthy.txt'))
        self.assertEqual(self.repair()[0],0)
        record_path=next((self.board/'repairs').glob('*.json'));record=json.loads(record_path.read_text())
        import hashlib
        record['target']=healthy.relative_to(self.board).as_posix();record['sha256']=hashlib.sha256(healthy.read_bytes()).hexdigest();record_path.write_text(json.dumps(record))
        self.assertNotEqual(self.cli('validate','--path',str(self.root))[0],0)
        code,out=self.cli('recent','--participant','test-human','--path',str(self.root));self.assertEqual(code,0);self.assertEqual(len(json.loads(out)['messages']),1)
        private=self.board/'direct/alpha-agent--bravo-agent/broken.txt';private.parent.mkdir(parents=True);private.write_bytes(b'broken')
        code,_=self.cli('repair','--path',str(self.root),'--message',private.relative_to(self.board).as_posix(),'--by','test-human','--reason','outside pair')
        self.assertNotEqual(code,0)
