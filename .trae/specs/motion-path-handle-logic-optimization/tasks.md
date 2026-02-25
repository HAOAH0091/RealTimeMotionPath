# Tasks

- [x] Task 1: Refactor `draw_motion_path_handles` implementation
  - [x] SubTask 1.1: Implement new handle calculation logic (Direction from Velocity, Length from F-Curve)
  - [x] SubTask 1.2: Remove fallback logic and skip handle generation when velocity is near zero
- [x] Task 2: Refactor `get_motion_path_handle_at_mouse` implementation
  - [x] SubTask 2.1: Update detection logic for Selected Bones (sync with Task 1)
  - [x] SubTask 2.2: Update detection logic for Active Bone (sync with Task 1)
  - [x] SubTask 2.3: Update detection logic for Object Mode (sync with Task 1)
- [x] Task 3: Verify the changes
  - [x] SubTask 3.1: Verify moving objects have correct handle direction and stable length
  - [x] SubTask 3.2: Verify static/clamped objects have NO handles (and no interaction conflict)

# Task Dependencies
- Task 2 depends on Task 1 logic being clear (though they can be implemented in parallel if logic is shared).
