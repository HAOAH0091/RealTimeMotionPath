# Motion Path Pro 撤销机制优化计划

## 1. 问题分析 (Problem Analysis)

用户反馈插件的撤销机制存在问题。经过代码审查，发现以下严重问题：

1.  **高频 Undo Push**:
    -   在 `MOTIONPATH_DirectManipulation` 模态操作中，处理 `MOUSEMOVE` 事件的函数（`move_selected_points`, `move_selected_handles`, `move_handle_point`）内部直接调用了 `bpy.ops.ed.undo_push()`。
    -   这意味着在用户拖拽手柄的过程中，每秒钟可能会触发几十次 Undo Push。
    -   **后果**: Undo 栈被瞬间填满，导致用户按 Ctrl+Z 只能撤销极其微小的移动，且严重影响性能。

2.  **Modal Operator 生命周期**:
    -   该 Operator 设计为长生命周期（Long-running Modal），直到用户显式关闭。
    -   因此不能依赖 Operator 结束时的自动 Undo，必须手动管理 Undo Push。

## 2. 解决方案 (Solution)

将 `undo_push` 的调用时机从“拖拽进行中”移动到“拖拽结束时”。

### 2.1 修改 `move_*` 函数
-   **移除** `move_selected_points` 中的 `bpy.ops.ed.undo_push()`。
-   **移除** `move_selected_handles` 中的 `bpy.ops.ed.undo_push()`。
-   **移除** `move_handle_point` 中的 `bpy.ops.ed.undo_push()`。

### 2.2 修改 `modal` 方法
-   在 `LEFTMOUSE` 的 `RELEASE` 事件处理块中：
    -   当检测到 `_state.is_dragging` 为 True（移动关键帧点）时，在重置状态前调用 `bpy.ops.ed.undo_push(message="Move Motion Path Points")`。
    -   当检测到 `_state.handle_dragging` 为 True（移动手柄）时，在重置状态前调用 `bpy.ops.ed.undo_push(message="Move Motion Path Handle")`。

## 3. 验证计划 (Verification Plan)

1.  **操作验证**:
    -   启动 Direct Manipulation 模式。
    -   拖动一个手柄，大幅度移动。
    -   松开鼠标。
    -   按 Ctrl+Z。
    -   **预期结果**: 手柄应该一次性回到拖动前的位置，而不是只回退一点点。

2.  **性能验证**:
    -   在拖动过程中观察流畅度，应该比之前更流畅（减少了大量的 Undo 写入开销）。

3.  **连续操作验证**:
    -   拖动一次，松开。再拖动另一次，松开。
    -   按 Ctrl+Z 两次。
    -   **预期结果**: 依次撤销第二次和第一次的拖动。
