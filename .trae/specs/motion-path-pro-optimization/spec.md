# Motion Path Pro Optimization Spec

## Why
Currently, the plugin lacks visual feedback for animation speed (frame points) and customization options for styles (path color, width, handle size/shape). Users have requested these features to improve usability and match their workflow preferences. The square handle endpoints also look outdated compared to modern UI standards.

## What Changes
- Add frame points drawing on the motion path to visualize speed.
- Add a new "Style Settings" panel for customizing path, points, and handles.
- Change handle endpoints from square to circle.
- Update drawing logic to respect user-defined styles.

## Impact
- **Affected specs**: None (new feature set).
- **Affected code**:
    - `__init__.py`: Will add new PropertyGroup for settings, new Panel class, and update drawing functions (`draw_motion_path_overlay`, `draw_motion_path_handles`).
    - `MotionPathState`: Might need updates to cache style settings if performance requires it (though direct property access is usually fine for UI settings).

## ADDED Requirements

### Requirement: Frame Points on Path
The system SHALL draw small points on the motion path for every frame to visualize speed.
- **Scenario: Speed Visualization**
    - **WHEN** the user enables "Show Frame Points" (default on)
    - **THEN** small circular points are drawn at each frame's position on the path.
    - **AND** points are denser where movement is slow, and sparser where movement is fast.

### Requirement: Customizable Styles
The system SHALL provide a UI panel to customize the appearance of the motion path elements.
- **Scenario: Custom Path Style**
    - **WHEN** the user changes "Path Width" or "Path Color"
    - **THEN** the motion path line updates immediately in the viewport.
- **Scenario: Custom Point Style**
    - **WHEN** the user changes "Frame Point Size" or "Frame Point Color"
    - **THEN** the frame points update immediately.
- **Scenario: Custom Keyframe Point Style**
    - **WHEN** the user changes "Keyframe Size" or "Keyframe Color" (normal/selected)
    - **THEN** the keyframe points update immediately.
- **Scenario: Custom Handle Style**
    - **WHEN** the user changes "Handle Line Width", "Handle Line Color", "Handle Endpoint Size", or "Handle Endpoint Color"
    - **THEN** the handles update immediately.
    - **AND** there are separate color settings for normal and selected states.

### Requirement: Circular Handle Endpoints
The system SHALL draw handle endpoints as circles instead of squares.
- **Scenario: Modern Look**
    - **WHEN** handles are drawn
    - **THEN** the endpoints are circular.
    - **AND** the size matches the user setting.

## MODIFIED Requirements

### Requirement: Drawing Logic
The existing drawing functions will be updated to use the new style properties and draw the new elements.
- `draw_motion_path_overlay`: Updated to draw frame points and use custom path styles.
- `draw_motion_path_handles`: Updated to use circular endpoints and custom handle styles.

## REMOVED Requirements
- **Requirement**: Square Handle Endpoints
    - **Reason**: Replaced by circular endpoints for better aesthetics.
