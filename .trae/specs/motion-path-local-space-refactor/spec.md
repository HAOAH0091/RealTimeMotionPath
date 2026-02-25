# Motion Path Local Space Refactor Spec

## Why
Currently, the Motion Path Pro addon calculates and draws paths and handles in **World Space**. This leads to several critical issues:
1.  **Visual Distortion**: When a parent object moves or rotates, the child's path (calculated frame-by-frame in world space) distorts in ways that don't reflect the actual local animation curve.
2.  **Interaction Slippage**: Dragging handles is "slippery" because the reference frame (parent's world transform) is changing over time, but the interaction logic tries to compensate for it frame-by-frame, leading to precision errors and "jumping".
3.  **Complexity**: The current implementation relies on finite difference methods to calculate "world velocity" to determine handle direction, which is error-prone and computationally expensive.

## What Changes
We will refactor the entire core logic to operate in **Local Space** (relative to the parent).
-   **Data Storage**: The position cache will store **Local Coordinates** (relative to the parent's transform at that frame) instead of World Coordinates.
-   **Drawing**: We will use the **Current Frame's Parent Matrix** as the model matrix for drawing. This means the path will be drawn as if it were a rigid object attached to the parent, moving and rotating with it in real-time.
-   **Interaction**: Handle manipulation will calculate the mouse position in World Space, then transform it into Local Space using the **Current Parent Matrix**, and apply the delta directly to the F-Curve. This ensures 1:1 mapping between mouse movement and data change.

## Impact
-   **Affected Files**: `__init__.py` (Core logic is here).
-   **Affected Functions**:
    -   `build_position_cache`: Will be simplified to store local data and remove velocity calculations.
    -   `draw_motion_path_handles` & `draw_motion_path_point`: Will be updated to transform local points by the current parent matrix during drawing.
    -   `move_selected_handles`, `move_handle_point`, `move_selected_points`: Will be updated to use the current parent matrix for World-to-Local transformation.
    -   `get_motion_path_handle_at_mouse` & `get_motion_path_point_at_mouse`: Will be updated to perform hit testing using the new drawing logic (Local * Current Parent Matrix).

## ADDED Requirements
### Requirement: Local Space Caching
The system SHALL cache keyframe and path points in Local Space.
-   **Object Mode**: Store `obj.matrix_local.translation`.
-   **Pose Mode**: Store bone positions relative to the armature (or parent bone, effectively "Armature Space" for drawing).

### Requirement: Parent-Relative Drawing
The system SHALL draw the path and handles using the Parent Object's *current* World Transform.
-   **Scenario**: Parent moves.
    -   **THEN**: The entire drawn path moves with the parent rigidly. The shape of the path does *not* change.

### Requirement: Direct Handle Interaction
The system SHALL calculate handle interaction by transforming Mouse World Position to Local Space using the Current Parent Matrix.
-   **Scenario**: User drags a handle.
    -   **THEN**: The handle moves exactly with the mouse cursor, without jitter or offset, regardless of parent animation.

## MODIFIED Requirements
### Requirement: `build_position_cache`
Modified to remove `velocity_prev` and `velocity_next` calculations. It will only store position and rotation data needed for local-to-world reconstruction if necessary, but primarily local positions.

### Requirement: `draw_motion_path_handles`
Modified to calculate handle direction and length directly from F-Curve data (`handle_right - co`), rather than derived velocity.

## REMOVED Requirements
### Requirement: World Velocity Calculation
**Reason**: No longer needed as we use explicit F-Curve tangents in local space.
**Migration**: Remove all finite difference code.
