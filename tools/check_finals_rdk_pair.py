"""Offline pairing check. Arguments: published RDK checkout, built test_finals_wire executable."""
from collections import Counter
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

rdk, fixture = map(Path, sys.argv[1:3])
sys.path[:0] = [str(rdk / "competition_rescue"), str(rdk / "vision")]
import protocol as p
import state_machine as sm
from rescue_vision.vision_protocol import config_frame

GREEN, CORE, ORANGE, BLUE = "green_supply", "core_black", "injured_orange", "danger_cyan"
RED = p.CMD_VALID | p.CMD_RED_SIDE


def run(stage, first, messages):
    inputs = [config_frame(1, 0x11, 1).hex()]
    for seq, (action, frame, payload) in enumerate(messages, 2):
        inputs.append((p.command_context_frame(seq, 7, action, frame) + payload(seq)).hex())
    result = subprocess.run([str(fixture.resolve()), stage, str(int(first))],
                            input="\n".join(inputs)+"\n", text=True, capture_output=True, check=True)
    replies = []
    for line in result.stdout.splitlines():
        raw = bytes.fromhex(line)
        ctx, status = raw[:15], raw[15:]
        for msg, code in ((ctx, 0x1e), (status, 0x17)):
            assert len(msg) == 15 and msg[:3] == bytes((0xa3,0xb3,code))
            assert int.from_bytes(msg[12:14], "little") == p.crc16_modbus(msg[2:12])
            assert msg[14] == 0xc3
        assert ctx[3] == status[3]
        replies.append((int.from_bytes(ctx[4:6], "big"),int.from_bytes(ctx[6:8], "big"),
                        ctx[8],ctx[9] & 7,status[4],status[5]))
    assert len(replies) == len(messages), (stage, result.stdout)
    return replies


def cargo(left, right):
    counts = Counter()
    for name, n in (left, right):
        if n: counts[name] += n
    return sm.CargoAudit(left_class=left[0], right_class=right[0], left_count=left[1],
        right_count=right[1], total_count=left[1]+right[1],
        class_counts=tuple(sorted(counts.items())),
        left_green_count=left[1] if left[0]==GREEN else 0,
        right_green_count=right[1] if right[0]==GREEN else 0,
        left_class_counts=((left[0],left[1]),) if left[1] else (),
        right_class_counts=((right[0],right[1]),) if right[1] else (),
        danger_present=BLUE in counts, injury_mixed=ORANGE in counts and len(counts)>1)


def planner(first, target):
    m=sm.CompetitionMission(sm.CompetitionSettings(side="red",initial_stash_enabled=False))
    m.first_common_delivered=first
    m._select_batch(sm.CargoBatch((7,), (target,), "injury" if target==ORANGE else "material"))
    return m


def audit_frames(m,a):
    payload=m._audit_payload(a)
    return [(11,10+i,replace(payload,stable=True,audit_id=i+1).frame) for i in range(2)]


none=("none",0)
for first,target,left,right,legal in [
    (False,GREEN,(GREEN,1),none,True), (False,GREEN,(CORE,1),none,False),
    (False,GREEN,(GREEN,2),none,False), (True,CORE,(ORANGE,1),none,False),
    (True,ORANGE,(CORE,1),none,True), (True,ORANGE,(GREEN,1),(CORE,2),True),
    (True,GREEN,(GREEN,1),(ORANGE,1),False), (True,GREEN,(GREEN,1),(BLUE,1),False),
    (True,GREEN,(CORE,2),(GREEN,2),False)]:
    m,a=planner(first,target),cargo(left,right)
    assert m._audit_valid(a) == legal
    last=run("audit",first,audit_frames(m,a))[-1]
    assert last[:3]==(7,11,p.CMD_CARGO_AUDIT) and last[4]&0x40,(a,last)
    assert bool(last[4]&0x10)==legal and (last[5]==22)==legal,(target,left,right,last)
    if legal: assert m._audit_payload(a).destination_injury == (left[0]==ORANGE)
print("Actual-cargo policy: nine RDK audits matched FinalRun decisions and status frames")

for side in ("left","right"):
    m=planner(False,GREEN)
    a=cargo((GREEN,1),(BLUE,1)) if side=="left" else cargo((BLUE,1),(GREEN,1))
    m._arm_disperse(sm.StmSnapshot(),side,keep_count=1,audit=a)
    action=(12,0,m.disperse_command.to_frame)
    replies=run("split",False,audit_frames(m,a)+[action,action])
    assert all(x[:4]==(7,12,p.CMD_DISPERSE_PILE,1) and x[5]==25 for x in replies[-2:]),replies
print("Ordinary left/right separation and identical action retransmission passed")

for side in ("left","right"):
    m=planner(True,CORE)
    a=cargo((CORE,1),(ORANGE,1)) if side=="left" else cargo((ORANGE,1),(CORE,1))
    assert not m._audit_valid(a) and m._preferred_keep_side(a)==side
    m._arm_disperse(sm.StmSnapshot(),side,keep_count=1,audit=a)
    assert not m.disperse_command.flags&p.CMD_KEEP_ORANGE
    replies=run("split",True,audit_frames(m,a)+[(12,0,m.disperse_command.to_frame)]*2)
    assert all(x[:4]==(7,12,p.CMD_DISPERSE_PILE,1) and x[5]==25 for x in replies[-2:]),replies
stash=planner(True,CORE)
stash.selected_batch=replace(stash.selected_batch,destination="stash",initial_stash=True)
single=cargo((ORANGE,1),none)
last=run("audit",True,audit_frames(stash,single))[-1]
assert stash._audit_valid(single) and last[4]&0x10 and last[5]==22,last
print("Casualty/material mixed audits retain the real material side; opening relocation remains available")

def req(code,flags=RED,a=0,b=0,u=0):
    return lambda seq:p.mission_frame(seq,code,flags,a,b,u)

for opcode in (p.CMD_RELEASE_LEFT,p.CMD_RELEASE_RIGHT,p.CMD_RELEASE_BOTH):
    m=planner(False,GREEN)
    actual=run("split",False,audit_frames(m,cargo((GREEN,1),(BLUE,1)))+
               [(12,0,req(opcode))])[-1]
    assert actual[:3]==(7,12,opcode) and actual[3]&1,actual
print("Ordinary unilateral release and abandonment without retained side passed")

def legacy(a,b,flags):
    def packet(seq):
        f=bytearray(p.mission_frame(seq,p.CMD_DISPERSE_PILE,RED|p.CMD_SIDE_VALID))
        f[5]=flags
        f[6:8]=a.to_bytes(2,"big",signed=True)
        f[8:10]=b.to_bytes(2,"big",signed=True)
        f[12:14]=p.crc16_modbus(f[2:12]).to_bytes(2,"little")
        return bytes(f)
    return packet

for a,b,flags in ((10,0,RED),(-10,1,RED),(0,0,RED),(0,0,RED|p.CMD_FIRST_GREEN_BUMP)):
    m=planner(False,GREEN)
    replies=run("split",False,audit_frames(m,cargo((GREEN,1),(BLUE,1)))+[(12,12,legacy(a,b,flags))])
    assert replies[-1][3]&4 and replies[-1][1]==11 and replies[-1][5]!=25,replies
print("Legacy pre-turn, mid-turn brake, unassigned turn and bump rejected")

r=run("relook",False,[(11,15,req(p.CMD_APPROACH_TARGET,RED|p.CMD_DISTANCE_VALID|p.CMD_APPROACH_RANGE,0,12000,5))]*2)
assert all(x[:3]==(7,11,p.CMD_APPROACH_TARGET) and x[5]==3 for x in r),r
for u in (0,1):
    m=planner(False,GREEN)
    m.state=sm.CompetitionState.TASK_COMPLETE
    m.carried_manifest=(GREEN,)
    m.confirmed_delivery_destination="material"
    m.delivery_completion_basis="delivery_visual_confirmed" if u==0 else "delivery_verify_timeout"
    cmds=[(11,0,lambda seq:p.enter_safe_zone_frame(seq,90,True)),(12,0,m._task_complete_command().to_frame)]
    last=run("delivery",False,cmds)[-1]
    assert last[:4]==(7,12,p.CMD_TASK_COMPLETE,3) and last[5]==16 and not last[4]&2,last
    task, action, op, status, flags, mode = last
    reply=sm.StmSnapshot(age_ms=0, mode=mode, flags=flags, task_id=task, action_id=action,
        context_valid=True, context_matches=(task, action)==(7,12), accepted_command=op, action_status=status)
    assert not m._observe_delivery_completion(replace(reply, context_matches=False))
    for _ in range(2):
        assert m._observe_delivery_completion(reply)
        assert m.first_common_delivered == (u == 0) and m.delivery_count == int(u == 0)
print("Empty-claw relook, confirmed and unconfirmed release/exit handoffs passed")

assert run("boot",False,[]) == []
move=lambda distance: req(p.CMD_BULLDOZER_STEP, RED | (13<<4), distance, 0, 9000)
rs=run("station",True,[(11,0,move(1200)),(11,0,move(0))])
assert rs[0][:4]==(7,11,p.CMD_BULLDOZER_STEP,1) and rs[-1][:4]==(7,11,p.CMD_BULLDOZER_STEP,3),rs
for code,flags,a,b,u in (
    (p.CMD_CORRIDOR_NUDGE,RED|p.CMD_SIDE_VALID,100,228,9000),
    (p.CMD_CLEAR_SAFE_ZONE,RED,200,150,0)):
    r=run("gate",True,[(11,0,req(code,flags,a,b,u))])[-1]
    assert r[:4]==(7,11,code,1),r
print("Start CONFIG and reverse, step13 start/finish, gate nudge and sweep acceptance passed")

m=planner(True,CORE)
before=audit_frames(m,cargo((CORE,1),none))
after=audit_frames(m,cargo((ORANGE,1),none))
after=[(13,frame+10,fn) for _,frame,fn in after]
grab=(12,0,lambda seq:p.grab_frame(seq,True))
replies=run("grab",True,before+[grab]+after)
assert replies[2][:3]==(7,12,p.CMD_GRAB_CONFIRMED) and replies[2][5]==23,replies
assert replies[-1][:3]==(7,13,p.CMD_CARGO_AUDIT) and replies[-1][5]==23 and not replies[-1][4]&0x10,replies
assert replies[-1][4]&0x40,replies
print("Open audit core -> simulated close -> actual single casualty stays invalid for transport")
