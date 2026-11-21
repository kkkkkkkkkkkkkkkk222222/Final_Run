/* Production Task/mechanism; only hardware is replaced by existing mocks. */
#define main original_fixture_main
#include "test_injury_backoff.c"
#undef main
#include <stdlib.h>
#undef assert
#define assert(x) ((x) ? (void)0 : (fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x),exit(1)))

static uint32_t generation;
static uint8_t side_flags;
static uint16_t side_heading;

static void pose_gate(bool red)
{
  prepare(); generation=0;
  configured_color=red?VISION_COLOR_RED:VISION_COLOR_BLUE;
  side_flags=VISION_CMD_VALID|(red?VISION_CMD_RED_SIDE:0);
  side_heading=red?9000:27000;
  test_pose.heading_mdeg=side_heading*10;
  context_session_generation=1;
  test_vision=(VisionData){.config_ready=true,.color=configured_color,.session_generation=1};
  task_enter(TASK_ALIGN_SAFE_ZONE,0);
  audit_received=audit_valid=audit_host_stable=true;
  audit_initial_stash=audit_destination_injury=transport_stage_injury=false;
  audit_last_total_count=1; audit_last_left_class=VISION_CARGO_CORE;
  audit_last_right_class=VISION_CARGO_NONE;
  audit_last_counts=1;
  task_status.gripper_closed=true;
  safe_align_done=nav_ready=true;
  safe_align_visual_confirmed=false;
  accepted_context=(TaskContext){.valid=true,.completed=true,.task_id=7,.action_id=10,
    .opcode=VISION_CMD_ALIGN_SAFE_ZONE,.flags=side_flags|VISION_CMD_USE_FINAL_HEADING};
  active_mission=(VisionMissionCommand){0};
}

static VisionMissionCommand request(uint8_t op,uint16_t action,uint8_t flags,int a,int b,uint16_t h)
{
  return (VisionMissionCommand){.received=true,.payload_valid=true,.context_valid=true,
    .task_id=7,.action_id=action,.command=op,.flags=flags,
    .target_x_mm=a,.target_y_mm=b,.heading_cdeg=h};
}

static bool submit(VisionMissionCommand command,uint32_t now)
{
  command.generation=++generation;command.sequence=(uint8_t)generation;command.tick_ms=now;
  test_vision.mission=command;command_accepted=false;
  task_accept_mission(&test_vision,now);
  return command_accepted;
}

static VisionMissionCommand enter_request(int front,int tail)
{
  return request(VISION_CMD_ENTER_SAFE_ZONE,11,
      side_flags|VISION_CMD_DRIVE_STRAIGHT|VISION_CMD_USE_FINAL_HEADING|VISION_CMD_DISTANCE_VALID,
      front,tail,side_heading);
}

static void stroke(bool red,int front,int tail)
{
  pose_gate(red);
  VisionMissionCommand enter=enter_request(front,tail);
  assert(submit(enter,100));
  assert(state==TASK_NAVIGATE && delivery_front_mm()==(unsigned)front &&
         delivery_total_mm()==(unsigned)(front+tail));
  test_pose.path_mm=1000;
  safe_enter_follow(&active_mission,110);
  const uint32_t origin=safe_enter_start_path_mm;
  assert(submit(enter,120) && safe_enter_start_path_mm==origin);
  VisionMissionCommand changed=enter;changed.target_x_mm++;
  assert(!submit(changed,130) && delivery_front_mm()==(unsigned)front);
  changed=enter;changed.action_id=12;
  assert(!submit(changed,140));
  assert(submit(enter,150));
  if(front){
    test_pose.path_mm=1000+front-1;
    assert(safe_enter_follow(&active_mission,200)==REMOTE_ROUTE_RUNNING);
    assert(!nav_final_push_active && !delivery.final_push_lift_requested);
  }
  test_pose.path_mm=1000+front;
  RemoteRouteStatus result=safe_enter_follow(&active_mission,210);
  if(tail){
    assert(delivery.final_push_lift_requested);
    const uint32_t ready=delivery.final_push_lift_ready_ms>210?delivery.final_push_lift_ready_ms:210;
    if(delivery.final_push_lift_ready_ms>210) {
      assert(!task_status.motors_active);
      assert(safe_enter_follow(&active_mission,ready-1)==REMOTE_ROUTE_WAITING);
    }
    assert(safe_enter_follow(&active_mission,ready)==REMOTE_ROUTE_RUNNING);
    assert(nav_final_push_active);
    const uint32_t started=nav_final_push_started_ms;
    assert(submit(request(VISION_CMD_PAUSE,11,side_flags,0,0,0),ready+10));
    assert(mission_paused && safe_enter_start_path_mm==origin);
    assert(submit(enter,ready+1010));
    assert(!mission_paused && safe_enter_start_path_mm==origin && delivery_total_mm()==(unsigned)(front+tail));
    assert(safe_enter_follow(&active_mission,ready+1010)==REMOTE_ROUTE_RUNNING);
    assert(nav_final_push_started_ms>=started+1000);
    test_pose.path_mm=1000+front+tail-1;
    assert(safe_enter_follow(&active_mission,ready+1020)==REMOTE_ROUTE_RUNNING);
    test_pose.path_mm++;
    result=safe_enter_follow(&active_mission,ready+1030);
  }
  assert(result==REMOTE_ROUTE_REACHED && nav_final_push_done && !task_context_complete());
  task_process_navigation(&test_vision,3000);
  assert(state==TASK_OPEN_FOR_RAM && !task_context_complete());
  task_process_delivery_open(&active_mission,3100);
  task_process_delivery_open(&active_mission,5100);
  task_process_delivery_open(&active_mission,6000);
  assert(state==TASK_RAM_VERIFY && task_context_complete());
  assert(submit(enter,6100) && state==TASK_RAM_VERIFY);
}

static void alignment(bool red)
{
  pose_gate(red);safe_align_done=nav_ready=false;
  test_pose.heading_mdeg=side_heading*10-2000;
  task_process_safe_align(100);
  assert(!safe_align_done && task_status.motors_active);
  test_pose.heading_mdeg=side_heading*10-1000;
  task_process_safe_align(200);
  task_process_safe_align(200+APP_SAFE_ALIGN_CAMERA_SETTLE_MS+APP_NAV_TURN_SETTLE_MS);
  assert(safe_align_done && task_context_complete());
  test_pose.heading_mdeg=side_heading*10-1001;
  assert(!submit(enter_request(200,270),2000));
  assert(!safe_align_done && state==TASK_ALIGN_SAFE_ZONE);
}

static void navigation_epochs(void)
{
  pose_gate(true);task_enter(TASK_NAVIGATE,10);delivery_stage_only=true;
  distance_command_done=true;
  accepted_context=(TaskContext){.valid=true,.completed=true,.task_id=7,.action_id=10,
    .opcode=VISION_CMD_NAVIGATE_WAYPOINT,.flags=side_flags|VISION_CMD_DISTANCE_VALID|VISION_CMD_STAGE_ONLY};
  const uint8_t flags=accepted_context.flags;
  VisionMissionCommand next=request(VISION_CMD_NAVIGATE_WAYPOINT,11,flags,470,0,9000);
  assert(submit(next,100));
  assert(!accepted_context.completed && !task_context_complete() && !distance_command_done);
  assert(nav_follow(&active_mission,VISION_CMD_NAVIGATE_WAYPOINT,800,120)==REMOTE_ROUTE_WAITING);
  assert(!task_context_complete() && nav_coarse.valid);
  next.target_x_mm=0;assert(submit(next,140));
  assert(nav_follow(&active_mission,VISION_CMD_NAVIGATE_WAYPOINT,800,150)==REMOTE_ROUTE_REACHED);
  assert(task_context_complete());
  next.target_x_mm=470;
  assert(submit(next,155));
  assert(nav_follow(&active_mission,VISION_CMD_NAVIGATE_WAYPOINT,800,156)==REMOTE_ROUTE_REACHED);
  assert(task_context_complete());
  next.action_id=12;next.target_x_mm=160;next.heading_cdeg=18000;
  assert(submit(next,160));assert(!task_context_complete()&&!nav_coarse.valid);
  assert(nav_follow(&active_mission,VISION_CMD_NAVIGATE_WAYPOINT,800,170)==REMOTE_ROUTE_WAITING);
  assert(nav_follow(&active_mission,VISION_CMD_NAVIGATE_WAYPOINT,800,175)==REMOTE_ROUTE_RUNNING);
  assert(fabsf(nav_coarse.heading_deg-180.f)<.01f);
  next.action_id=11;assert(!submit(next,180));
}

static void nudge_and_sweep(bool red)
{
  pose_gate(red);
  VisionMissionCommand nudge=request(VISION_CMD_CORRIDOR_NUDGE,11,side_flags|VISION_CMD_SIDE_VALID,
                                     100,80,side_heading);
  assert(submit(nudge,100) && remote_action.type==REMOTE_ACTION_CORRIDOR_NUDGE);
  task_process_corridor_nudge(110);assert(remote_action.phase==0);
  const float lateral_counts=100.f*1.5f*APP_ENCODER_COUNTS_PER_WHEEL_REV/
      (APP_OMNI_LATERAL_API_SIGN*3.14159265359f*APP_WHEEL_DIAMETER_MM*APP_OMNI_M3_ENCODER_SIGN);
  test_wheel_encoder[2].position=remote_action.straight_start_counts[2]-(int64_t)lateral_counts;
  task_process_corridor_nudge(120);assert(remote_action.phase==1);
  distance_result=MOTOR_DISTANCE_RUNNING;
  task_process_corridor_nudge(140);assert(remote_action.phase==1&&!remote_action.done);
  distance_result=MOTOR_DISTANCE_DONE;distance_travelled_mm=80;
  task_process_corridor_nudge(160);assert(remote_action.phase==2);
  task_process_corridor_nudge(170);
  test_wheel_encoder[2].position=remote_action.straight_start_counts[2]+(int64_t)lateral_counts;
  task_process_corridor_nudge(180);assert(remote_action.phase==3);
  task_process_corridor_nudge(200);
  assert(remote_action.done&&remote_action.nudge_forward_mm==80&&task_context_complete());
  VisionMissionCommand align=request(VISION_CMD_ALIGN_SAFE_ZONE,12,side_flags|VISION_CMD_USE_FINAL_HEADING,
                                    0,0,side_heading);
  assert(submit(align,220) && state==TASK_ALIGN_SAFE_ZONE);
  safe_align_done=nav_ready=true;
  VisionMissionCommand after_nudge=enter_request(120,270);after_nudge.action_id=13;
  assert(submit(after_nudge,230)&&safe_enter_resume_mm==0&&delivery_total_mm()==390);
  pose_gate(red);
  uint16_t sweep_heading=red?0:18000;
  VisionMissionCommand to_a=request(VISION_CMD_BULLDOZER_STEP,11,
      side_flags|(VISION_BULLDOZER_LEFT_TO_SWEEP<<4),160,red?0:18000,side_heading);
  assert(submit(to_a,100));
  task_process_bulldozer(&active_mission,110);assert(!task_context_complete());
  to_a.target_x_mm=0;assert(submit(to_a,120));
  task_process_bulldozer(&active_mission,130);assert(task_context_complete());
  assert(submit(to_a,140)&&remote_action.done);
  VisionMissionCommand turn=request(VISION_CMD_BULLDOZER_STEP,12,side_flags,0,0,sweep_heading);
  assert(submit(turn,150)&&!remote_action.done);
  test_pose.heading_mdeg=sweep_heading*10;
  task_process_bulldozer(&active_mission,160);assert(remote_action.done);
  VisionMissionCommand release=request(VISION_CMD_BULLDOZER_STEP,13,
      side_flags|(VISION_BULLDOZER_RELEASE_LOAD<<4),0,0,0);
  assert(submit(release,170));
  task_process_bulldozer(&active_mission,180);task_process_bulldozer(&active_mission,2180);
  assert(remote_action.done&&!task_status.gripper_closed);
  VisionMissionCommand back=request(VISION_CMD_BULLDOZER_STEP,14,
      side_flags|(VISION_BULLDOZER_BACK_200<<4),-160,0,sweep_heading);
  assert(submit(back,2200));task_process_bulldozer(&active_mission,2220);
  assert(remote_action.done&&fabsf(distance_request+.160f)<.00001f);
}

static void legacy_and_reset(void)
{
  pose_gate(true);
  VisionMissionCommand legacy=request(VISION_CMD_ENTER_SAFE_ZONE,11,
      side_flags|VISION_CMD_DRIVE_STRAIGHT|VISION_CMD_USE_FINAL_HEADING,0,0,9000);
  assert(submit(legacy,100)&&delivery_front_mm()==400&&delivery_total_mm()==670);
  pose_gate(true);assert(submit(enter_request(200,270),100));
  assert(delivery_total_mm()==470);
  test_vision.session_generation=2;test_vision.mission=(VisionMissionCommand){0};
  task_accept_mission(&test_vision,120);
  assert(!delivery.distances_latched && !accepted_context.valid && safe_enter_resume_mm==0);
}

int main(void)
{
  for(int red=0;red<2;++red){
    stroke(red,200,270);stroke(red,70,270);stroke(red,0,240);stroke(red,0,0);
    alignment(red);nudge_and_sweep(red);
  }
  navigation_epochs();legacy_and_reset();
  puts("PASS 8 strokes; red/blue 1-degree alignment; pause/repeat/mutation/old-action handling; NAV epochs; nudge and sweep handoffs; legacy/reset");
  return 0;
}
