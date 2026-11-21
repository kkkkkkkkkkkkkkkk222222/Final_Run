"""Replay the frozen RDK distance/heading generator against the native Task fixture.
Usage: python -B tools/check_final1_route.py HOST FIXTURE [output_traces.json]
"""
from pathlib import Path
import json
import math
import subprocess
import sys

host, fixture = (Path(arg).resolve() for arg in sys.argv[1:3])
assert subprocess.check_output(["git","-C",str(host),"rev-parse","HEAD"],text=True).strip() == "28deaa6861c0208adf4b00c125d213c687bd2a95"
sys.path[:0] = [str(host/"competition_rescue"),str(host/"vision")]
import state_machine as sm
from search_transfer import SearchTransferRoute

starts = [(300,100),(-720,260),(0,340),(-650,790),(390,915)]
results = []
subprocess.run([fixture],check=True)
def replay(p,side,injury,station,yaw):
    m=sm.CompetitionMission(sm.CompetitionSettings(side="red" if side==1 else "blue"))
    x,y=p
    target = ((station*0.4,0) if station else
              (m.settings.injury_target_x_m if injury else m.settings.material_target_x_m,
               m.settings.safe_staging_y_m))
    route = SearchTransferRoute(1,3,target,yaw)
    trace = [(x,y)]
    initial_yaw=yaw
    angles=[yaw]
    with subprocess.Popen([fixture,str(int(bool(station))),str(side),str(int(injury))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True) as proc:
        for tick in range(800):
            pose=sm.PoseSnapshot(True,x/1000,y/1000,yaw)
            if station:
                d,h,u=route.payload(pose.x_m,pose.y_m)
                flags=m._side_flags() | int(sm.RouteStep.EMPTY_BODY_MOVE)<<4
            else:
                cmd=m._navigation_command(pose,target,staging_only=True)
                d,h,u,flags=cmd.arg_a,cmd.arg_b,cmd.aux,cmd.flags
                if m._at_target(pose,target,staging_only=True): d=0
            proc.stdin.write(f"{round(x)} {round(y)} {round(yaw*1000)} {d} {h} {u} {flags}\n")
            proc.stdin.flush()
            forward,left,rotation,done=map(float,proc.stdout.readline().split())
            assert bool(done)==(d==0)
            if done: break
            a=math.radians(yaw)
            dx=.02*(forward*math.cos(a)-left*math.sin(a))
            dy=.02*(forward*math.sin(a)+left*math.cos(a))
            assert abs(dx)<.002 or abs(dy)<.002,(dx,dy)
            if rotation:
                assert dx == dy == 0
            yaw=(yaw+.02*rotation)%360
            angles.append(round(yaw,3))
            x+=dx; y+=dy
            trace.append((round(x,2),round(y,2)))
        else: raise AssertionError((p,side,injury,station,trace[-4:]))
        proc.stdin.close()
    assert proc.returncode==0
    return dict(side=side,injury=injury,station=station,yaw=initial_yaw,angles=angles,trace=trace)

for side in (1,-1):
    for injury in (False,True):
        mirror=side*(-1 if injury else 1)
        for x,y in starts:
            results.append(replay((x*mirror,y*side),side,injury,0,90 if side==1 else 270))
        for station in (-1,1):
            results.append(replay((-150*mirror,910*side),side,injury,station,90 if side==1 else 270))

nominal_count = len(results)
for yaw in (0,45,135,180,225,270,315):
    for start in starts:
        results.append(replay(start,1,False,0,yaw))


if len(sys.argv)>3:
    Path(sys.argv[3]).write_text(json.dumps(results),encoding="utf-8")
print(f"{nominal_count} nominal and {len(results)-nominal_count} additional yaw cases reached host D=0.")
