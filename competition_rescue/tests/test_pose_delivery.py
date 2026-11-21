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


def test_opening_casualty_relook_keeps_real_audit_and_task():
    Planner, Log = load_planner()
    for side in ("red", "blue"):
        m = sm.CompetitionMission(sm.CompetitionSettings(side=side))
        pose = sm.PoseSnapshot(True, 0, 0, 135, 0)
        injury = sm.TrackedCargo(7, "injured_orange", .9, (600, 500, 40, 40),
                                None, 3, 0, True, False)
        audit = sm.CargoAudit(left_class="injured_orange", left_count=1, total_count=1)
        v = sm.VisionSnapshot(frame_sequence=10, cargo=(injury,), capture_cargo=(injury,),
                              capture_audit=audit)
        assert m._pile_batch(v) is None
        mixed = replace(v, cargo=(injury, replace(injury, track_id=8, class_name="core_black")))
        assert set(m._pile_batch(mixed).classes) == {"injured_orange", "core_black"}
        search = sm.StmSnapshot(mode=3, camera_pitch_cdeg=10500, age_ms=0)
        m.step(v, pose, search, 1.)
        out = m.step(v, pose, search, 1.02)
        assert out.state == sm.CompetitionState.INITIAL_CLAW_CHECK
        ready = sm.StmSnapshot(mode=21, flags=1, camera_pitch_cdeg=14000, age_ms=0)
        m.step(v, pose, ready, 1.7)
        for frame, now in ((11, 1.8), (12, 1.91)):
            v = replace(v, frame_sequence=frame, observed_monotonic_s=now)
            out = m.step(v, pose, ready, now)
        assert out.state == sm.CompetitionState.AUDIT_CONFIRM
        assert out.command.audit.stable and out.command.audit.total_count == 1
        assert out.command.audit.left_class == "injured_orange"
        assert out.command.audit.initial_stash and out.command.audit_vision_frame == 12
        assert m.pending_audit_release_context == "initial_injury_relook"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            planner = Planner(m, root/'pose', root/'stm', root/'cmd', root/'diag', Log(root/'events'), 20)
            planner.protocol_vision = v
            planner._publish(out)
            task, action = planner.protocol_task, planner.protocol_action
            reply = replace(ready, flags=81, acknowledged_sequence=1,
                relay_mission_tx_frames=1, relay_last_mission_command=p.CMD_CARGO_AUDIT,
                relay_last_mission_payload=tuple(out.command.to_frame(0)[4:12]),
                context_valid=True, context_matches=True,
                accepted_command=p.CMD_CARGO_AUDIT, action_status=1)
            for bad in (replace(reply, context_matches=False), replace(reply, flags=17),
                        replace(reply, accepted_command=p.CMD_HOLD)):
                wait = m.step(v, pose, bad, 1.92)
                assert wait.command.opcode == p.CMD_CARGO_AUDIT
            out = m.step(v, pose, reply, 1.93)
            assert out.command.opcode == p.CMD_APPROACH_TARGET
            assert (out.command.arg_a, out.command.arg_b, out.command.aux) == (0, 12000, 5)
            assert out.command.source_vision_frame == 12
            planner._publish(out)
            assert planner.protocol_task == task and planner.protocol_action != action
            assert planner.protocol_vision_frame == 12
            relook_action = planner.protocol_action
            planner._publish(out)
            assert planner.protocol_action == relook_action
        out = m.step(v, pose, replace(reply, mode=3, camera_pitch_cdeg=12000,
                                     accepted_command=p.CMD_APPROACH_TARGET), 1.94)
        assert out.state == sm.CompetitionState.INITIAL_OBSERVE
        out = m.step(replace(v, frame_sequence=13, observed_monotonic_s=2.), pose, search, 2.)
        assert out.command.opcode == p.CMD_HOLD  # Do not chase the same casualty.


def test_opening_mixed_batch_never_tracks_injury_when_material_disappears():
    for side in ("red", "blue"):
        m = sm.CompetitionMission(sm.CompetitionSettings(side=side))
        m.state = sm.CompetitionState.INITIAL_OBSERVE
        m.initial_claw_check_started = True
        green = sm.TrackedCargo(8, "green_supply", .9, (400, 300, 80, 80),
                                None, 3, 0, True, False)
        injury = replace(green, track_id=9, class_name="injured_orange", bbox=(650, 540, 80, 80))
        v = sm.VisionSnapshot(frame_sequence=20, cargo=(green, injury), observed_monotonic_s=1.)
        st = sm.StmSnapshot(mode=3, camera_pitch_cdeg=12000, age_ms=0)
        pose = sm.PoseSnapshot(True, 0, 0, 135, 0)
        out = m.step(v, pose, st, 1.)
        assert out.state == sm.CompetitionState.INITIAL_APPROACH
        assert m.locked_target_track_id == 8
        assert set(m.selected_batch.classes) == {"green_supply", "injured_orange"}
        # Even within the ordinary brief-loss replay window, do not chase.
        m.last_approach_command = out.command
        injury_only = replace(v, frame_sequence=21, cargo=(injury,), observed_monotonic_s=1.01)
        out = m.step(injury_only, pose, st, 1.01)
        assert out.command.opcode == p.CMD_HOLD
        assert m._target_for_batch(injury_only) is None
        # Previously locked injury ID and a replacement ID both stay excluded.
        m.locked_target_track_id = injury.track_id
        m.target_last_class = "injured_orange"
        assert m._target_for_batch(injury_only) is None
        assert m._target_for_batch(replace(injury_only, cargo=(replace(injury, track_id=99),))) is None


def test_original_pickup_requires_new_120_view_and_rechecks_misses():
    for side in ("red", "blue"):
        for role in ("original", "obstacle"):
            m = mission(side)
            route = ObstacleRoute(side, (7,), ("core_black",), "material",
                (0, .77), (0, .77), ("core_black",), "pickup")
            route.pickup_role = role
            m.obstacle_route = route
            m.state = sm.CompetitionState.OBSTACLE_PICKUP
            st = status(p.CMD_BULLDOZER_STEP, mode=25)
            target = sm.TrackedCargo(7, "core_black", .9, (600, 500, 40, 40),
                                    None, 3, 0, True, False)
            v = sm.VisionSnapshot(frame_sequence=10, cargo=(target,), range_pitch_cdeg=14000,
                                  observed_monotonic_s=1.)
            out = m._obstacle_pickup_output(v, replace(st, camera_pitch_cdeg=14000), 1.)
            assert out.state == sm.CompetitionState.OBSTACLE_PICKUP
            out = m._obstacle_pickup_output(v, st, 1.1)
            assert out.command.opcode == p.CMD_HOLD
            out = m._obstacle_pickup_output(replace(v, frame_sequence=11), st, 1.2)
            assert out.command.opcode == p.CMD_HOLD  # Old viewpoint despite higher ID.
            empty = replace(v, frame_sequence=12, cargo=(), range_pitch_cdeg=12000,
                            observed_monotonic_s=1.3)
            for _ in range(5):
                out = m._obstacle_pickup_output(empty, st, 1.3)
                assert m.obstacle_route is route
            assert route.pickup_missing_frames == 1
            for stamp in (None, -1.):
                for cargo in ((), (target,)):
                    out = m._obstacle_pickup_output(replace(empty, frame_sequence=13,
                        cargo=cargo, observed_monotonic_s=stamp), st, 1.4)
                    assert out.command.opcode == p.CMD_HOLD
                    assert route.pickup_missing_frames == 1 and route.pickup_frame_floor == 12
            out = m._obstacle_pickup_output(replace(empty, frame_sequence=13), st, 1.4)
            assert route.pickup_missing_frames == 2
            out = m._obstacle_pickup_output(replace(empty, frame_sequence=14, cargo=(target,)), st, 1.5)
            assert out.state == sm.CompetitionState.APPROACH
            assert out.command.opcode == p.CMD_APPROACH_TARGET
            assert m.recovering_original_load == (role == "original")
            # A separate complete empty observation exits on its third distinct new image.
            m.obstacle_route = route
            route.begin_original_recovery()
            m.state = sm.CompetitionState.OBSTACLE_PICKUP
            empty = replace(empty, observed_monotonic_s=2.)
            m._obstacle_pickup_output(replace(empty, frame_sequence=20), st, 2.)
            for frame in (21, 22, 23):
                out = m._obstacle_pickup_output(replace(empty, frame_sequence=frame), st, 2.1)
            assert out.state == sm.CompetitionState.SEARCH and m.obstacle_route is None


def test_pickup_planner_blocks_source_before_camera_boundary():
    Planner, Log = load_planner()
    m = mission()
    m.state = sm.CompetitionState.OBSTACLE_PICKUP
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        planner = Planner(m, root/'pose', root/'stm', root/'cmd', root/'diag', Log(root/'events'), 20)
        old = replace(status(p.CMD_BULLDOZER_STEP, mode=25), camera_pitch_cdeg=14000,
                      received_monotonic_ns=1_000_000_000)
        planner.view_boundary.observe(old)
        ready = replace(old, camera_pitch_cdeg=12000, received_monotonic_ns=2_000_000_000)
        # Inference may finish late and carry a new sequence but an old source image.
        v = sm.VisionSnapshot(frame_sequence=100, range_pitch_cdeg=12000, observed_monotonic_s=1.9)
        out = planner._output_for_cycle(v, sm.PoseSnapshot(True, 0, .77, 90), ready, False, 2.1)
        assert out.suppress_command_tx and out.reason == "camera_view_transition"


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("PASS", name)
