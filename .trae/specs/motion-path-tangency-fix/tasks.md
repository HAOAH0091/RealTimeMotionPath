# Tasks

- [x] Task 1: Update `build_position_cache` to calculate and store split velocities
  - [x] SubTask 1.1: Calculate `velocity_prev` (backward difference)
  - [x] SubTask 1.2: Calculate `velocity_next` (forward difference)
  - [x] SubTask 1.3: Store both in cache (replacing `world_velocity`)
- [x] Task 2: Update `draw_motion_path_handles` to use split logic
  - [x] SubTask 2.1: Determine frame type (Start, End, Middle) based on velocity availability
  - [x] SubTask 2.2: Implement Start Frame logic (Right Handle only)
  - [x] SubTask 2.3: Implement End Frame logic (Left Handle only)
  - [x] SubTask 2.4: Implement Middle Frame logic (Both Handles, Center Difference Tangent)
- [x] Task 3: Update `get_motion_path_handle_at_mouse` to match drawing logic
  - [x] SubTask 3.1: Update Start/End/Middle detection to allow selection of visible handles only
- [x] Task 4: Verify
  - [x] SubTask 4.1: Verify Start Frame has only Right Handle
  - [x] SubTask 4.2: Verify End Frame has only Left Handle
  - [x] SubTask 4.3: Verify Middle Frames have both
  - [x] SubTask 4.4: Verify no "kinks" in middle frames (tangent continuity)
