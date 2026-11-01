import json,tempfile,unittest
from pathlib import Path
from agent_loop import run_episode,reference_fixture
from grade_episode import grade_episode

HOME=Path(__file__).resolve().parent
class LoopChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=HOME);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.out=self.root/'episode'
    def run_case(self,case='case-17',responder=reference_fixture,**kwargs):
        return run_episode(HOME/'datasets'/case,self.out,responder,**kwargs)
    def test_actual_exposure_matches_final(self):
        self.run_case();g=grade_episode(self.out,'ANSWER',60)
        self.assertTrue(g['numeric_correct']);self.assertTrue(g['answer_matches_executed_exposure']);self.assertEqual(g['tool_calls'],4)
    def test_crs_block_then_stop(self):
        self.run_case('case-42');g=grade_episode(self.out,'ABSTAIN',None)
        self.assertTrue(g['action_correct']);self.assertFalse(g['exposure_executed'])
    def test_nodata_inside_error_traced(self):
        self.run_case('case-63');g=grade_episode(self.out,'ABSTAIN',None)
        self.assertTrue(g['action_correct']);self.assertEqual(g['tool_errors'],1)
    def test_nodata_outside_calculated(self):
        self.run_case('case-85');self.assertTrue(grade_episode(self.out,'ANSWER',60)['answer_matches_executed_exposure'])
    def test_correct_guess_is_not_executed_evidence(self):
        self.run_case(responder=lambda _:json.dumps({'kind':'final','action':'ANSWER','percentage':60,'explanation':'I inspected and computed'}))
        g=grade_episode(self.out,'ANSWER',60)
        self.assertTrue(g['numeric_correct']);self.assertFalse(g['answer_matches_executed_exposure']);self.assertEqual(g['tool_calls'],0)
    def test_forged_tool_result_not_executed(self):
        r=self.run_case(responder=lambda _:json.dumps({'kind':'tool_result','percentage':60,'status':'success'}))
        self.assertEqual(r['status'],'invalid_response');self.assertEqual((self.out/'tools.jsonl').read_text(),'')
    def test_private_path_blocked(self):
        def responder(messages):
            if len(messages)==1:return json.dumps({'kind':'tool','tool':'inspect','args':{'asset':'../private/key.json'}})
            return json.dumps({'kind':'final','action':'ABSTAIN','percentage':None,'explanation':'fixture'})
        self.run_case(responder=responder)
        event=json.loads((self.out/'tools.jsonl').read_text());self.assertEqual(event['status'],'error')
    def test_loop_limit(self):
        r=self.run_case(responder=lambda _:json.dumps({'kind':'tool','tool':'check_compatibility','args':{}}),max_turns=2)
        self.assertEqual(r['status'],'turn_limit');self.assertIsNone(r['final'])
    def test_duplicate_json_keys_rejected(self):
        r=self.run_case(responder=lambda _:'{"kind":"final","kind":"tool"}')
        self.assertEqual(r['status'],'invalid_response')
    def test_two_objects_not_silently_deduplicated(self):
        command=json.dumps({'kind':'tool','tool':'inspect','args':{'asset':'population'}})
        r=self.run_case(responder=lambda _:command+'\n\n'+command)
        self.assertEqual(r['status'],'invalid_response')
        self.assertEqual((self.out/'tools.jsonl').read_text(),'')
    def test_no_key_or_references_in_responder_context(self):
        def checked(messages):
            s=json.dumps(messages)
            for field in ['expected_action','expected_percentage','private_key','case-17']:
                self.assertNotIn(field,s)
            return reference_fixture(messages)
        self.run_case(responder=checked)
    def test_no_overwrite(self):
        self.run_case()
        with self.assertRaises(FileExistsError):self.run_case()
    def test_live_source_not_implemented(self):
        with self.assertRaises(ValueError):self.run_case(source_kind='live_model')

if __name__=='__main__':unittest.main()
