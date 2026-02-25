# Motion Path Handle Logic Optimization Spec

## Why
1. **手柄长度异常**：旧逻辑中手柄长度受物体运动速度影响，速度快时手柄会被拉得极长甚至飞出屏幕，导致操作困难且视觉混乱。
2. **末尾帧交互问题**：末尾帧由于速度计算为0，手柄会缩成一个点（或需要回退机制才能显示），导致手柄遮挡关键帧或无法调节。
3. **逻辑统一**：希望统一手柄的计算逻辑，不再依赖复杂的回退判断，而是基于明确的物理规则（动则有切线，静则无切线）。

## What Changes
- **重构手柄计算逻辑**：
    - **方向 (Direction)**：完全由 **世界速度 (World Velocity)** 决定，确保切线正确。
    - **长度 (Length)**：完全由 **F-Curve 原始数据** 决定，不受速度大小影响。
- **移除旧的回退机制**：
    - 不再在速度极小时回退使用父级旋转后的局部手柄位置。
    - 改为：当速度极小（< 1e-6，即静止或末尾帧钳制）时，**直接不生成手柄**。
- **API 变更**：
    - `draw_motion_path_handles` 函数逻辑更新。
    - `get_motion_path_handle_at_mouse` 函数逻辑更新（3处调用点）。

## Impact
- **Affected Specs**: 
    - 之前的“末尾帧手柄锁定问题修复”逻辑将被新逻辑覆盖。
    - 静止物体的关键帧将不再显示手柄（符合预期）。
- **Affected Code**: 
    - `c:\Users\Windows\AppData\Roaming\Blender Foundation\Blender\5.0\extensions\user_default\Motion_Path_Pro\__init__.py`

## ADDED Requirements
### Requirement: New Handle Calculation
The system SHALL calculate handle position using:
- Direction = Normalize(World Velocity)
- Length = Length(Parent Matrix * Local Handle Vector)
- Final Position = Keyframe Position + (Direction * Length)

#### Scenario: Moving Object
- **WHEN** object has velocity > 0
- **THEN** handle is drawn with correct tangent direction and stable length derived from F-Curve.

#### Scenario: Static Object (Zero Velocity)
- **WHEN** object has velocity ≈ 0 (e.g. static or clamped last frame)
- **THEN** handle is NOT drawn.

## REMOVED Requirements
### Requirement: Fallback Mechanism
**Reason**: The fallback mechanism (using local rotation when velocity is small) is replaced by the "no handle when static" rule for clarity and simplicity.
**Migration**: Remove the fallback code block in `draw_motion_path_handles` and `get_motion_path_handle_at_mouse`.
