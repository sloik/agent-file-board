"""Explicit local signing administration; shared metadata never supplies commands."""
import base64
import hashlib
import json
from pathlib import Path
import uuid
import sys

import board_identity as identity
import signing_core as core
import signing_runtime as runtime
import signing_usability as usability
from board_upgrade import safe_path


def session(root, state_dir=None):
    board, config, _, _ = identity._config(root)
    _, _, registry = identity._registry(root, config)
    return runtime.Session(root, config, registry, state_dir)


def current(s, participant):
    if identity._person(s.registry, participant).get("identity") is None:
        raise ValueError(usability.no_profile_message(s.root, participant))
    result = s.resolve(participant)
    head = result["head"]
    if head.fingerprint in result["revoked"]:
        raise ValueError(usability.revoked_message(s.root, participant, head.fingerprint, result["revoked"][head.fingerprint]))
    return head


def signed_packet(s, relative, raw, key=None):
    import boardctl
    headers = boardctl.parse_message_bytes(raw) if hasattr(boardctl, "parse_message_bytes") else None
    if headers is None:
        # Parse the same raw UTF-8 bytes that will be hashed; no reconstruction.
        text = raw.decode("utf-8")
        headers = {}
        for line in text.replace("\r\n", "\n").split("\n"):
            if line == "---":
                break
            if ": " in line:
                k, v = line.split(": ", 1)
                if k in headers:
                    raise ValueError("duplicate message header. Next: remove the repeated header line from the draft")
                headers[k] = v
    head = current(s, headers["FROM"])
    context = core.MessageContext(s.board_id, headers["FROM"], head.envelope_sha256, relative)
    minimum = s.minimum(relative, headers["THREAD"].split("-")[0])
    if minimum == "trusted" and s.state["pins"].get(headers["FROM"]) != head.fingerprint:
        raise ValueError(usability.unapproved_message(s, headers["FROM"], head, "outgoing scope requires a deliberately trusted current signer"))
    record = "sig_" + str(uuid.uuid4())
    if "SIGNATURE" in headers:
        raise ValueError("draft already declares a signature. Next: remove the SIGNATURE header from the draft; signing adds it")
    # Existing writer emits LF; refuse ambiguity rather than normalizing it.
    marker = b"\n---\n"
    if raw.count(marker) < 1:
        raise ValueError("draft has no canonical header/body separator. Next: write the draft with boardctl post, which produces the right shape")
    before, after = raw.split(marker, 1)
    final = before + b"\nSIGNATURE: " + core._json_bytes({"version": 1, "record": record}) + marker + after
    payload = core._json_bytes(core._statement(final, context))
    packet = {"version": 1, "kind": "message", "boardId": s.board_id,
              "participant": headers["FROM"], "profile": head.envelope_sha256,
              "keyId": head.fingerprint, "path": relative, "message": base64.b64encode(final).decode(),
              "payloadType": core.MESSAGE_TYPE, "payload": base64.b64encode(payload).decode()}
    if key is not None:
        envelope = core.sign_message(final, context, key)
        try:
            core.verify_message(envelope, head.descriptor, final, context)
        except ValueError as exc:
            detail = usability.key_mismatch_message(s, headers["FROM"], head, key, str(exc), relative)
            if detail is None:
                raise
            raise ValueError(detail) from exc
        return packet, envelope
    return packet, None


def publish(s, packet, envelope):
    import boardctl
    core._fields(packet, ("version", "kind", "boardId", "participant", "profile", "keyId", "path", "message", "payloadType", "payload"), "signing request")
    if type(packet["version"]) is not int or packet["version"] != 1 or packet["kind"] != "message" or packet["boardId"] != s.board_id or packet["payloadType"] != core.MESSAGE_TYPE:
        raise ValueError("unsupported/stale signing request. " + usability.PREPARE_AGAIN)
    head = current(s, packet["participant"])
    if (head.envelope_sha256, head.fingerprint) != (packet["profile"], packet["keyId"]):
        raise ValueError("profile/key changed since signing request. " + usability.PREPARE_AGAIN)
    raw = core._decode64(packet["message"])
    context = core.MessageContext(s.board_id, packet["participant"], packet["profile"], packet["path"])
    try:
        result = core.verify_message(envelope, head.descriptor, raw, context)
    except ValueError as exc:
        raise ValueError(usability.response_message(exc, packet["participant"], head, envelope)) from exc
    if result.payload != core._decode64(packet["payload"]):
        raise ValueError("response did not sign requested exact statement. Next: run boardctl signing respond --request REQUEST_FILE --key-file KEY_FILE --output RESPONSE_FILE again on this exact request")
    path = safe_path(s.board, packet["path"])
    # Validate routing/metadata using a disposable source, preserving final path.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / (".signing-check-" + uuid.uuid4().hex)
    try:
        temporary.write_bytes(raw)
        headers = boardctl.check_message(path, s.board, s.config, boardctl.ids(s.registry), source_path=temporary)
    finally:
        temporary.unlink(missing_ok=True)
    if headers["FROM"] != packet["participant"]:
        raise ValueError("signed request author mismatch. " + usability.PREPARE_AGAIN + " with --from set to the participant who signs")
    if s.minimum(packet["path"], headers["THREAD"].split("-")[0]) == "trusted" and s.state["pins"].get(headers["FROM"]) != head.fingerprint:
        raise ValueError(usability.unapproved_message(s, headers["FROM"], head, "outgoing scope requires a trusted signer") + ", then run signing publish again")
    ref = core.strict_json(headers["SIGNATURE"].encode())
    core._fields(ref, ("version", "record"), "SIGNATURE")
    import re
    if ref["version"] != 1 or type(ref["version"]) is not int or not re.fullmatch(r"sig_[a-f0-9-]{36}", ref["record"]):
        raise ValueError("invalid signature reference. " + usability.PREPARE_AGAIN + "; do not edit the message")
    sidecars = safe_path(s.board, str(path.parent.relative_to(s.board) / ".signatures"))
    sidecars.mkdir(exist_ok=True)
    sidecar = sidecars / (ref["record"] + ".json")
    # Every publication checks the persisted private revision as well as shared
    # bytes. A prepared request is not authority to bypass a later local floor,
    # trust removal, source revocation or profile change.
    latest = [s]
    def recheck():
        fresh = session(s.root, s.state_path.parent.parent)
        fresh_head = current(fresh, packet["participant"])
        if (fresh.config != s.config or fresh.registry != s.registry
                or fresh_head.envelope_sha256 != head.envelope_sha256
                or fresh.before != s.before):
            raise ValueError("signing context changed before publication: the board settings, participants, "
                             f"the profile of {packet['participant']} or your private signing state changed after this request was prepared. "
                             + usability.PREPARE_AGAIN)
        if fresh.minimum(packet["path"], headers["THREAD"].split("-")[0]) == "trusted" and fresh.state["pins"].get(headers["FROM"]) != fresh_head.fingerprint:
            raise ValueError(usability.unapproved_message(fresh, headers["FROM"], fresh_head, "outgoing scope requires a trusted signer") + ", then run signing publish again")
        if headers.get("REPLY-TO", "-") != "-":
            source = safe_path(s.board, str(path.parent.relative_to(s.board) / headers["REPLY-TO"]))
            source_headers = boardctl.check_message(source, fresh.board, fresh.config, boardctl.ids(fresh.registry))
            decision = fresh.evaluate(source, source_headers)
            if decision["eligibility"] != "eligible":
                raise ValueError(usability.reply_source_message("reply source excluded by signing requirements",
                                                                source.relative_to(s.board).as_posix(), decision, s.root))
            if "ANSWER-STATE" in headers:
                import answer_state
                claim = answer_state.metadata(headers, source_headers)
                if hashlib.sha256(source.read_bytes()).hexdigest() != claim['questionDigest']:
                    raise ValueError("ANSWER-STATE question bytes changed. Next: prepare the request again so it records the question as it is now")
        latest[0] = fresh
    publish_atomic(sidecar, envelope, guard=recheck)
    # A failed message publication may leave an immutable harmless orphan sidecar.
    publish_atomic(path, raw, guard=recheck)
    latest[0].evaluate(path, headers, raw)
    try:
        latest[0].save()
    except (OSError, ValueError):
        print("warning: message published; private verification history could not be saved", file=sys.stderr)
    return path


def publish_atomic(path, raw, guard=None):
    temporary = path.parent / (".signing-publish-" + uuid.uuid4().hex)
    try:
        identity._publish(temporary, raw)
        import os
        if guard is not None:
            guard()
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def command(args):
    root = Path(args.path).resolve()
    action = args.signing_action
    if action in ("keygen", "require", "check"):
        result, code = usability.run(action, root, args)
        print(json.dumps(result))
        return code
    s = session(root, args.state_dir)
    if action in ("profile", "transition", "update", "revoke"):
        result = administer(s, args)
    elif action == "adopt":
        s.state["floor"] = s.shared if args.replace_floor else runtime.merge_floor(s.floor, s.shared, s.config)
        s.save()
        result = {"boardId": s.board_id, "floor": s.state["floor"]}
    elif action == "trust":
        head = current(s, args.participant)
        if head.fingerprint != args.fingerprint or head.envelope_sha256 != args.profile:
            raise ValueError("explicit fingerprint/profile does not match verified current participant. "
                             f"Next: {usability.cmd('boardctl', 'identity', 'inspect', args.participant, '--path', root)}, "
                             "copy its fingerprint and profile, and compare the fingerprint with its owner through another channel before approving")
        s.state["pins"][args.participant] = head.fingerprint
        s.save()
        result = {"participant": args.participant, "fingerprint": head.fingerprint, "trust": "trusted"}
    elif action == "untrust":
        s.state["pins"].pop(args.participant, None)
        s.save()
        result = {"participant": args.participant, "trust": "unfamiliar"}
    elif action == "inspect":
        import boardctl
        path = safe_path(s.board, args.message)
        headers = boardctl.check_message(path, s.board, s.config, boardctl.ids(s.registry))
        result = s.evaluate(path, headers)
        s.save()
    elif action == "respond":
        packet = core.strict_json(identity._read(Path(args.request), 8388608), limit=8388608)
        key = runtime.private_key(args.key_file, root)
        if packet.get("kind") == "message":
            context = core.MessageContext(packet["boardId"], packet["participant"], packet["profile"], packet["path"])
            raw = core._decode64(packet["message"])
            envelope = core.sign_message(raw, context, key)
            if core._parse_envelope(envelope, core.MESSAGE_TYPE)[1] != core._decode64(packet["payload"]):
                raise ValueError("request statement differs from exact message")
        elif packet.get("kind") == "possession":
            envelope = core._sign_payload(core._decode64(packet["payload"]), runtime.POSSESSION, key)
        else:
            raise ValueError("unsupported signing request")
        identity._publish(Path(args.output), envelope)
        result = {"response": args.output}
    elif action == "publish":
        packet = core.strict_json(identity._read(Path(args.request), 8388608), limit=8388608)
        envelope = identity._read(Path(args.response), 65536)
        published = publish(s, packet, envelope)
        result = {"message": str(published.relative_to(root))}
        # Recording needs the signer's key, which an external signer keeps; say so (SPEC-002-062).
        import boardctl
        import history_recording
        thread = boardctl.parse_message(published).get("THREAD", "").split("-")[0]
        for line in history_recording.after_post(root, args.state_dir, s.config, published.parent.relative_to(s.board).as_posix(),
                                                 thread, packet["participant"], None, "published from an external signing request"):
            print(line, file=sys.stderr)
    else:
        raise ValueError("unknown signing action")
    print(json.dumps(result))
    return 0


def administer(s, args):
    participant = args.participant
    person = identity._person(s.registry, participant)
    if args.signing_action == "profile":
        key = runtime.private_key(args.key_file, s.root)
        snapshot = identity._read(Path(args.snapshot_file), 32768) if args.snapshot_file else identity._encode({k: v for k, v in person.items() if k != "identity"})
        raw = core.sign_profile(snapshot, s.board_id, key, previous=args.previous)
        identity._publish(Path(args.output), raw)
        return {"profile": hashlib.sha256(raw).hexdigest(), "output": args.output}
    resolved = s.resolve(participant)
    old = resolved["head"]
    if args.signing_action == "transition":
        raw = identity._read(Path(args.profile_file), 65536)
        new = core.verify_profile(raw, expected_sha256=args.sha256, board_id=s.board_id, participant=participant)
        if new.previous != old.envelope_sha256 or new.fingerprint == old.fingerprint:
            raise ValueError("transition needs a new key profile whose predecessor is current")
        statement = {"version": 1, "boardId": s.board_id, "participant": participant,
                     "fromProfile": old.envelope_sha256, "toProfile": new.envelope_sha256}
        raw = runtime.seal(statement, runtime.TRANSITION,
                           [runtime.private_key(args.key_file, s.root), runtime.private_key(args.new_key_file, s.root)])
        digest = hashlib.sha256(raw).hexdigest()
        runtime.event(raw, digest, runtime.TRANSITION, [old.descriptor, new.descriptor])
        identity._publish(Path(args.output), raw)
        return {"event": digest, "output": args.output}
    if args.expect_profile != old.envelope_sha256:
        raise ValueError("current profile changed; inspect before administering identity")
    new_person = dict(person)
    objects = []
    refs = list(person["identity"].get("events", []))
    if args.signing_action == "update":
        if old.fingerprint in resolved["revoked"]:
            raise ValueError("revoked key cannot authorize an update; independent recovery review required")
        raw = identity._read(Path(args.profile_file), 65536)
        new = core.verify_profile(raw, expected_sha256=args.sha256, board_id=s.board_id, participant=participant)
        if new.previous != old.envelope_sha256:
            raise ValueError("new profile must name the exact current predecessor")
        new_person = core.strict_json(new.snapshot, allow_floats=True)
        import boardctl
        diagnostic = boardctl.operator_error(new_person, s.registry)
        if diagnostic:
            raise ValueError(diagnostic)
        objects.append(("profiles", new.envelope_sha256, raw))
        if args.event_file:
            transition_raw = identity._read(Path(args.event_file), 65536)
            ref = hashlib.sha256(transition_raw).hexdigest()
            data = runtime.event(transition_raw, ref, runtime.TRANSITION, [old.descriptor, new.descriptor])
            if data != {"version": 1, "boardId": s.board_id, "participant": participant, "fromProfile": old.envelope_sha256, "toProfile": new.envelope_sha256}:
                raise ValueError("transition statement mismatch")
            refs.append(ref)
            objects.append(("events", ref, transition_raw))
        elif new.fingerprint != old.fingerprint:
            raise ValueError("key rotation needs dual-authorized --event-file")
        new_person["identity"] = {"version": 1, "profile": new.envelope_sha256, "events": sorted(set(refs))}
    else:
        statement = {"version": 1, "boardId": s.board_id, "participant": participant,
                     "authorizingProfile": old.envelope_sha256, "keyId": old.fingerprint, "status": args.status}
        if args.reason:
            statement["reason"] = args.reason
        raw = runtime.seal(statement, runtime.REVOCATION, [runtime.private_key(args.key_file, s.root)])
        ref = hashlib.sha256(raw).hexdigest()
        runtime.event(raw, ref, runtime.REVOCATION, [old.descriptor])
        refs.append(ref)
        objects.append(("events", ref, raw))
        new_person["identity"] = dict(person["identity"], events=sorted(set(refs)))
    if len(refs) > 64:
        raise ValueError("lifecycle event budget")
    board, config, config_path, config_before = identity._config(s.root)
    registry_path, before, registry = identity._registry(s.root, config)
    if registry != s.registry or config != s.config:
        raise ValueError("registration changed during identity review")
    created = []
    with identity._write_lock(board):
        try:
            for kind, digest, raw in objects:
                destination = safe_path(board, f"identity/{kind}/{digest}.json")
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    if identity._read(destination, 65536) != raw:
                        raise ValueError("immutable lifecycle bytes conflict")
                else:
                    created.append((destination, identity._publish(destination, raw)))
            registry["participants"] = [new_person if p["id"] == participant else p for p in registry["participants"]]
            candidate = runtime.Session(s.root, config, registry, args.state_dir)
            candidate.resolve(participant)
            if identity._read(config_path) != config_before:
                raise ValueError("board config changed")
            identity._atomic_replace(registry_path, before, identity._encode(registry))
        except BaseException:
            for path, owned in reversed(created): identity._remove_owned(path, owned)
            raise
    candidate.save()
    return {"participant": participant, "profile": new_person["identity"]["profile"],
            "lifecycle": args.status if args.signing_action == "revoke" else "updated", "trust": "local pins unchanged"}


def add_parser(commands):
    cli = commands.add_parser("signing", help="Local trust/policy and portable explicit signing requests")
    actions = cli.add_subparsers(dest="signing_action", required=True)
    for name in ("adopt", "trust", "untrust", "inspect", "respond", "publish", "profile", "transition", "update", "revoke", "keygen", "require", "check"):
        sub = actions.add_parser(name)
        sub.add_argument("--path", default=".")
        sub.add_argument("--state-dir")
        if name == "keygen":
            sub.add_argument("--output", help="new private key file outside the project; default ~/private/afb/PROJECT-ID/PARTICIPANT.json (AGENT_FILE_BOARD_KEY_DIR replaces ~/private/afb)")
            sub.add_argument("--participant", help="participant ID: names the default key file and fills the printed next commands")
        if name == "require":
            target = sub.add_mutually_exclusive_group(required=True)
            target.add_argument("--board", action="store_true", help="require for the whole board")
            target.add_argument("--scope", help="physical folder such as rooms/releases or direct/a--b")
            sub.add_argument("--thread", help="narrow --scope to one thread such as T001")
            sub.add_argument("--minimum", choices=("trusted", "optional"), required=True)
            sub.add_argument("--weaken", action="store_true", help="allow lowering an existing trusted requirement")
        if name == "check":
            sub.add_argument("--from", dest="sender", required=True, help="participant who would post")
            sub.add_argument("--scope", required=True, help="physical folder such as rooms/releases or direct/a--b")
            sub.add_argument("--thread", help="thread such as T001")
            sub.add_argument("--signing-key-file", help="the private key file you would post with")
        if name == "adopt": sub.add_argument("--replace-floor", action="store_true", help="deliberately replace the private requirement floor after review")
        if name in ("trust", "untrust"): sub.add_argument("--participant", required=True)
        if name == "trust":
            sub.add_argument("--fingerprint", required=True)
            sub.add_argument("--profile", required=True)
        if name == "inspect": sub.add_argument("--message", required=True)
        if name in ("respond", "publish"): sub.add_argument("--request", required=True)
        if name == "respond":
            sub.add_argument("--key-file", required=True)
            sub.add_argument("--output", required=True)
        if name == "publish": sub.add_argument("--response", required=True)
        if name in ("profile", "transition", "update", "revoke"):
            sub.add_argument("--participant", required=True)
        if name in ("profile", "transition", "revoke"):
            sub.add_argument("--key-file", required=True)
        if name == "profile":
            sub.add_argument("--snapshot-file")
            sub.add_argument("--previous")
        if name in ("profile", "transition"): sub.add_argument("--output", required=True)
        if name in ("transition", "update"):
            sub.add_argument("--profile-file", required=True)
            sub.add_argument("--sha256", required=True)
        if name == "transition": sub.add_argument("--new-key-file", required=True)
        if name in ("update", "revoke"): sub.add_argument("--expect-profile", required=True)
        if name == "update": sub.add_argument("--event-file")
        if name == "revoke":
            sub.add_argument("--status", choices=("retired", "compromised"), required=True)
            sub.add_argument("--reason")
        sub.set_defaults(func=command)
