/* Host fixture. Keep the wire parser, Task, mechanism and reply encoder real.
 * Each scenario starts at a named handoff; motor/encoder/servo I/O is simulated. */
#define TEST_WITH_VISION_PARSER
#define main injury_fixture_main
#include "test_injury_backoff.c"
#undef main
#include <stdlib.h>
#include <string.h>
#include "Uart.h"

bool Uart_Send(const uint8_t *data, uint16_t size)
{
  if (size == 2U * VISION_FRAME_SIZE) {
    for (unsigned i = 0; i < size; ++i) printf("%02x", data[i]);
    putchar('\n');
  }
  return true;
}

static void feed(const char *hex, uint32_t now)
{
  size_t len = strcspn(hex, "\r\n");
  assert(len > 0 && len % 2 == 0);
  for (size_t i = 0; i < len; i += 2) {
    unsigned value;
    assert(sscanf(hex+i,"%2x",&value)==1);
    uint8_t byte = value;
    Vision_ParseBytes(&byte,1,now);
  }
}

int main(int argc,char **argv)
{
  assert(argc==3);
  char line[256];
  Vision_Init();
  assert(fgets(line,sizeof(line),stdin));
  feed(line,20);
  VisionData v=Vision_GetSnapshot();
  assert(v.config_ready && v.color==VISION_COLOR_RED);
  prepare();
  configured_color=v.color;
  first_delivery_done=atoi(argv[2])!=0;
  context_session_generation=v.session_generation;
  accepted_context=(TaskContext){.valid=true,.task_id=7,.action_id=10,.opcode=VISION_CMD_APPROACH_TARGET};
  if (!strcmp(argv[1],"boot")) {
    task_start_configured_round(&v,100);
    assert(state==TASK_START && start_motion_phase==START_REVERSE);
    task_process_start(&v.fused_pose,120);
    assert(start_motion_phase==START_REVERSE_SETTLE && distance_request==-APP_START_CLEARANCE_DISTANCE_M);
    return 0;
  } else if (!strcmp(argv[1],"gate")) {
    task_enter(TASK_ALIGN_SAFE_ZONE,50);
    safe_align_done=safe_align_visual_confirmed=true;
    accepted_context.opcode=VISION_CMD_ALIGN_SAFE_ZONE;
  } else if (!strcmp(argv[1],"delivery")) {
    task_enter(TASK_ALIGN_SAFE_ZONE,50);
    safe_align_done=true;
  } else if (!strcmp(argv[1],"split") || !strcmp(argv[1],"relook") || !strcmp(argv[1],"grab")) {
    task_enter(TASK_GRAB_OBSERVE,50);
    task_status.gripper_closed=false;
    task_capture_budget_begin();
    task_status.claw_visible=true;
  } else if (!strcmp(argv[1],"station")) {
    task_enter(TASK_SEARCH,50); task_status.gripper_closed=false;
  } else { assert(!strcmp(argv[1],"audit")); }
  Camera_SetAngle(APP_GRAB_VIEW_ANGLE);
  uint32_t now=100;
  while (fgets(line,sizeof(line),stdin)) {
    now+=150;
    feed(line,now);
    v=Vision_GetSnapshot();
    command_accepted=false;
    task_accept_mission(&v,now);
    if (!strcmp(argv[1],"grab") && state==TASK_CLOSE_CLAW) {
      initial_claw_ready=true;
      Task_Process(now);
      now+=2000;
      Task_Process(now);
      assert(state==TASK_POST_GRAB_AUDIT && task_status.gripper_closed);
    }
    if (!strcmp(argv[1],"delivery") && state==TASK_OPEN_FOR_RAM) {
      task_process_delivery_open(&active_mission,now);
      now+=2000;
      task_process_delivery_open(&active_mission,now);
    }
    if (!strcmp(argv[1],"station") && state==TASK_REMOTE_ACTION && command_accepted)
      task_process_bulldozer(&active_mission,now);
    task_publish_status(now);
    for (unsigned i=0;i<5;++i) Vision_Process();
  }
  return 0;
}
