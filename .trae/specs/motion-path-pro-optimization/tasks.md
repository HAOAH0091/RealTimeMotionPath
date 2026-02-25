# Tasks

- [x] Task 1: Create Data Structure for Style Settings
    - [x] SubTask 1.1: Define a new PropertyGroup class `MotionPathStyleSettings` in `__init__.py`.
        - Properties for Path: `path_width` (Float), `path_color` (FloatVector, subtype='COLOR', size=4).
        - Properties for Frame Points: `show_frame_points` (Bool), `frame_point_size` (Float), `frame_point_color` (FloatVector, subtype='COLOR', size=4).
        - Properties for Keyframe Points: `keyframe_point_size` (Float), `keyframe_point_color` (FloatVector, subtype='COLOR', size=4), `selected_keyframe_point_color` (FloatVector, subtype='COLOR', size=4).
        - Properties for Handles: `handle_line_width` (Float), `handle_line_color` (FloatVector, subtype='COLOR', size=4), `selected_handle_line_color` (FloatVector, subtype='COLOR', size=4), `handle_endpoint_size` (Float), `handle_endpoint_color` (FloatVector, subtype='COLOR', size=4), `selected_handle_endpoint_color` (FloatVector, subtype='COLOR', size=4).
    - [x] SubTask 1.2: Register the PropertyGroup and assign it to `bpy.types.WindowManager.motion_path_styles`.

- [x] Task 2: Create UI Panel for Style Settings
    - [x] SubTask 2.1: Define a new Panel class `MOTIONPATH_StyleSettingsPanel` (or integrate into existing panel).
    - [x] SubTask 2.2: Add properties to the panel layout in `draw` method.
    - [x] SubTask 2.3: Register the panel.

- [x] Task 3: Implement Frame Points Drawing
    - [x] SubTask 3.1: In `draw_motion_path_overlay`, implement logic to iterate over `_state.position_cache`.
    - [x] SubTask 3.2: Skip keyframe points (already drawn separately).
    - [x] SubTask 3.3: Use `gpu.shader.from_builtin('UNIFORM_COLOR')` and `batch_for_shader` to draw points efficiently.
    - [x] SubTask 3.4: Respect `show_frame_points`, `frame_point_size`, and `frame_point_color` settings.

- [x] Task 4: Update Path Drawing Logic
    - [x] SubTask 4.1: Update `draw_motion_path_overlay` to use `path_width` and `path_color` settings for the line strip.

- [x] Task 5: Update Keyframe Point Drawing Logic
    - [x] SubTask 5.1: Update `draw_motion_path_point` to use `keyframe_point_size`, `keyframe_point_color`, and `selected_keyframe_point_color` settings.
    - [x] SubTask 5.2: Ensure proper selection highlighting is maintained (e.g., different color/size).

- [x] Task 6: Update Handle Drawing Logic
    - [x] SubTask 6.1: Update `draw_motion_path_handles` to use circular endpoints instead of squares.
    - [x] SubTask 6.2: Use `handle_line_width`, `handle_line_color`, `selected_handle_line_color` for lines.
    - [x] SubTask 6.3: Use `handle_endpoint_size`, `handle_endpoint_color`, `selected_handle_endpoint_color` for endpoints.
    - [x] SubTask 6.4: Ensure proper selection highlighting is maintained.

# Task Dependencies
- Task 2 depends on Task 1.
- Task 3, 4, 5, 6 depend on Task 1.
