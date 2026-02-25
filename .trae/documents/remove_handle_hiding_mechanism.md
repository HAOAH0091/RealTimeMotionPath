# 移除手柄隐藏机制计划

## 1. 目标
移除当手柄长度接近 0 时隐藏手柄的机制，使得所有关键帧（包括首尾帧和平坦关键帧）的手柄都可见且可交互。同时优化交互优先级，确保零长度手柄容易被选中。

## 2. 受影响文件
- [__init__.py](file:///c:/Users/Windows/AppData/Roaming/Blender%20Foundation/Blender/5.0/extensions/user_default/Motion_Path_Pro/__init__.py)

## 3. 修改步骤

### 步骤 1: 修改绘制逻辑 (`draw_motion_path_handles`)
- **位置**: `draw_motion_path_handles` 函数 (约 Line 532, 550)
- **操作**: 
    - 移除 `if len_left > 1e-6:` 判断，改为无条件执行绘制逻辑。
    - 移除 `if len_right > 1e-6:` 判断，改为无条件执行绘制逻辑。
- **预期结果**: 即使手柄长度为 0，也会绘制手柄端点（此时端点与关键帧位置重合）。

### 步骤 2: 修改交互检测逻辑 (`get_motion_path_handle_at_mouse`)
- **位置**: `get_motion_path_handle_at_mouse` 内部函数 `check_handles_at_frame` (约 Line 1442, 1449)
- **操作**:
    - 移除 `if world_vector_left.length > 1e-6:` 判断。
    - 移除 `if world_vector_right.length > 1e-6:` 判断。
- **预期结果**: 鼠标检测逻辑将能够识别零长度的手柄。

### 步骤 3: 调整交互优先级 (`modal`)
- **问题分析**: 目前代码中先检测“路径点” (`get_motion_path_point_at_mouse`)，后检测“手柄” (`get_motion_path_handle_at_mouse`)。当手柄长度为 0 时，手柄端点与路径点重合，导致用户点击时总是优先选中路径点，无法拖出手柄。
- **操作**:
    - 在 `MOTIONPATH_DirectManipulation.modal` 方法中 (约 Line 966-1047)。
    - 将 `get_motion_path_handle_at_mouse` 的检测逻辑块移动到 `get_motion_path_point_at_mouse` 之前。
- **预期结果**: 当鼠标位于重合点时，优先响应手柄拖动操作，解决无法从零长度拉出手柄的问题。

## 4. 验证计划
1. **视觉验证**: 
   - 在 Blender 中观察首尾帧（通常手柄长度为0）。
   - 确认是否能看到手柄端点（此时应显示为关键帧点上的额外圆圈或颜色变化）。
2. **交互验证**:
   - 尝试点击并拖动首尾帧的位置。
   - 确认是否触发“手柄拖动”而不是“移动关键帧”。
