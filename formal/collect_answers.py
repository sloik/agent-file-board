"""Observe the production acceptance resolver; never compute expected winners here."""
import copy
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import answer_state
DIGEST = 'f' * 64
AUTHOR = 'owner'


def records():
    def record(name, **opts):
        return dict(file=name + '.txt', sha256=name.encode().hex().rjust(64, '0'),
                    **dict(author='respondent', answer=True, eligible=True, state=None) | opts)
    def claim():
        return dict(version=1, questionDigest=DIGEST, parents=[], winner=None)
    a, b, h = record('a', state=claim()), record('b', state=claim()), record('h')
    def resolution(name, parents, winner, author=AUTHOR):
        return record(name, author=author, answer=False, state=dict(version=1, questionDigest=DIGEST,
                      parents=list(map(answer_state.reference, parents)), winner=answer_state.reference(winner)))
    ra, rb = resolution('ra', [a, b], a), resolution('rb', [a, b], b)
    return dict(a=a, b=b, c=record('c', state=claim()), h=h, legacy=resolution('legacy', [], h), ra=ra, rb=rb, merge=resolution('merge', [ra, rb], a),
                u=resolution('u', [], a, 'intruder'))


def trace(scenario, actions, mutation=''):
    module = answer_state
    if mutation:
        source = (ROOT / 'answer_state.py').read_text()
        if mutation == 'conflict':
            source = source.replace("len(choices) == 1 else 'conflict'", "len(choices) >= 1 else 'conflict'")
        if mutation == 'first':
            source = source.replace("result['winner'] = result['choices'][0]", "result['winner'] = result['history'][-1]")
        if mutation == 'authority':
            source = source.replace("require(r.get('author') == author and not r.get('answer'), 'unauthorized explicit acceptance')", 'pass')
        if mutation == 'trust':
            source = source.replace("require(r.get('eligible'), 'acceptance evidence is unavailable or signing-excluded')", 'pass')
        module = types.ModuleType('mutated_answer_state')
        exec(compile(source, 'mutated_answer_state.py', 'exec'), module.__dict__)
    all_records, visible, denied = records(), [], False
    def observe():
        rows = [dict(copy.deepcopy(all_records[name]), eligible=not (denied and name == 'a')) for name in visible]
        result = module.resolve(DIGEST, rows, AUTHOR)
        return dict(visible={'$set': visible.copy()}, denied=denied, status=result['status'],
                    winner=result['winner']['file'].removesuffix('.txt') if result['winner'] else 'none')
    states = [observe()]
    for action in actions:
        if action == 'trust':
            denied = not denied
        elif action not in visible:
            visible.append(action)
        states.append(observe())
    return dict(model='AnswerAcceptance', scenario=scenario, states=states)


def traces(mutant=False):
    if mutant:
        return [trace('answer mutant: ignores offline conflict', ['a','b'], 'conflict'),
                trace('answer mutant: later history replaces first', ['a','h'], 'first'),
                trace('answer mutant: accepts excluded claim', ['a','trust'], 'trust'),
                trace('answer mutant: unauthorized resolution', ['a','u'], 'authority')]
    return [trace('answer: first and backdated history survive reload', ['a','h','a']),
            trace('answer: offline fork and explicit resolution', ['a','b','ra']),
            trace('answer: concurrent resolutions and merge', ['b','a','rb','ra','merge']),
            trace('answer: out-of-order missing evidence', ['merge','ra','rb','a','b']),
            trace('answer: trust exclusion blocks promotion', ['a','h','trust','trust']),
            trace('answer: unauthorized acceptance blocked', ['a','u']),
            trace('answer: legacy history and reordered convergence', ['h','b','a','ra']),
            trace('answer: late offline claim reopens conflict', ['a','b','ra','c']),
            trace('answer: explicit legacy anchoring', ['legacy','h'])]
