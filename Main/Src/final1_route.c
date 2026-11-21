#include "final1_route.h"
#include <math.h>

#define DEG_RAD 0.01745329252f
#define RELIEF_STEP_MM 50.0f
#define LEG_TOLERANCE_MM 7.0f

/* A rounded-up convex envelope of the closed claws, blade and wheels at
 * yellow-block height. Coordinates are forward and left in millimetres.
 * A rectangular vehicle envelope hides reachable approaches at diagonal yaw. */
static const FieldPoint low_hull[] = {
    {-136, -35}, {38, -132}, {46, -132}, {192, -78}, {207, -63},
    {220, -42},  {226, -22}, {226, 22},  {220, 42},  {207, 63},
    {192, 78},   {46, 132},  {38, 132},  {-136, 35}};
enum { HULL_SIZE = sizeof(low_hull) / sizeof(low_hull[0]) };

float Final1_ClearTravel(FieldPoint p, float dx, float dy, float yaw) {
  float c = cosf(yaw * DEG_RAD), s = sinf(yaw * DEG_RAD);
  FieldPoint hull[HULL_SIZE];
  for (unsigned k = 0; k < HULL_SIZE; ++k) {
    hull[k] = (FieldPoint){low_hull[k].x * c - low_hull[k].y * s,
                           low_hull[k].y * c + low_hull[k].x * s};
  }
  /* Project once per axis for all four blocks. Travel is the intersection
   * of time intervals where the polygons overlap on every separating axis. */
  float enter[4] = {0}, leave[4] = {1, 1, 1, 1};
  float penetration[4] = {INFINITY, INFINITY, INFINITY, INFINITY};
  bool escaping[4] = {false};
  for (unsigned k = 0; k < HULL_SIZE + 2; ++k) {
    float nx = 1, ny = 0;
    if (k == 1) {
      nx = 0;
      ny = 1;
    }
    if (k >= 2) {
      FieldPoint a = hull[k - 2], b = hull[(k - 1) % HULL_SIZE];
      nx = b.y - a.y;
      ny = a.x - b.x;
      float length = hypotf(nx, ny);
      nx /= length;
      ny /= length;
    }
    float lo = INFINITY, hi = -INFINITY;
    for (unsigned v = 0; v < HULL_SIZE; ++v) {
      float proj = nx * hull[v].x + ny * hull[v].y;
      lo = fminf(lo, proj);
      hi = fmaxf(hi, proj);
    }
    float radius = 75 * fabsf(nx) + 50 * fabsf(ny) + 5;
    float speed = dx * nx + dy * ny;
    for (unsigned i = 0; i < 4; ++i) {
      if (leave[i] < enter[i])
        continue;
      float x = (i & 1) ? 325 : -325, y = (i & 2) ? 610 : -610;
      float centre = (x - p.x) * nx + (y - p.y) * ny;
      float lower = centre - radius - hi, upper = centre + radius - lo;
      float depth = fminf(-lower, upper);
      if (depth < penetration[i]) {
        penetration[i] = depth;
        escaping[i] = (-lower < upper) ? speed < 0 : speed > 0;
      }
      if (fabsf(speed) < 0.0001f) {
        if (depth < 0)
          leave[i] = -1;
      } else {
        float a = lower / speed, b = upper / speed;
        enter[i] = fmaxf(enter[i], fminf(a, b));
        leave[i] = fminf(leave[i], fmaxf(a, b));
      }
    }
  }
  float reach = 1;
  for (unsigned i = 0; i < 4; ++i) {
    if (leave[i] >= enter[i] && !(penetration[i] >= 0 && escaping[i]))
      reach = fminf(reach, enter[i]);
  }
  return reach;
}

static bool clear_plan(const Final1Route *r, FieldPoint start) {
  for (unsigned i = 0; i < r->count; ++i) {
    FieldPoint q = r->points[i];
    if (Final1_ClearTravel(start, q.x - start.x, q.y - start.y, r->yaw) < 1)
      return false;
    start = q;
  }
  return true;
}

static void plan_translation(Final1Route *r, FieldPoint p, float yaw, int side,
                             bool injury) {
  /* Aim inside the host's ORIGINAL arrival window, towards the centre gap.
   * The host can issue D=0 before this nominal endpoint. */
  float x = (injury ? 75 : -75) * side, y = 540 * side;
  FieldPoint goal = {x, y};
  bool lateral_first = p.y * side <= 310 || p.y * side >= 845;
  *r = (Final1Route){.yaw = yaw, .initialized = true, .count = 2};
  for (int order = 0; order < 2; ++order) {
    r->points[0] = lateral_first ? (FieldPoint){x, p.y} : (FieldPoint){p.x, y};
    r->points[1] = goal;
    if (clear_plan(r, p))
      return;
    lateral_first = !lateral_first;
  }
  /* Outside a block: clear its inner row before crossing its x range. */
  r->count = 3;
  r->points[0] = (FieldPoint){p.x, 300 * side};
  r->points[1] = (FieldPoint){x, 300 * side};
  r->points[2] = goal;
  if (clear_plan(r, p))
    return;
  /* A wide sideways footprint may need to pass at x=0 first. */
  r->count = 4;
  r->points[1].x = 0;
  r->points[2] = (FieldPoint){0, y};
  r->points[3] = goal;
  if (clear_plan(r, p))
    return;
  r->count = 0;
  r->no_clear_path = true;
  r->points[0] = p;
}

bool Final1_CanTurn(FieldPoint p) {
  /* A 240 mm disk contains the swept low hull at EVERY heading and leaves
   * margin beyond its 228 mm reach. Stay on the field side of both fences. */
  if (fabsf(p.x) + 240 >= 1500 || fabsf(p.y) + 240 >= 1140)
    return false;
  float dx = fmaxf(0, fabsf(fabsf(p.x) - 325) - 75);
  float dy = fmaxf(0, fabsf(fabsf(p.y) - 610) - 50);
  return dx * dx + dy * dy > 240 * 240;
}

static bool window_entry(FieldPoint p, FieldPoint q, float tx, float ty,
                         FieldPoint *entry) {
  /* All proposed segments are axis-aligned. Clamp the starting coordinate
   * to the old host box to find the first point of intersection. */
  float x = fminf(tx + 100, fmaxf(tx - 100, p.x)),
        y = fminf(ty + 50, fmaxf(ty - 50, p.y));
  if ((x - p.x) * (x - q.x) > 0 || (y - p.y) * (y - q.y) > 0)
    return false;
  *entry = (FieldPoint){x, y};
  return true;
}

static bool door_turn_clear(FieldPoint p, float yaw, float goal) {
  float delta = remainderf(goal - yaw, 360);
  if (fabsf(delta) <= 3)
    return true;
  /* Ten-degree samples; 22 mm covers the arc between the nearest sample
   * and a 228 mm claw tip. Include 8 mm for the local corner tolerance. */
  unsigned steps = (unsigned)ceilf(fabsf(delta) / 10);
  for (unsigned i = 0; i <= steps; ++i) {
    float a = (yaw + delta * i / steps) * DEG_RAD, c = cosf(a), s = sinf(a);
    float xmin = INFINITY, xmax = -INFINITY, ymin = INFINITY, ymax = -INFINITY;
    for (unsigned k = 0; k < HULL_SIZE; ++k) {
      float x = p.x + c * low_hull[k].x - s * low_hull[k].y;
      float y = p.y + s * low_hull[k].x + c * low_hull[k].y;
      xmin = fminf(xmin, x);
      xmax = fmaxf(xmax, x);
      ymin = fminf(ymin, y);
      ymax = fmaxf(ymax, y);
    }
    for (int sx = -1; sx <= 1; sx += 2)
      for (int sy = -1; sy <= 1; sy += 2) {
        if (xmin <= sx * 325 + 75 + 30 && xmax >= sx * 325 - 75 - 30 &&
            ymin <= sy * 610 + 50 + 30 && ymax >= sy * 610 - 50 - 30)
          return false;
      }
  }
  return true;
}

void Final1_PlanStage(Final1Route *r, FieldPoint p, float yaw, int side,
                      bool injury) {
  plan_translation(r, p, yaw, side, injury);
  float target_yaw = 90 * side, tx = (injury ? 150 : -150) * side,
        ty = 540 * side;
  FieldPoint last = p, entry;
  bool need_turn = r->no_clear_path;
  for (unsigned i = 0; !need_turn && i < r->count; ++i) {
    if (window_entry(last, r->points[i], tx, ty, &entry)) {
      need_turn = !door_turn_clear(entry, yaw, target_yaw);
      break;
    }
    last = r->points[i];
  }
  if (!need_turn || fabsf(remainderf(target_yaw - yaw, 360)) <= 3)
    return;

  *r = (Final1Route){.initialized = true, .yaw = yaw, .turn_at_end = true};
  if (Final1_CanTurn(p))
    return;
  /* Optional pre-turn must itself be reachable at the original yaw without
   * first crossing the upper's D=0 window. Never turn in a pinched doorway. */
  FieldPoint pivots[] = {
      {0, p.y}, {p.x, 280 * side}, {0, 830 * side}, {0, 280 * side}};
  for (unsigned i = 0; i < sizeof(pivots) / sizeof(pivots[0]); ++i) {
    FieldPoint pivot = pivots[i];
    if (!Final1_CanTurn(pivot))
      continue;
    r->count = 2;
    r->points[0] = (FieldPoint){pivot.x, p.y};
    r->points[1] = pivot;
    if (!window_entry(p, r->points[0], tx, ty, &entry) &&
        !window_entry(r->points[0], pivot, tx, ty, &entry) && clear_plan(r, p))
      return;
  }
  r->count = 0;
  r->turn_at_end = false;
  r->no_clear_path = true;
  r->points[0] = p;
}

void Final1_PlanReturn(Final1Route *r, FieldPoint p, float yaw) {
  *r = (Final1Route){.yaw = yaw,
                     .initialized = true,
                     .count = 2,
                     .points = {{0, p.y}, {0, 0}}};
  /* The third leg follows live H/D to the station chosen by the host. */
}

bool Final1_NextLeg(Final1Route *r, FieldPoint p, float *heading,
                    float *remaining) {
  while (r->index < r->count) {
    FieldPoint q = r->points[r->index];
    float dx = q.x - p.x, dy = q.y - p.y;
    /* Each nominal leg is axial. Small cross-track drift is corrected on
     * the next cycle/leg; no diagonal shortcut while loaded. */
    bool horizontal = fabsf(dx) > fabsf(dy);
    float delta = horizontal ? dx : dy;
    if (fabsf(delta) > LEG_TOLERANCE_MM) {
      *heading = horizontal ? (delta > 0 ? 0 : 180) : (delta > 0 ? 90 : -90);
      *remaining = fabsf(delta);
      return true;
    }
    ++r->index;
  }
  return false;
}

void Final1_Interrupt(Final1Relief *r) {
  r->tracking = false;
  r->active = false;
}

bool Final1_ResolveStall(Final1Relief *r, FieldPoint p, float yaw, int side,
                         bool injury, bool visual, float h, uint32_t now,
                         float *drive, float *speed) {
  /* Only uninterrupted requests along the same axis accumulate evidence.
   * Reversing a visual correction immediately returns authority to the host. */
  bool same = r->tracking && now - r->last <= 60 &&
              cosf((r->direction - h) * DEG_RAD) > 0.94f;
  if (!same) {
    Final1_Interrupt(r);
    r->blocked = false;
    r->tracking = true;
    r->direction = h;
    r->origin = p;
    r->started = now;
  }
  r->last = now;
  if (r->blocked) {
    if (hypotf(p.x - r->origin.x, p.y - r->origin.y) < 8) {
      *speed = 0;
      return true;
    }
    r->blocked = false;
    r->origin = p;
    r->started = now;
  }
  if (!r->active) {
    float progress = (p.x - r->origin.x) * cosf(h * DEG_RAD) +
                     (p.y - r->origin.y) * sinf(h * DEG_RAD);
    if (now - r->started < 400)
      return false;
    r->origin = p;
    r->started = now;
    if (progress >= 8)
      return false;
    if (r->used) {
      r->blocked = true;
      *speed = 0;
      return true;
    }
    r->used = true;
    float target_x = (injury ? 150 : -150) * side;
    float inner = visual ? 60 : 10;
    float room = fminf(RELIEF_STEP_MM, fabsf(p.x) - inner);
    /* A visual attempt must stay inside the same host window, with 10 mm
     * reserve for braking on its centre and forward edges. */
    if (visual && (fabsf(p.x - target_x) > 100 || fabsf(p.y - side * 540) > 50))
      room = 0;
    if (visual)
      room = fminf(room, 580 - side * p.y);
    /* Keep the front of the model on the field side of the fence. */
    room = fminf(room, 1140 - 235 - side * p.y);
    float sx = p.x > 0 ? -1 : 1;
    if (room > 0)
      room *= Final1_ClearTravel(p, sx * room, side * room, yaw);
    if (room <= 5) {
      r->blocked = true;
      *speed = 0;
      return true;
    }
    r->goal = (FieldPoint){p.x + sx * room, p.y + side * room};
    r->active = true;
  }
  float dx = r->goal.x - p.x, dy = r->goal.y - p.y;
  /* Stop each axis independently if momentum took it past the endpoint. */
  if ((r->goal.x - r->origin.x) * dx <= 0)
    dx = 0;
  if ((r->goal.y - r->origin.y) * dy <= 0)
    dy = 0;
  float distance = hypotf(dx, dy);
  if (distance <= 4 || now - r->started >= 650) {
    bool failed =
        distance > 4 && hypotf(p.x - r->origin.x, p.y - r->origin.y) < 8;
    Final1_Interrupt(r);
    r->tracking = true;
    r->started = now;
    r->origin = p;
    r->blocked = failed;
    *speed = 0;
    return true;
  }
  if (Final1_ClearTravel(p, dx, dy, yaw) < 0.999f ||
      (visual && (fabsf(p.y - side * 540) > 50 ||
                  fabsf(p.x - (injury ? 150 : -150) * side) > 100))) {
    r->active = false;
    r->blocked = true;
    r->origin = p;
    *speed = 0;
    return true;
  }
  *drive = atan2f(dy, dx) / DEG_RAD;
  *speed = fminf(180, 5 * distance + 35);
  return true;
}
