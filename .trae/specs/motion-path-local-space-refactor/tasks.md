# Tasks

- [ ] Task 1: Refactor `build_position_cache` to store Local Space data
    -   [ ] Modify `build_position_cache` to store `matrix_local` translation for Objects.
    -   [ ] Modify `build_position_cache` to store Armature-Space positions for Bones.
    -   [ ] Remove all velocity calculation code (finite difference) from this function.
    -   [ ] Remove sub-frame sampling (prev/next 0.01 frame) as velocity is no longer needed.

- [ ] Task 2: Refactor Drawing Logic (`draw_motion_path_overlay` and helpers)
    -   [ ] Implement helper to get `current_parent_matrix` (Object's parent matrix or Armature's matrix).
    -   [ ] Update `draw_enhanced_object_path` and `draw_enhanced_bone_path` to transform cached local points by `current_parent_matrix` before drawing.
    -   [ ] Update `draw_motion_path_handles` to calculate handle vectors directly from F-Curve data (`handle_vector = handle_pos - co`).
    -   [ ] Ensure handles are drawn by transforming these local vectors by `current_parent_matrix`.

- [ ] Task 3: Refactor Hit Testing Logic
    -   [ ] Update `get_motion_path_point_at_mouse` to project (Local Point * Current Parent Matrix) to screen.
    -   [ ] Update `get_motion_path_handle_at_mouse` to project (Local Handle * Current Parent Matrix) to screen.
    -   [ ] Ensure hit testing matches the new visual representation.

- [ ] Task 4: Refactor Interaction Logic (`DirectManipulation`)
    -   [ ] Update `move_selected_points` to use `current_parent_matrix` for World-to-Local delta calculation.
    -   [ ] Update `move_selected_handles` and `move_handle_point` to use `current_parent_matrix` for World-to-Local delta calculation.
    -   [ ] Simplify logic: Remove any dependency on "cached parent matrix at keyframe time". Always use the *current* parent matrix.

- [ ] Task 5: Cleanup and Verification
    -   [ ] Remove unused code (velocity calculation helpers, old specific math).
    -   [ ] Verify Object Mode interaction with parent animation.
    -   [ ] Verify Pose Mode interaction with parent bone animation.
