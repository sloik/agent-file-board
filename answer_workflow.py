"""Filesystem/signing adapter for the data-only answer acceptance reducer."""
import hashlib
import json
from pathlib import Path
import tempfile
import answer_state


def scan(root, question, state_dir=None):
    import boardctl
    import signing_commands
    board, config, _, registry = boardctl.board_paths(root)
    known = boardctl.ids(registry)
    path = Path(question)
    if not path.is_absolute():
        path = board / path
    path = path.absolute()
    answer_state.require(path.is_relative_to(board.absolute()), 'question outside board')
    h = boardctl.check_message(path, board, config, known)
    answer_state.require('QUESTION' in h and 'ANSWER' not in h, 'target is not a question')
    import message_repairs
    quarantined, _ = message_repairs.scan(board, config, known, lambda p: boardctl.message_error(p, board, config, known))
    signing = signing_commands.session(root, state_dir)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    records = []
    for message in path.parent.glob('*.txt'):
        if message == path or message.is_symlink():
            continue
        try:
            headers = boardctl.parse_message(message)
            if headers.get('REPLY-TO') != path.name or not ('ANSWER' in headers or 'ANSWER-STATE' in headers):
                continue
            headers = boardctl.check_message(message, board, config, known)
            state = answer_state.metadata(headers, h)
            records.append(dict(file=message.name, sha256=hashlib.sha256(message.read_bytes()).hexdigest(),
                                author=headers['FROM'], answer='ANSWER' in headers, state=state,
                                eligible=message.relative_to(board).as_posix() not in quarantined and signing.evaluate(message, headers)['eligibility'] == 'eligible'))
        except (ValueError, OSError, KeyError, TypeError, RecursionError):
            continue
    result = answer_state.resolve(digest, records, h['FROM'])
    if path.relative_to(board).as_posix() in quarantined or signing.evaluate(path, h)['eligibility'] != 'eligible':
        result.update(status='blocked', winner=None, reason='question is signing-excluded')
    result['questionDigest'] = digest
    return path, h, result


def command(args):
    import boardctl
    path, h, result = scan(Path(args.path).resolve(), args.question, args.signing_state_dir)
    if args.action == 'inspect':
        print(json.dumps(result, sort_keys=True))
        return 0
    answer_state.require(args.sender == h['FROM'], 'only question author may resolve')
    answer_state.require(result['status'] in ('conflict', 'legacy'), 'no unresolved choice to accept')
    expected = json.loads(args.expected_heads)
    answer_state.require(expected == result['heads'], 'heads changed; inspect and review again')
    choices = result['choices'] if result['status'] == 'conflict' else result['history']
    winner = next((c for c in choices if c['file'] == args.winner), None)
    answer_state.require(winner is not None, 'winner is not an eligible reviewed choice')
    state = dict(version=1, questionDigest=result['questionDigest'], parents=result['heads'], winner=winner)
    # Reuse the normal writer, including signing and immutable publication guards.
    with tempfile.TemporaryDirectory(prefix='afb-answer-choice-') as temp:
        value = Path(temp) / 'state.json'
        value.write_text(json.dumps(state), encoding='utf-8')
        options = ['post', '--path', args.path, '--from', args.sender, '--to', h['FROM'],
                   '--scope', h['SCOPE'].lower(), '--thread', h['THREAD'].split('-')[0],
                   '--slug', 'answer-acceptance-' + __import__('uuid').uuid4().hex,
                   '--status', 'REPLY', '--reply-to', path.name,
                   '--answer-state-file', str(value), '--body', 'Explicitly accepted answer: ' + args.winner]
        if h['SCOPE'] == 'ROOM':
            options.extend(['--room', h['ROOM']])
        else:
            options[options.index('--to') + 1] = next(p.strip() for p in h['DIRECT-PARTICIPANTS'].split(',') if p.strip() != args.sender)
        for name in ('signing_key_file', 'signing_state_dir', 'prepare_signing'):
            if getattr(args, name, None):
                options.extend(['--' + name.replace('_', '-'), getattr(args, name)])
        return boardctl.main(options)
