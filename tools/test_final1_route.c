/* Drive the production route entry points with H/D from the frozen Python
 * host. Each input row is one control tick, each reply is body velocity/DONE.
 */
#define TEST_FINAL1_TURN
#define main original_fixture_main
#include "test_injury_backoff.c"
#undef main
#include <stdlib.h>

static void relief_tests(void) {
  for (int side = -1; side <= 1; side += 2) {
    for (int injury = 0; injury <= 1; ++injury) {
      for (int edge = 0; edge <= 2; ++edge) {
        FieldPoint p = {(injury ? 118 : -118) * side, (edge == 2   ? 584
                                                       : edge == 1 ? 568
                                                                   : 525) *
                                                          side};
        Final1Relief r = {0};
        float h = 0, v = 400, yaw = side > 0 ? 90 : 270;
        for (unsigned t = 0; t < 400; t += 20)
          assert(!Final1_ResolveStall(&r, p, yaw, side, injury, true, 0, t, &h,
                                      &v));
        assert(Final1_ResolveStall(&r, p, yaw, side, injury, true, 0, 400, &h,
                                   &v));
        assert(r.used);
        if (edge == 2) {
          assert(v == 0 && !r.active);
          continue;
        }
        float expected = edge == 1 ? 12 : 50;
        assert(fabsf(fabsf(r.goal.x - p.x) - expected) < 0.1f);
        assert(fabsf((r.goal.y - p.y) * side - expected) < 0.1f);
        assert(fabsf(r.goal.x) < fabsf(p.x));
        for (unsigned t = 420; t < 2000; t += 20)
          assert(Final1_ResolveStall(&r, p, yaw, side, injury, true, 0, t, &h,
                                     &v));
        assert(r.blocked && v == 0);
        assert(!Final1_ResolveStall(&r, p, yaw, side, injury, true, 180, 2000,
                                    &h, &v));
        assert(r.used && !r.active);
      }
    }
  }
  Final1Relief moved = {0};
  FieldPoint start = {-118, 525};
  float drive = 0, speed = 400;
  for (unsigned t = 0; t <= 400; t += 20)
    Final1_ResolveStall(&moved, start, 90, 1, false, true, 180, t, &drive,
                        &speed);
  assert(moved.active);
  assert(Final1_ResolveStall(&moved, moved.goal, 90, 1, false, true, 180, 420,
                             &drive, &speed));
  assert(!moved.active && moved.used && speed == 0);
  assert(!Final1_ResolveStall(&moved, moved.goal, 90, 1, false, true, 180, 440,
                              &drive, &speed));
  Final1Relief rolling = {0};
  for (unsigned i = 0; i < 60; ++i) {
    FieldPoint p = {100 + (float)i, 200};
    assert(!Final1_ResolveStall(&rolling, p, 90, 1, false, false, 0, i * 20,
                                &drive, &speed));
  }
  assert(!rolling.used);
  prepare();
  task_status.gripper_closed = true;
  configured_color = VISION_COLOR_RED;
  task_enter(TASK_ALIGN_SAFE_ZONE, 0);
  nav_ready = safe_align_lateral_active = safe_align_visual_confirmed = true;
  safe_align_pixel_error_px = -90;
  test_pose.x_mm = -118;
  test_pose.y_mm = 525;
  for (unsigned t = 0; t <= 400; t += 20)
    task_process_safe_align(t);
  assert(final_relief.active && reverse_output > 0 && lateral_output < 0);
  task_pause_runtime(410);
  assert(!final_relief.active && final_relief.used && reverse_output == 0);
  /* Changing from visual alignment to an axial repair retains host routing. */
  task_enter(TASK_NAVIGATE, 420);
  assert(staging_repair);

  /* Short live H/D at entry: preserve the axis released by the host. */
  final1_reset();
  test_pose = (LocationPose){
      .valid = true, .heading_mdeg = 90000, .x_mm = -75, .y_mm = 455};
  VisionMissionCommand command = {.command = VISION_CMD_NAVIGATE_WAYPOINT,
                                  .target_x_mm = 85,
                                  .heading_cdeg = 9000,
                                  .flags = VISION_CMD_STAGE_ONLY |
                                           VISION_CMD_DISTANCE_VALID |
                                           VISION_CMD_RED_SIDE};
  nav_follow(&command, command.command, 800, 500);
  assert(fabsf(reverse_output - 400) < 0.01f && fabsf(lateral_output) < 0.01f);
  assert(!distance_command_done);
  command.target_x_mm = 0;
  nav_follow(&command, command.command, 800, 520);
  assert(distance_command_done && reverse_output == 0);
  final1_reset();
  VisionMissionCommand station = {.command = VISION_CMD_BULLDOZER_STEP,
                                  .task_id = 4,
                                  .action_id = 6,
                                  .flags =
                                      (VISION_BULLDOZER_EMPTY_BODY_MOVE << 4) |
                                      VISION_CMD_RED_SIDE | VISION_CMD_VALID,
                                  .target_x_mm = 800,
                                  .heading_cdeg = 9000};
  task_enter(TASK_SEARCH, 550);
  task_status.gripper_closed = false;
  assert(task_accept_bulldozer(&station, 560) && !station_return);
}

int main(int argc, char **argv) {
  if (argc == 1) {
    relief_tests();
    puts("one-shot, clipped, mirrored, timeout, pause and repair passed");
    return 0;
  }
  assert(argc == 4);
  bool returning = atoi(argv[1]) != 0, injury = atoi(argv[3]) != 0;
  prepare();
  configured_color = atoi(argv[2]) > 0 ? VISION_COLOR_RED : VISION_COLOR_BLUE;
  if (returning) {
    task_status.gripper_closed = false;
    task_enter(TASK_EXIT_SAFE_ZONE, 0);
    task_enter(TASK_FACE_FIELD_CENTER, 20);
    task_enter(TASK_SEARCH, 40);
  } else {
    task_enter(TASK_WAIT_NAVIGATION, 0);
    task_enter(TASK_NAVIGATE, 20);
    task_status.gripper_closed = true;
    audit_destination_injury = injury;
    delivery_stage_only = true;
  }
  unsigned tick = 0;
  int x, y, yaw, d, h, u, flags;
  while (scanf("%d %d %d %d %d %d %d", &x, &y, &yaw, &d, &h, &u, &flags) == 7) {
    test_pose = (LocationPose){
        .x_mm = x, .y_mm = y, .heading_mdeg = yaw, .valid = true};
    VisionMissionCommand cmd = {.command = returning
                                               ? VISION_CMD_BULLDOZER_STEP
                                               : VISION_CMD_NAVIGATE_WAYPOINT,
                                .flags = flags,
                                .task_id = 7,
                                .action_id = 11,
                                .target_x_mm = d,
                                .target_y_mm = returning ? h : 0,
                                .heading_cdeg = u};
    tick += 20;
    if (returning) {
      if (tick == 20) {
        assert(task_accept_bulldozer(&cmd, tick));
        assert(station_return);
      }
      task_process_bulldozer(&cmd, tick);
    } else {
      assert(nav_follow(&cmd, cmd.command, 800, tick) !=
             REMOTE_ROUTE_COMMAND_INVALID);
    }
    printf("%.3f %.3f %.3f %d\n", reverse_output, lateral_output, yaw_output,
           returning ? remote_action.done : distance_command_done);
    fflush(stdout);
  }
}
