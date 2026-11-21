"""Focused offline checks for the pose-only delivery and paired action epochs.

Runs with Python alone. The production planner class is loaded without its
Linux camera imports; file publication and mission/protocol code remain real.
"""
import ast
import json
import math
import os
import secrets
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent / "vision")]
import protocol as p
import state_machine as sm
from delivery_route import DeliveryRoute
from obstacle_route import ObstacleRoute, RouteStep, LIVE_STEPS
from rescue_vision.mission_protocol import write_command_frame


def load_planner():
    source = ROOT / "run_competition_rescue.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    nodes += [n for n in tree.body if isinstance(n, ast.ClassDef) and
              n.name in {"CompetitionPlanner", "CameraViewBoundary", "JsonlLog"}]
    env = dict(vars(sm), **{k: v for k, v in vars(p).items() if not k.startswith("__")})
    env.update(globals())
    env["MATCH_RECORDING"] = False
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(source), "exec"), env)
    return env["CompetitionPlanner"], env["JsonlLog"]


def mission(side="red", destination="material"):
    m = sm.CompetitionMission(sm.CompetitionSettings(side=side, initial_stash_enabled=False))
    m.first_common_delivered = True
    kind = "injured_orange" if destination == "injury" else "core_black"
    m._select_batch(sm.CargoBatch((7,), (kind,), destination))
    m._latch_carried_manifest(sm.CargoAudit(left_class=kind, left_count=1, total_count=1,
                                          class_counts=((kind, 1),)))
    m.confirmed_delivery_destination = destination
    m.transport_load_reuse_active = True
    m.state = sm.CompetitionState.NAVIGATE
    return m


def status(op=p.CMD_NAVIGATE_WAYPOINT, *, done=True, matched=True, mode=10):
    return sm.StmSnapshot(mode=mode, flags=2 | (32 if done else 0), age_ms=0,
        context_valid=True, context_matches=matched, accepted_command=op,
        action_status=3 if done else 1, camera_pitch_cdeg=12000)


def test_staging_epochs_and_boundaries():
    Planner, Log = load_planner()
    for side in ("red", "blue"):
        m = mission(side)
        sign = m.settings.side_sign
        v = sm.VisionSnapshot()
        pose = sm.PoseSnapshot(True, -.4, 0, 90)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            planner = Planner(m, root/'pose', root/'stm', root/'cmd', root/'diag', Log(root/'events'), 20)
            out = m._staging_navigation(v, pose, status(matched=False), 1.)
            assert tuple(tuple(round(v,3) for v in xy) for xy in m.delivery_route.points) == ((0., .3*sign), (0., .77*sign), (-.16*sign, .77*sign))
            actions = []
            for target in m.delivery_route.points:
                planner._publish(out)
                action = planner.protocol_action
                actions.append(action)
                planner._publish(out)
                assert planner.protocol_action == action
                pose = replace(pose, x_m=target[0], y_m=target[1])
                # Even a matching DONE cannot skip the first D=0 publication.
                out = m._staging_navigation(v, pose, status(), 1.1)
                assert out.command.opcode == p.CMD_NAVIGATE_WAYPOINT and out.command.arg_a == 0
                planner._publish(out)
                assert planner.protocol_action == action
                old_index = m.delivery_route.index
                out = m._staging_navigation(v, pose, status(matched=False), 1.2)
                assert m.delivery_route.index == old_index
                out = m._staging_navigation(v, pose, status(done=False), 1.3)
                assert m.delivery_route.index == old_index
                out = m._staging_navigation(v, pose, status(), 1.4)
            assert len(set(actions)) == 3 and out.command.opcode == p.CMD_ALIGN_SAFE_ZONE
            planner._publish(out)
            aligned_action = planner.protocol_action
            m._begin_safe_zone_pose_align(status(), 2.)
            planner._publish(replace(out, command=m._safe_zone_pose_align_command()))
            assert planner.protocol_action != aligned_action
        # Correct x only when outside the separately approved 10 mm window.
        pose = replace(pose, x_m=pose.x_m+.011, yaw_deg=m.settings.safe_heading_deg)
        out = m._ensure_delivery_staging(pose, status(), 3.)
        assert out.command.opcode == p.CMD_NAVIGATE_WAYPOINT and out.command.arg_a > 0
        assert m.delivery_route.precise
        assert m._pose_heading_ready(replace(pose, yaw_deg=m.settings.safe_heading_deg+1))
        assert not m._pose_heading_ready(replace(pose, yaw_deg=m.settings.safe_heading_deg+1.01))


def test_pose_box_corridor_enter_and_reobserve():
    for side in ("red", "blue"):
        m = mission(side)
        x, y = m._target_point()
        pose = sm.PoseSnapshot(True, x, y, m.settings.safe_heading_deg)
        st = status(p.CMD_ALIGN_SAFE_ZONE, mode=11)
        v = sm.VisionSnapshot(frame_sequence=1, observed_monotonic_s=1., safe_bbox=(10, 20, 500, 200),
                              safe_corridor_polygon=((1,1),(2,1),(2,2)))
        m._begin_safe_zone_pose_align(st, 1.)
        out = m.step(v, pose, replace(st, action_status=1), 1.01)
        assert out.state == sm.CompetitionState.ALIGN_SAFE_ZONE_BY_POSE
        out = m.step(v, pose, replace(st, context_matches=False), 1.02)
        assert out.state == sm.CompetitionState.ALIGN_SAFE_ZONE_BY_POSE
        out = m.step(v, pose, st, 1.03)
        assert out.state == sm.CompetitionState.ACQUIRE_SAFE_ZONE, out
        for frame in range(2,5):
            v = replace(v, frame_sequence=frame, observed_monotonic_s=1.+frame/10)
            out = m.step(v, pose, st, 1.+frame/10)
            assert not out.command.flags & p.CMD_VISUAL_CORRECTION_VALID
        assert out.state == sm.CompetitionState.SAFE_ZONE_CORRIDOR_CHECK
        out = m.step(v, pose, st, 1.5)
        assert out.reason == "SAFE_CORRIDOR_UNAVAILABLE"
        out = m.step(replace(v,frame_sequence=5), pose, st, 1.6)
        assert out.command.opcode == p.CMD_ENTER_SAFE_ZONE, out
        assert (out.command.arg_a,out.command.arg_b) == (200,270)
        out.command.to_frame(7)
        captured = out.command
        m.enter_command_published = True
        out = m.step(replace(v,frame_sequence=6,safe_corridor_obstacle_class="danger_cyan"),
                     replace(pose,y_m=pose.y_m+.1), st, 1.7)
        assert out.command == captured  # Later pose/image cannot change an in-flight stroke.
        m._begin_safe_zone_pose_align(st, 2.)
        m.step(v, pose, st, 2.1)
        m.safe_zone_box_ready = m.pose_align_confirmed = True
        m.state = sm.CompetitionState.SAFE_ZONE_CORRIDOR_CHECK
        out = m.step(replace(v,safe_bbox=None),pose,st,2.2)
        assert out.state == sm.CompetitionState.ACQUIRE_SAFE_ZONE
        assert out.command.arg_b == 11500 and not out.command.flags & p.CMD_VISUAL_CORRECTION_VALID
        # Actual post-nudge position sets remaining distance once, without double credit.
        m._prepare_pose_enter(replace(pose, y_m=.90*m.settings.side_sign))
        assert (m.enter_pose_command.arg_a,m.enter_pose_command.arg_b) == (70,270)
        m._prepare_pose_enter(replace(pose, y_m=1.00*m.settings.side_sign))
        assert (m.enter_pose_command.arg_a,m.enter_pose_command.arg_b) == (0,240)


def test_sweep_mirrors_and_live_completion():
    for side, sign in (("red",1),("blue",-1)):
        for x in (-.16,.16):
            route = ObstacleRoute(side,(1,),("core_black",),"material",
                (x*sign,.77*sign),(x*sign,.77*sign),("danger_cyan",),"sweep")
            assert RouteStep.FORWARD_PARK not in route.steps
            assert route.sweep_point == (-.56*sign,.91*sign)
            # Tolerance offsets on the other axis never turn an axial leg diagonal.
            assert route.payload(x*sign,.74*sign,pose_valid=True)[1] in {0,18000,-18000}
            route.index=4;route.arrival_latched=False
            assert abs(route.payload(-.11*sign,.77*sign,pose_valid=True)[1])==9000
            route.index=5;route.arrival_latched=False
            assert abs(route.payload(-.16*sign,.84*sign,pose_valid=True)[1]) in {0,18000}
            positions = {0:(0.,.77),4:(-.16,.87),5:(-.56,.87),6:(-.56,.91),10:(0.,.91),11:(0.,.77)}
            for index, step in enumerate(route.steps):
                route.index=index; route.arrival_latched=False
                target = positions.get(index,(0.,.77))
                payload = route.payload(target[0]*sign,target[1]*sign,pose_valid=True)
                sm.CommandRequest(p.CMD_BULLDOZER_STEP,1|(8 if side=="red" else 0)|(int(step)<<4),*payload).to_frame(index)
                if step in LIVE_STEPS:
                    assert payload[0] == 0
                if step == RouteStep.BACK_200:
                    assert payload[0] == -160
            m = mission(side)
            m.obstacle_route = ObstacleRoute(side,(1,),("core_black",),"material",
                (x*sign,.77*sign),(x*sign,.77*sign),("danger_cyan",),"sweep")
            m.state = sm.CompetitionState.OBSTACLE_ROUTE
            st=status(p.CMD_BULLDOZER_STEP)
            at=sm.PoseSnapshot(True,0,.77*sign,90 if sign==1 else 270)
            out=m._obstacle_route_output(sm.VisionSnapshot(),at,st,1.)
            assert m.obstacle_route.index==0 and out.command.arg_a==0
            m._obstacle_route_output(sm.VisionSnapshot(),at,replace(st,context_matches=False),1.1)
            assert m.obstacle_route.index==0
            m._obstacle_route_output(sm.VisionSnapshot(),at,st,1.2)
            assert m.obstacle_route.index==1


def test_return_waypoints_and_original_recovery():
    for recover in (False,True):
        for side in ("red","blue"):
            m=mission(side);sign=m.settings.side_sign
            pose=sm.PoseSnapshot(True,-.16*sign,.77*sign,m.settings.safe_heading_deg)
            m._prepare_pose_enter(pose)
            if recover:
                m.obstacle_route=ObstacleRoute(side,(1,),("core_black",),"material",
                    (.16*sign,.77*sign),(.16*sign,.77*sign),("core_black",),"pickup",
                    recover_after_delivery=True)
            m._clear_selected_batch()
            m._begin_return(status(),1.,station=1,via_delivery=True)
            assert tuple(tuple(round(v,3) for v in xy) for xy in m.delivery_return_route.points[:2])==((-.16*sign,.77*sign),(0.,.77*sign))
            assert len(m.delivery_return_route.points)==(2 if recover else 3)
            m.delivery_return_started=True
            m.delivery_return_heading=round(pose.yaw_deg*100)
            points=m.delivery_return_route.points
            for xy in points:
                pose=replace(pose,x_m=xy[0],y_m=xy[1])
                out=m._delivery_return_output(sm.VisionSnapshot(),pose,status(p.CMD_BULLDOZER_STEP),1.2)
                assert out.command.arg_a==0
                out=m._delivery_return_output(sm.VisionSnapshot(),pose,status(p.CMD_BULLDOZER_STEP),1.3)
            assert m.state==(sm.CompetitionState.OBSTACLE_ROUTE if recover else sm.CompetitionState.SEARCH_TRANSFER)


def test_material_selection_includes_clipped_zone_entry():
    for side in ("red","blue"):
        m=mission(side)
        orange=sm.TrackedCargo(1,"injured_orange",.9,(300,300,40,40),hits=3,inside_safe_zone=True)
        vision=sm.VisionSnapshot(cargo=(orange,),frame_sequence=1,range_pitch_cdeg=12000,
                                 clipped_zone_candidates=((1,"fixture_zone"),))
        assert m._choose_delivery_target(vision,(orange,)) is None
        assert m._choose_search_target(vision) is None
        assert m._start_zone_observation(vision,sm.StmSnapshot(mode=3,flags=0,
            age_ms=0,camera_pitch_cdeg=12000),1.) is None
        # Identity remains a casualty, but it never grants formal transport.
        m.confirmed_delivery_destination="injury"
        assert not m._audit_valid(sm.CargoAudit(left_class="injured_orange",left_count=1,
                                           total_count=1,class_counts=(("injured_orange",1),)))


def test_casualty_audit_and_material_retention():
    for side in ("red","blue"):
        m=mission(side)
        orange=sm.CargoAudit(left_class="injured_orange",left_count=1,total_count=1,
                             class_counts=(("injured_orange",1),))
        assert not m._audit_valid(orange)
        assert m._preferred_keep_side(orange) is None
        assert m._choose_release_side(orange)=="both"
        assert m._audit_payload(orange).left_class=="injured_orange"
        for keep in ("left","right"):
            a=sm.CargoAudit(left_class="core_black" if keep=="left" else "injured_orange",
                right_class="core_black" if keep=="right" else "injured_orange",
                left_count=1,right_count=1,total_count=2,injury_mixed=True,
                class_counts=(("core_black",1),("injured_orange",1)))
            assert not m._audit_valid(a) and m._preferred_keep_side(a)==keep
            assert m._retained_class(a,keep)=="core_black"
            assert not m._audit_payload(a).destination_injury
        m.selected_batch=replace(m.selected_batch,initial_stash=True,destination="stash")
        assert m._audit_valid(orange)  # Opening relocation is not casualty delivery.


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("PASS", name)
