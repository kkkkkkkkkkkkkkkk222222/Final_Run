#ifndef FINAL1_ROUTE_H
#define FINAL1_ROUTE_H
#include <stdbool.h>
#include <stdint.h>

typedef struct {
  float x, y;
} FieldPoint;
typedef struct {
  FieldPoint points[4];
  unsigned count, index;
  float yaw;
  bool initialized, no_clear_path, turn_at_end, turn_stopped;
} Final1Route;

typedef struct {
  bool tracking, active, used, blocked;
  FieldPoint origin, goal;
  float direction;
  uint32_t started, last;
} Final1Relief;

void Final1_PlanStage(Final1Route *route, FieldPoint start, float yaw, int side,
                      bool injury);
bool Final1_CanTurn(FieldPoint pos);
void Final1_PlanReturn(Final1Route *route, FieldPoint start, float yaw);
bool Final1_NextLeg(Final1Route *route, FieldPoint pos, float *heading,
                    float *remaining);
float Final1_ClearTravel(FieldPoint pos, float dx, float dy, float yaw);
void Final1_Interrupt(Final1Relief *relief);
/* Returns true when relief owns output. A zero speed explicitly requests a
 * stop. */
bool Final1_ResolveStall(Final1Relief *relief, FieldPoint pos, float yaw,
                         int side, bool injury, bool visual,
                         float requested_heading, uint32_t now,
                         float *drive_heading, float *speed);
#endif
