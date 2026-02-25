# Motion Path Custom Draw Spec

## Why
Blender 原生的运动路径（Motion Path）系统在视觉样式和控制上存在限制（如线宽、颜色、扭曲等不可定制），且插件目前采用“原生路径线 + 自绘手柄”的双层叠加模式，导致计算冗余和视觉不一致。为了提供更统一、高效且可定制的编辑体验，插件将完全接管路径线的绘制，不再依赖 Blender 原生系统。

## What Changes
### 核心架构变更
- **移除原生依赖**：不再调用 `object.paths_calculate` 等原生操作，不再显示原生运动路径。
- **单一数据源**：路径线、关键帧点、手柄均基于插件内部的 `_state.position_cache` 数据绘制。
- **全自绘实现**：使用 `gpu` 模块和 `batch_for_shader` 绘制完整的运动轨迹线。

### UI 变更
- **简化面板**：移除原有的复杂操作面板（Calculate, Update, Clear 等）。
- **核心开关**：在动画控制区域（如时间线/控制台附近）添加一个“启用自定义路径线”开关。
- **参数控制**：提供基础的显示控制（如帧范围、步长，如果需要），但首选默认配置。

### 数据与绘制
- **采样策略**：默认采用“每一帧采样”（步长=1），确保路径平滑且精确。
- **绘制逻辑**：
  - 在 `build_position_cache` 或专门的更新函数中构建路径线的顶点数据（`vertices`）。
  - 使用 `gpu.shader.from_builtin('UNIFORM_COLOR')` 或 `SMOOTH_COLOR` 进行批处理绘制（`LINE_STRIP`）。
  - 支持基础样式：不同颜色区分选中/未选中对象，或基于速度/时间着色。

### 交互
- **实时更新**：拖拽手柄修改 F-Curve 后，立即触发缓存重建和路径线重绘，保证“所见即所得”。
- **本地路径**：第一阶段仅绘制子级对象的本地路径（基于 Location F-Curve），暂不处理复杂的父子级世界空间偏移（除非已由缓存支持）。

## Impact
- **Affected Specs**: 涉及现有的 `motion-path-handle-logic-optimization`（如果还在进行中）。
- **Affected Code**:
  - `__init__.py`:
    - `AutoMOTIONPATHSPanel`: 需要大幅简化。
    - `draw_motion_path_overlay`: 增加路径线绘制逻辑。
    - `build_position_cache`: 确保数据满足绘制需求。
    - `MOTIONPATH_DirectManipulation`: 确保拖拽结束更新缓存。
    - 新增/修改 Operator 以支持新开关。

## ADDED Requirements
### Requirement: Custom Path Drawing
The system SHALL draw motion paths using Blender's `gpu` module based on cached world positions.
- **Scenario**: User enables "Custom Motion Path".
- **Result**: A colored line strip is drawn connecting keyframes and interpolated frames in the 3D viewport.

### Requirement: Simplified UI
The system SHALL provide a simplified UI with a toggle for the custom motion path feature.
- **Scenario**: User looks at the Motion Path Pro panel.
- **Result**: Old complex buttons are gone; a clear toggle/switch is visible.

## MODIFIED Requirements
### Requirement: Data Caching
The `build_position_cache` function SHALL be optimized/verified to support dense sampling (every frame) for smooth path drawing.

## REMOVED Requirements
### Requirement: Native Motion Path Support
**Reason**: Replaced by custom drawing for better control and performance.
**Migration**: Users will switch to the new custom path system; old native paths will be cleared or hidden.
