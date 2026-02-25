# 手柄交互重构：总偏移量法 (Total Offset Method)

## 🐛 问题根源
之前的“增量累加法”和“绝对位置计算法”在父级有动画时存在根本缺陷：
1.  **父级干扰**：试图从世界速度反推本地手柄位置，忽略了父级本身的速度贡献，导致双重计算。
2.  **漂移积累**：每一帧的微小误差会累积，导致手柄位置漂移。
3.  **跳变**：一旦开始拖动，手柄会被强制重置到基于速度的理论位置，丢失初始状态。

## 🛠️ 解决方案
改用**总偏移量法**。不再试图计算手柄的“绝对位置”，而是只计算用户的“相对移动量”。

**核心逻辑**：
$$ New\_Local\_Handle = Initial\_Local\_Handle + (Inverse(Parent\_Rotation) \times Total\_World\_Offset) $$

---

## 📅 实施计划

### 1. 修改 `MotionPathState` 类
-   增加 `initial_handle_values` 字典，用于存储拖动开始时受影响关键帧的原始手柄值。

### 2. 修改 `MOTIONPATH_DirectManipulation.modal` 方法
-   **Press (开始拖动)**：
    -   调用 `capture_initial_handle_values`（新函数），记录当前选中手柄的原始值。
    -   记录鼠标的起始 3D 位置 `_state.drag_start_3d`。
-   **MouseMove (拖动中)**：
    -   计算当前鼠标 3D 位置。
    -   计算**总偏移量**：`total_offset_world = current_mouse_3d - _state.drag_start_3d`。
    -   调用 `move_selected_handles`，传入这个 `total_offset_world`。
    -   **不再更新 `drag_start_3d`**（保持参考点固定）。

### 3. 重写 `move_selected_handles` 方法
-   **参数变更**：接收 `total_offset_world` 而不是 `new_handle_pos`。
-   **逻辑变更**：
    -   不再使用 `world_velocity` 反推位置。
    -   直接使用 `initial_handle_values` 作为基准。
    -   将 `total_offset_world` 逆向旋转为 `total_offset_local`。
    -   更新手柄：`keyframe.handle = initial_value + total_offset_local`。

### 4. 验证目标
-   拖动开始时无任何跳变。
-   拖动过程中手柄平滑跟随鼠标。
-   即使父级在快速移动/旋转，手柄也能正确响应用户的相对输入。
