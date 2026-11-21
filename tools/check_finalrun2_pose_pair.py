"""Real upper publication -> production C parser/Task -> real paired replies.

Arguments: RDK source directory, test_finals_wire executable. Hardware motion,
encoder positions and camera evidence are simulated; no serial port is opened.
"""
from dataclasses import replace
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading

rdk, executable = (Path(x).resolve() for x in sys.argv[1:3])
sys.path[:0] = [str(rdk/'competition_rescue/tests'), str(rdk/'competition_rescue'), str(rdk/'vision')]
import test_pose_delivery as check
import protocol as p
import state_machine as sm
from rescue_vision.vision_protocol import config_frame


class Wire:
    def __init__(self, side, stage="flow"):
        self.process = subprocess.Popen([str(executable),stage,"1"],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.lines = queue.Queue()
        def read():
            for line in self.process.stdout:
                self.lines.put(line)
            self.lines.put("")
        threading.Thread(target=read,daemon=True).start()
        self.process.stdin.write(config_frame(1,0x11 if side=="red" else 0x12,1).hex()+"\n")
        self.process.stdin.flush()
        self.now=100
        self.path=0
        self.tx_count=0
        self.last_payload=()

    def exchange(self,line):
        self.process.stdin.write(line+"\n");self.process.stdin.flush()
        try:
            value=self.lines.get(timeout=5)
        except queue.Empty:
            self.process.kill()
            raise AssertionError("fixture did not emit a reply")
        assert value, self.process.stderr.read()
        raw=bytes.fromhex(value)
        assert len(raw)==30
        ctx,status=raw[:15],raw[15:]
        for frame in (ctx,status):
            assert int.from_bytes(frame[12:14],"little")==p.crc16_modbus(frame[2:12])
        return sm.StmSnapshot(age_ms=0,context_valid=True,task_id=int.from_bytes(ctx[4:6],"big"),
            action_id=int.from_bytes(ctx[6:8],"big"),accepted_command=ctx[8],action_status=ctx[9]&7,
            rejected_action_id=int.from_bytes(ctx[10:12],"big"),flags=status[4],mode=status[5],
            camera_pitch_cdeg=int.from_bytes(status[6:8],"big"),acknowledged_sequence=status[8],
            fault_code=status[9],relay_mission_tx_frames=self.tx_count,
            relay_last_mission_command=self.last_payload[0] if self.last_payload else None,
            relay_last_mission_payload=self.last_payload)

    def packet(self,packet):
        self.now+=150
        self.tx_count+=1
        self.last_payload=tuple(packet[-11:-3])
        return self.exchange(packet.hex())

    def tick(self,pose,dt=50,distance=0):
        self.now+=dt;self.path+=distance
        return self.exchange(f"@ {self.now} {self.path} {round(pose.yaw_deg*1000)} {round(pose.x_m*1000)} {round(pose.y_m*1000)}")

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill();self.process.wait()
        assert self.process.returncode==0,self.process.stderr.read()


def run_delivery(side,destination,confirmed,precise=False):
    m=check.mission(side,destination)
    m.transport_load_reuse_active=False
    Planner,Log=check.load_planner()
    wire=Wire(side)
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        planner=Planner(m,root/'pose',root/'stm',root/'cmd',root/'diag',Log(root/'events'),20)
        planner.protocol_task=planner.protocol_task_cursor=7
        planner.protocol_action=planner.protocol_action_cursor=11
        kind="core_black" if destination=="material" else "injured_orange"
        audit=sm.CargoAudit(left_class=kind,left_count=1,total_count=1,class_counts=((kind,1),))
        for n in (1,2):
            frame=replace(m._audit_payload(audit),stable=True,audit_id=n).frame(n+1)
            st=wire.packet(p.command_context_frame(n+1,7,11,n+10)+frame)
        assert st.mode==22 and st.audit_ready and st.audit_valid,st
        pose=sm.PoseSnapshot(True,0,0,m.settings.safe_heading_deg,0)
        vision=sm.VisionSnapshot(frame_sequence=20,observed_monotonic_s=wire.now/1000)

        def cycle():
            nonlocal vision
            vision=replace(vision,frame_sequence=vision.frame_sequence+1,observed_monotonic_s=wire.now/1000)
            return planner._output_for_cycle(vision,pose,st,False,wire.now/1000)

        def send(out):
            planner._publish(out)
            reply=wire.packet((root/'cmd').read_bytes())
            assert not reply.fault and not reply.action_status&4,(out,reply)
            assert (reply.task_id,reply.action_id)==(planner.protocol_task,planner.protocol_action),(out,reply)
            return reply

        # Start at the established audited-load handoff. Pickup/audit publication
        # is covered separately by check_finals_rdk_pair.py.
        out=m._staging_navigation(vision,pose,replace(st,context_matches=True),wire.now/1000)
        for target in tuple(m._route_for_navigation().points):
            st=send(out)
            assert st.action_status&1 and not st.action_status&2,(out,st)
            old=pose
            pose=replace(pose,x_m=target[0],y_m=target[1])
            if precise and m.delivery_route.last:
                pose=replace(pose,x_m=pose.x_m+.02)
            st=wire.tick(pose,distance=round(((old.x_m-pose.x_m)**2+(old.y_m-pose.y_m)**2)**.5*1000))
            out=cycle()
            assert out.command.opcode==p.CMD_NAVIGATE_WAYPOINT and out.command.arg_a==0,out
            st=send(out)
            assert st.action_status&3==3 and st.distance_done,st
            out=cycle()
        vision=replace(vision,capture_audit=audit,capture_observation_valid=True)
        for _ in range(16):
            if out.command.opcode==p.CMD_ALIGN_SAFE_ZONE:break
            assert out.command.opcode==p.CMD_CARGO_AUDIT,out
            st=send(out);out=cycle()
        assert out.command.opcode==p.CMD_ALIGN_SAFE_ZONE,out
        st=send(out)
        for _ in range(20):
            if st.action_status&3==3 and st.mode==11:break
            st=wire.tick(pose)
        assert st.mode==11 and st.action_status&3==3,st
        out=cycle()
        if precise:
            assert out.command.opcode==p.CMD_NAVIGATE_WAYPOINT and m.delivery_route.precise,out
            st=send(out)
            pose=replace(pose,x_m=m.delivery_route.target[0])
            st=wire.tick(pose,distance=20)
            out=cycle();assert out.command.arg_a==0
            st=send(out);out=cycle()
            assert out.command.opcode==p.CMD_ALIGN_SAFE_ZONE,out
            st=send(out)
            for _ in range(20):
                if st.action_status&3==3 and st.mode==11:break
                st=wire.tick(pose)
            out=cycle()
        assert out.state==sm.CompetitionState.ACQUIRE_SAFE_ZONE,out
        vision=replace(vision,safe_bbox=(10,20,500,200),safe_corridor_polygon=((1,1),(2,1),(2,2)))
        for _ in range(4):
            st=send(out);out=cycle()
            assert not out.command.flags&p.CMD_VISUAL_CORRECTION_VALID,out
        assert out.command.opcode==p.CMD_ENTER_SAFE_ZONE,out
        assert (out.command.arg_a,out.command.arg_b)==(200,270)
        enter=out
        st=send(out)
        assert st.mode==10 and st.action_status==1,st
        st=wire.tick(pose,distance=199)
        assert st.mode==10 and not st.action_status&2
        st=wire.tick(pose,distance=1)
        assert st.mode==10 and not st.motors_active
        st=wire.tick(pose,dt=600)
        assert st.mode==10 and st.motors_active
        st=send(enter)
        st=wire.tick(pose,distance=269)
        assert st.mode==10 and not st.action_status&2
        st=wire.tick(pose,distance=1)
        assert st.mode==12 and not st.action_status&2,st
        for _ in range(40):
            if st.mode==15:break
            st=wire.tick(pose)
        assert st.mode==15 and st.action_status&3==3,st
        # Inject only the visual verdict; physical completion remains a real C reply.
        out=m._finish_delivery(st,wire.now/1000,
            basis="delivery_visual_confirmed" if confirmed else "delivery_visual_timeout",
            message="fixture vision result",event="")
        st=send(out)
        for _ in range(40):
            if st.mode in (16,17) and st.action_status&3==3:break
            st=wire.tick(pose)
        assert st.mode in (16,17) and st.action_status&3==3,st
        before=m.delivery_count
        out=cycle()
        assert out.command.opcode==p.CMD_RETURN_CENTER and out.command.arg_a==0,out
        assert m.delivery_count==before+int(confirmed)
        st=send(out)
        for _ in range(40):
            if st.mode==3:break
            st=wire.tick(pose)
        assert st.mode==3,st
        out=cycle()
        assert m.delivery_return_started,out
        for target in tuple(m.delivery_return_route.points):
            st=send(out)
            pose=replace(pose,x_m=target[0],y_m=target[1])
            st=wire.tick(pose)
            out=cycle();st=send(out);out=cycle()
        assert m.state==sm.CompetitionState.SEARCH_TRANSFER,(m.state,out)
        assert m.delivery_count==before+int(confirmed)
    wire.close()
    print("PASS actual wire",side,destination,"confirmed" if confirmed else "unconfirmed",
          "20mm correction" if precise else "nominal")


def run_sweep(side,destination,blocker="danger_cyan"):
    m=check.mission(side,destination)
    m.settings=replace(m.settings,bulldozer_enabled=True)
    m.pose_align_confirmed=m.safe_zone_box_ready=True
    m.state=sm.CompetitionState.SAFE_ZONE_CORRIDOR_CHECK
    sign=m.settings.side_sign
    x,y=m._target_point()
    pose=sm.PoseSnapshot(True,x,y,m.settings.safe_heading_deg,0)
    vision=sm.VisionSnapshot(frame_sequence=1,observed_monotonic_s=.1,
        safe_bbox=(10,20,500,200),safe_corridor_polygon=((1,1),(2,1),(2,2)),
        safe_corridor_obstacle_class=blocker,safe_corridor_obstacle_count=1)
    wire=Wire(side,"pose_flow")
    Planner,Log=check.load_planner()
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        planner=Planner(m,root/'pose',root/'stm',root/'cmd',root/'diag',Log(root/'events'),20)
        planner.protocol_task=planner.protocol_task_cursor=7
        planner.protocol_action=planner.protocol_action_cursor=10
        st=wire.tick(pose)
        out=m._blocked_corridor_output(vision,replace(st,context_matches=True),.2,pose=pose)
        route=m.obstacle_route
        assert route.kind=="sweep"
        targets={0:(0.,.77),4:(-.16,.87),5:(-.56,.87),6:(-.56,.91),10:(0.,.91),11:(0.,.77)}

        def send(out):
            planner._publish(out)
            reply=wire.packet((root/'cmd').read_bytes())
            assert not reply.fault and not reply.action_status&4,(route.index,out,reply)
            assert reply.action_id==planner.protocol_action,(route.index,out,reply)
            return reply

        def cycle():
            return planner._output_for_cycle(vision,pose,st,False,wire.now/1000)

        for index,step in enumerate(route.steps):
            assert route.index==index,(index,route.index,out)
            st=send(out)
            owner=st.action_id
            if index in targets:
                tx,ty=targets[index]
                pose=replace(pose,x_m=tx*sign,y_m=ty*sign)
                st=wire.tick(pose)
                out=cycle();assert out.command.arg_a==0,(index,out)
                st=send(out)
            elif step==check.RouteStep.TURN_RIGHT:
                pose=replace(pose,yaw_deg=0 if side=="red" else 180)
                st=wire.tick(pose)
            elif step==check.RouteStep.BACK_200:
                pose=replace(pose,x_m=-.16*sign,y_m=.77*sign)
            elif step==check.RouteStep.SWEEP_1000:
                wire.now+=50
                st=wire.exchange("# 990")
                if not st.action_status&2:
                    wire.now+=50;st=wire.exchange("# 1000")
                pose=replace(pose,x_m=.44*sign,y_m=.91*sign)
            for _ in range(60):
                if st.action_status&3==3:break
                st=wire.tick(pose)
            assert st.action_status&3==3 and st.action_id==owner,(index,st)
            # A repeated completed finite command cannot begin another movement.
            repeated=send(out)
            assert repeated.action_id==owner and repeated.action_status&3==3,(index,repeated)
            st=repeated
            out=cycle()
        assert out.state==sm.CompetitionState.OBSTACLE_PICKUP and st.mode==3,(out,st)
        assert route.deposit_vehicle_point is not None
        assert abs(route.deposit_vehicle_point[0])<1e-8 and abs(route.deposit_vehicle_point[1]-.77*sign)<1e-8
    wire.close()
    print("PASS actual sweep",side,blocker,"A release; retreat160; W1 only; 1000 sweep; original pickup")


def run_payload_boundaries():
    for side in ("red","blue"):
        flags=p.CMD_VALID|p.CMD_DRIVE_STRAIGHT|p.CMD_USE_FINAL_HEADING|p.CMD_DISTANCE_VALID
        flags|=p.CMD_RED_SIDE if side=="red" else 0
        heading=9000 if side=="red" else 27000
        for front,tail,expected in ((0,0,True),(0,270,True),(5000,270,True),
                                    (-1,270,False),(5001,270,False),(200,-1,False),(200,271,False)):
            wire=Wire(side,"pose_gate")
            frame=bytearray(p.mission_frame(2,p.CMD_ENTER_SAFE_ZONE,flags,200,270,heading))
            frame[6:8]=front.to_bytes(2,"big",signed=True)
            frame[8:10]=tail.to_bytes(2,"big",signed=True)
            frame[12:14]=p.crc16_modbus(frame[2:12]).to_bytes(2,"little")
            st=wire.packet(p.command_context_frame(2,7,11,0)+frame)
            assert (st.accepted_command==p.CMD_ENTER_SAFE_ZONE and st.action_id==11)==expected,st
            assert bool(st.action_status&4)!=expected,st
            wire.close()
    print("PASS 14 actual-wire distance-boundary cases")


def run_casualty_abandon(side,at_gate):
    m=check.mission(side)
    m.transport_load_reuse_active=False
    m.state=sm.CompetitionState.TRANSPORT_AUDIT if at_gate else sm.CompetitionState.POST_GRAB_AUDIT
    wire=Wire(side,"transport_flow" if at_gate else "flow")
    audit=sm.CargoAudit(left_class="injured_orange",left_count=1,total_count=1,
                        class_counts=(("injured_orange",1),))
    for n in range(1,7):
        payload=replace(m._audit_payload(audit),stable=True,audit_id=n)
        assert payload.left_class=="injured_orange" and payload.total_count==1
        st=wire.packet(p.command_context_frame(n+1,7,11,n+10)+payload.frame(n+1))
        if st.audit_ready:break
    assert st.audit_ready and not st.audit_valid and st.mode==(48 if at_gate else 23),st
    assert not m._audit_valid(audit) and m._preferred_keep_side(audit) is None
    Planner,Log=check.load_planner()
    pose=sm.PoseSnapshot(True,-.16*m.settings.side_sign if at_gate else -.4,
                         .77*m.settings.side_sign if at_gate else 0,m.settings.safe_heading_deg,0)
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        planner=Planner(m,root/'pose',root/'stm',root/'cmd',root/'diag',Log(root/'events'),20)
        planner.protocol_task=planner.protocol_task_cursor=7
        planner.protocol_action=planner.protocol_action_cursor=11
        out=m._start_capture_abandon(audit,replace(st,context_matches=True),wire.now/1000)
        assert out.command.opcode==p.CMD_RELEASE_BOTH
        planner._publish(out);st=wire.packet((root/'cmd').read_bytes())
        assert st.mode==24 and not st.action_status&4,st
        start_count=m.delivery_count
        for n in range(100):
            if st.mode==3:break
            distance=10 if not st.gripper_closed else 0
            pose=replace(pose,y_m=pose.y_m-distance*.001*m.settings.side_sign)
            st=wire.tick(pose,distance=distance)
            out=planner._output_for_cycle(sm.VisionSnapshot(frame_sequence=100+n),pose,st,False,wire.now/1000)
            assert out.command is None or out.command.opcode not in {p.CMD_ENTER_SAFE_ZONE,p.CMD_NAVIGATE_WAYPOINT}
            if out.command is not None:
                planner._publish(out);st=wire.packet((root/'cmd').read_bytes())
                assert not st.fault and not st.action_status&4,(out,st)
        assert st.mode==3 and not st.gripper_closed and wire.path>=300,st
        assert m.delivery_count==start_count and not m.transport_load_reuse_active
    wire.close()
    print("PASS actual casualty discard",side,"gate" if at_gate else "pickup",
          "true class, invalid transport, release/300mm/original exit; no delivery count")


if __name__=="__main__":
    run_payload_boundaries()
    for side in ("red","blue"):
        for confirmed in (False,True):
            run_delivery(side,"material",confirmed=confirmed)
            run_delivery(side,"material",confirmed=confirmed,precise=True)
        for blocker in ("danger_cyan","injured_orange"):
            run_sweep(side,"material",blocker)
        for at_gate in (False,True):
            run_casualty_abandon(side,at_gate)
