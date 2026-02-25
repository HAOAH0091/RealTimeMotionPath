# Motion Path Tangency Fix Spec

## Why
1. **末尾帧/起始帧手柄消失**：由于帧钳制或没有前后帧，导致中心差分计算的速度为0，手柄不显示。用户希望看到手柄。
2. **手柄切线方向精确性**：目前统一使用“中心差分”的速度作为双侧手柄的方向。但在曲线转折剧烈或起止点，前向切线和后向切线可能不共线（虽然对于位置连续的运动路径通常是平滑的，但速度变化可能不均匀）。
3. **用户改进建议**：分别计算前向速度（用于右侧手柄）和后向速度（用于左侧手柄），并在只有一侧速度时只绘制一侧手柄。

## What Changes
- **缓存结构变更**：
    - `position_cache` 不再存储单一的 `world_velocity`。
    - 改为存储 `velocity_prev` (后向速度) 和 `velocity_next` (前向速度)。
- **速度计算逻辑变更 (`build_position_cache`)**：
    - 计算 `pos_prev` -> `pos_curr` 的差分作为 `velocity_prev`。
    - 计算 `pos_curr` -> `pos_next` 的差分作为 `velocity_next`。
    - 处理边界情况：如果 `pos_prev` 取不到（起始帧），`velocity_prev` 为 None/Zero；同理 `velocity_next`。
- **手柄绘制逻辑变更 (`draw_motion_path_handles`)**：
    - **左手柄**：优先使用 `velocity_prev` 的反方向。如果 `velocity_prev` 无效，尝试使用 `velocity_next` 的反方向（共线假设）。如果都无效，不绘制。
    - **右手柄**：优先使用 `velocity_next` 的方向。如果 `velocity_next` 无效，尝试使用 `velocity_prev` 的方向（共线假设）。如果都无效，不绘制。
    - **更新**：用户建议“初始帧和末尾帧只绘制一个手柄”。这意味着：
        - 起始帧：没有 `velocity_prev`，只画右手柄（指向未来）。
        - 末尾帧：没有 `velocity_next`，只画左手柄（指向过去）。
- **交互检测变更 (`get_motion_path_handle_at_mouse`)**：
    - 同步更新检测逻辑，确保只能选中绘制出来的手柄。

## Impact
- **Affected Specs**: 之前的“手柄逻辑优化”将被此更精细的逻辑覆盖。
- **Affected Code**: `__init__.py` 中的缓存构建、绘制、交互检测函数。

## ADDED Requirements
### Requirement: Split Velocity Calculation
The system SHALL calculate and cache two velocity vectors per keyframe:
- `velocity_prev`: Vector from (Frame - 0.01) to Frame.
- `velocity_next`: Vector from Frame to (Frame + 0.01).

### Requirement: Conditional Handle Drawing
- **Left Handle**: Drawn if `velocity_prev` exists (or fallback to inverted `velocity_next` if strictly continuous).
    - **User Requirement**: For Start/End frames, maybe strict splitting is better. Let's follow the "tangent" concept.
    - **Refined Rule**:
        - **Left Handle** (Incoming): Uses `velocity_prev`. If Start Frame (no prev), do not draw? Or draw using `velocity_next` inverted?
            - *Decision*: Users said "Start/End frames... can calculate only one handle".
            - **Start Frame**: Draw ONLY Right Handle (using `velocity_next`).
            - **End Frame**: Draw ONLY Left Handle (using `velocity_prev`).
            - **Middle Frames**: Draw BOTH. Left uses `velocity_prev`, Right uses `velocity_next`.
            - **Wait**: Standard Bezier handles usually try to be collinear (Continuous) unless broken. If we split them strictly, we might show a "kink" that doesn't exist in the F-Curve (which forces continuity).
            - **Correction**: F-Curves enforce continuity. The physical path should also be continuous.
            - **Better Approach**:
                - Calculate `tangent` direction.
                - If Middle Frame: Use `(pos_next - pos_prev).normalized()` (Center Difference) for SMOOTH tangents.
                - If Start Frame: Use `(pos_next - pos_curr).normalized()` (Forward Difference).
                - If End Frame: Use `(pos_curr - pos_prev).normalized()` (Backward Difference).
                - **Drawing**:
                    - Always draw BOTH handles if F-Curve has them, using this unified tangent.
                    - **UNLESS** the user explicitly wants to hide the "out of bounds" handle?
                    - Blender's F-Curve editor shows both handles even at ends (extrapolation).
                    - But for *Motion Path*, the path ends.
                    - **User's specific request**: "Initial and End frames... can calculate only one handle".
                    - **Let's implement this**:
                        - Start Frame: Draw Right Handle only.
                        - End Frame: Draw Left Handle only.
                        - Middle: Draw Both.

#### Scenario: Start Frame
- **WHEN** current frame is start of animation
- **THEN** Only Right handle is drawn. Direction = `(pos_next - pos_curr)`.

#### Scenario: End Frame
- **WHEN** current frame is end of animation
- **THEN** Only Left handle is drawn. Direction = `(pos_curr - pos_prev)`.

#### Scenario: Middle Frame
- **WHEN** frame has both prev and next
- **THEN** Draw both. Direction = `(pos_next - pos_prev)`.

## REMOVED Requirements
### Requirement: Single World Velocity
**Reason**: Replaced by split/adaptive velocity calculation to handle boundary conditions better.
