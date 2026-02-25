# 问题分析与修复计划

## 1. 问题复现与原因分析

### 问题 1: 新建场景下，开启插件导致对象被“锁死”在原位，无法移动
*   **现象**: 打开运动路径开关后，对对象 K 帧位移，对象无法移动。关闭开关后恢复正常。
*   **原因分析**:
    *   `MOTIONPATH_DirectManipulation` 是一个 Modal Operator，它接管了 3D 视图的鼠标事件。
    *   在 `modal` 函数中，如果鼠标没有悬停在路径点或手柄上，理论上应该返回 `{'PASS_THROUGH'}` 让事件传递给 Blender 的变换工具（G/R/S）。
    *   **关键漏洞**: 当用户尝试使用 Blender 原生工具（如 G 键移动）时，如果此时插件的 Modal Operator 正在运行且拦截了事件，或者因为某些逻辑错误导致 `PASS_THROUGH` 没有正确触发，就会导致操作失效。
    *   **更深层原因**: 很可能是因为 `modal` 函数中对事件的判断逻辑过于激进，或者在某些状态下（如 `_state.is_dragging` 为 False 时）没有正确放行事件。特别是在没有选中任何路径点时，如果鼠标移动触发了 `MOUSEMOVE` 但没有命中任何东西，代码虽然返回了 `PASS_THROUGH`，但如果之前的 `LEFTMOUSE` 点击被错误拦截（即使没点中东西），Blender 的选择或变换操作就会失败。
    *   **代码审查**: 在 `modal` 函数中：
        ```python
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                # ...
                hit_point, ... = self.get_motion_path_point_at_mouse(...)
                if hit_frame is not None:
                    return {'RUNNING_MODAL'}
                # 如果没点中，继续向下...
                
                # 这一段逻辑在处理 handle 点击检测
                hit_side, ... = self.get_motion_path_handle_at_mouse(...)
                if hit_frame is not None:
                    return {'RUNNING_MODAL'}
                
                # 如果都没点中，这里应该返回 PASS_THROUGH
                return {'PASS_THROUGH'} 
        ```
        目前的代码逻辑看起来是正确的（没点中就放行）。
        但是！问题可能出在 **G 键 (Transform)** 等快捷键上。Modal Operator 默认会吞掉所有它不明确放行的键盘事件。
        在 `modal` 函数中，我没有看到对键盘事件（除了 `ESC`）的显式处理或放行逻辑。如果用户按下 G 键，`event.type` 是 'G'，代码会走到最后的 `return {'PASS_THROUGH'}`。
        **真正的嫌疑人**: 可能是 `find_region_under_mouse` 或其他检测逻辑在某些边缘情况下返回了错误，导致误判。
        或者，更可能是 **Blender 的事件传递机制**。当 Modal Operator 运行时，它确实拥有最高优先级。如果它返回 `PASS_THROUGH`，事件应该继续传递。
        **注意**: 如果用户是在新建场景中，可能还没有生成路径数据？
        **修正思路**: 确保所有未被插件明确处理的事件（特别是键盘快捷键、变换操作相关的鼠标事件）都能无阻碍地传递。

### 问题 2: 骨架物体（Object Mode）无法交互，而普通物体和 Pose Mode 骨骼正常
*   **现象**: 关闭插件 -> 选中骨架物体 -> K帧 -> 开启插件 -> 无法操作路径点。
*   **原因分析**:
    *   我在之前的代码分析中看到了一段逻辑：
        ```python
        obj = context.active_object
        if obj and obj.type == 'ARMATURE' and obj.mode == 'OBJECT' and wm.direct_manipulation_active:
            # Just pass through events in Object Mode, do not cancel or disable
            return {'PASS_THROUGH'}
        ```
    *   **这就是原因！** 这段代码原本是为了解决“在物体模式下误触插件导致无法选择骨架”的问题（之前的修复）。
    *   **副作用**: 它现在 **完全禁止了** 在物体模式下对骨架运动路径的交互。
    *   **用户需求**: 用户希望在物体模式下也能编辑骨架的**整体位移路径**（就像编辑普通立方体一样）。
    *   **逻辑矛盾**: 我们之前认为骨架在物体模式下不需要编辑路径（通常是在 Pose Mode 编辑骨头），但实际上用户确实会给骨架物体本身（Object Level）做动画。

## 2. 修复计划

### 修复问题 1 (对象锁死)
虽然代码看起来有 `PASS_THROUGH`，但在新建场景下“锁死”可能与数据初始化有关。
更关键的是，我们需要确保 Modal Operator 不会无意中干扰 Blender 的变换操作状态。
我们将优化 `modal` 函数，确保在没有拖拽操作时，尽可能减少对事件流的干扰。

### 修复问题 2 (骨架物体模式交互)
我们需要修改那段“透传”逻辑。
**新逻辑**:
1.  如果是骨架物体且在 OBJECT 模式：
    *   **首先** 尝试检测鼠标是否悬停在运动路径的点/手柄上。
    *   **如果命中**: 拦截事件，允许编辑路径（修复了无法交互的问题）。
    *   **如果未命中**: 返回 `PASS_THROUGH`，允许用户选择/移动骨架物体本身（保留了之前的优化）。

### 实施步骤

1.  **修改 `MOTIONPATH_DirectManipulation.modal`**:
    *   移除或调整“骨架物体模式直接透传”的硬编码逻辑。
    *   将其改为：先进行点击检测 (`get_motion_path_point_at_mouse` 等)，只有在检测结果为 None 时，才对骨架物体模式进行特殊放行（或者直接依赖底部的通用 `PASS_THROUGH`，因为通用的 `PASS_THROUGH` 已经足够处理“未命中则放行”的情况）。

2.  **验证逻辑**:
    *   普通物体：点击路径 -> 编辑；点击空白/物体 -> 选中/移动。
    *   骨架（Pose Mode）：点击路径 -> 编辑；点击骨头 -> 选中。
    *   骨架（Object Mode）：点击路径 -> 编辑（**本次修复目标**）；点击骨架 -> 选中/移动。

## 3. 预期结果
*   用户可以正常移动新建的对象，不会被插件卡住。
*   用户可以在物体模式下编辑骨架的运动路径，同时在不点击路径时也能正常操作骨架物体。
