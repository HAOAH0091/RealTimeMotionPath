# 手柄交互与类型判定机制分析报告（汇总版）

本文档汇总了关于 Motion Path Pro 插件中手柄绘制、类型判定、拖拽交互及异常现象的完整分析与排查计划。

## 1. 核心机制：手柄类型判定来源

**结论**：初始绘制时，手柄的类型完全取决于 F-Curve 关键帧当前的 `handle_type` 属性，插件不会在绘制阶段临时篡改它。

*   **数据来源**：
    *   直接读取 Blender 的 `keyframe.handle_left_type` 和 `handle_right_type`。
    *   绘制函数 `draw_motion_path_handles` 根据这些属性计算贝塞尔曲线的切线方向。
*   **默认值逻辑**：
    *   面板上的 "Handle Type" 选项（默认为 `ALIGNED`）**仅**在点击 "Apply Type" 按钮时生效，作为修改的目标值。
    *   它不会影响未执行 "Apply" 操作的现有关键帧。

**代码位置**：
*   绘制逻辑：[__init__.py:L480](file:///c:/Users/Windows/AppData/Roaming/Blender%20Foundation/Blender/5.0/extensions/user_default/Motion_Path_Pro/__init__.py#L480-L592)
*   命中检测：[__init__.py:L1371](file:///c:/Users/Windows/AppData/Roaming/Blender%20Foundation/Blender/5.0/extensions/user_default/Motion_Path_Pro/__init__.py#L1371-L1469)

---

## 2. 交互流程：点击与拖拽手柄

当用户在 3D 视图中点击并拖动手柄时，插件执行以下标准流程：

1.  **检测命中 (Hit Testing)**
    *   判断鼠标是否在手柄端点（`HANDLE_SELECT_RADIUS` 范围内）。
    *   代码：[__init__.py:L1371](file:///c:/Users/Windows/AppData/Roaming/Blender%20Foundation/Blender/5.0/extensions/user_default/Motion_Path_Pro/__init__.py#L1371-L1469)

2.  **记录初值 (Capture Initial Values)**
    *   记录当前帧、骨骼/对象、被点击侧（左/右）。
    *   **关键动作**：记录拖拽开始前的 `handle_left/right` 坐标作为基准。
    *   代码：[__init__.py:L1340](file:///c:/Users/Windows/AppData/Roaming/Blender%20Foundation/Blender/5.0/extensions/user_default/Motion_Path_Pro/__init__.py#L1340-L1370)

3.  **临时类型转换 (Temporary Type Conversion)**
    *   **VECTOR 类型**：若原为 `VECTOR`，拖拽开始时会临时改为 `FREE`，以便能自由移动，结束后视情况恢复。
    *   **AUTO 类型**：若原为 `AUTO` / `AUTO_CLAMPED`，在单端点拖拽时会强制改为 `ALIGNED`（见下文设计意图）。
    *   代码：[__init__.py:L786](file:///c:/Users/Windows/AppData/Roaming/Blender%20Foundation/Blender/5.0/extensions/user_default/Motion_Path_Pro/__init__.py#L786-L802) (Vector转Free)

4.  **拖拽循环 (Modal Loop)**
    *   计算鼠标位移 -> 转换为世界空间位移 -> 叠加到初值上。
    *   **对侧联动**：根据当前类型更新对侧手柄（如 `ALIGNED` 时镜像移动）。
    *   **关联缺陷**：此处的 `update_opposite_handle` 方法同样存在只计算 Y 轴、遗漏 X 轴的问题（见下文）。
    *   代码：[__init__.py:L1246](file:///c:/Users/Windows/AppData/Roaming/Blender%20Foundation/Blender/5.0/extensions/user_default/Motion_Path_Pro/__init__.py#L1246-L1319)

5.  **结束 (Finish)**
    *   松开鼠标，提交修改（Undo Push）。

---

## 3. 问题分析 A：拖拽起始瞬间跳变

**现象**：点击手柄开始拖拽的瞬间，手柄位置发生突变（跳动）。

**根因分析**：
1.  **“先改类型”导致的位置重算**：
    *   对于 `AUTO` / `AUTO_CLAMPED` 手柄，代码在拖拽第一帧将其强制设为 `ALIGNED`。
    *   Blender 内部机制会立即根据 `ALIGNED` 规则重算手柄位置（通常是拉直）。
2.  **基准值与当前值不匹配**：
    *   插件记录的“初值”是改类型 *之前* 的坐标。
    *   计算位移时使用 `初值 + 鼠标偏移`。
    *   但如果类型改变导致手柄被系统“瞬移”，`初值` 就失效了，导致计算结果偏差。
3.  **联动计算缺陷叠加**：
    *   拖拽第一帧即调用 `update_opposite_handle`，该函数因缺失 X 轴计算，可能将对侧手柄瞬间拉到错误位置（X轴不镜像），加剧视觉跳变。

**验证方法**：
*   暂时注释掉 `move_handle_point` 中将 `AUTO` 转为 `ALIGNED` 的代码，观察跳变是否消失。

---

## 4. 设计意图：为什么要把 AUTO 改为 ALIGNED？

**背景**：
*   `AUTO`（自动）手柄由 Blender 自动计算平滑度。
*   用户意图：当用户手动拖拽一个手柄时，通常希望打破“自动计算”，获得手动控制权，同时保持曲线平滑（即左右手柄共线）。

**原因**：
*   如果保持 `AUTO`，用户拖拽时 Blender 可能会不断抗拒用户的修改，试图“自动归位”。
*   改为 `ALIGNED`（对齐）是让用户能手动控制方向，同时强制对侧手柄跟随旋转，保持切线平滑。

**副作用**：
*   即上述的“起始跳变”问题。

---

## 5. 问题分析 B：Apply Type 导致手柄“越点越平”与 AUTO 转跳变

**现象 1**：
*   多次点击面板上的 "Apply Type" (设为 Aligned)，手柄位置不断变化，最终趋于水平。

**现象 2**：
*   拖拽手柄时，对侧手柄的联动行为也表现出类似的异常。

**根因分析 (Code Review)**：
*   **同源缺陷**：
    *   **Apply Type** 使用了 `set_handle_type` 函数。
    *   **拖拽联动** 使用了 `update_opposite_handle` 函数。
    *   **这两个函数使用了完全相同的缺陷逻辑**：
        ```python
        # 伪代码逻辑
        if handle_type == 'ALIGNED':
            left_direction_y = co.y - handle_left.y
            handle_right.y = co.y + left_direction_y  # 只设置了 Y 轴！漏了 X 轴！
        ```
*   **后果**：
    1.  **不完整的镜像**：仅镜像 Y 轴会导致左右手柄斜率不一致。
    2.  **Blender 的纠正机制**：`ALIGNED` 类型要求共线。代码强制设置了错误的 Y 值后，Blender 随后介入修正斜率。
    3.  **迭代误差**：这种循环导致数值迭代收敛（通常变短、变平）。

**代码位置**：
*   `set_handle_type`: [__init__.py:L1559-L1561](file:///c:/Users/Windows/AppData/Roaming/Blender%20Foundation/Blender/5.0/extensions/user_default/Motion_Path_Pro/__init__.py#L1559-L1561)
*   `update_opposite_handle`: [__init__.py:L1236-L1244](file:///c:/Users/Windows/AppData/Roaming/Blender%20Foundation/Blender/5.0/extensions/user_default/Motion_Path_Pro/__init__.py#L1236-L1244)

---

## 6. 修复与改进计划

### 核心修复：统一修正 ALIGNED 镜像逻辑
*   **目标**：确保 `set_handle_type` 和 `update_opposite_handle` 都执行完整的 2D 向量镜像（同时处理 X 和 Y）。
*   **逻辑修正**：
    ```python
    # 修正后的逻辑示例
    vec_left = co - handle_left  # 2D 向量 (Frame, Value)
    handle_right = co + vec_left # 完全中心对称镜像
    ```
    *建议提取为公共 helper 函数 `mirror_handle_vector` 以避免重复代码。*

### 针对“拖拽跳变”的改进
*   **方案 A (最小改动)**：在强制改变类型为 `ALIGNED` *之后*，立即重新捕获一次“初值”和“基准坐标”。
*   **方案 B (体验优化)**：拖拽开始时不立即改类型，而是当鼠标位移超过一定阈值（如 5px）后，再由 `AUTO` 转为 `ALIGNED`，并同步更新基准。

### 针对“拖拽 Vector 手柄”的逻辑
*   目前 Vector 转 Free 的逻辑是合理的，但需确保转类型后的坐标重算不会影响后续位移计算。

---

## 7. 下一步行动
*   **步骤 1**：修复 `set_handle_type` 和 `update_opposite_handle` 中的 X 轴遗漏问题（解决“越点越平”和“联动异常”）。
*   **步骤 2**：优化 `move_handle_point` 中的类型转换逻辑（解决“起始跳变”）。

---

## 8. 进阶优化：解除“强制长度对齐”导致的跳变

**新现象 (用户反馈)**：
*   修复后，Apply Type 或拖拽手柄时，对侧手柄虽然共线了，但长度被强制变成与当前手柄一致，导致了新的“长度跳变”。

**原因分析**：
*   **上一轮修复的副作用**：为了快速解决“越点越平”的斜率问题，我们采用了“完全中心对称镜像”算法：
    ```python
    handle_right = co + (co - handle_left)
    ```
*   **几何含义**：这不仅强制了方向相反（共线），也强制了模长（长度）相等。
*   **Blender 原生行为**：`ALIGNED` 类型只要求方向共线，允许左右手柄长度不同（非对称手柄）。强制对齐长度属于“过度修正”。

**优化方案**：
*   **只对齐方向，保留原长度**。
*   **算法改进**：
    1.  计算当前手柄相对于关键帧点的方向向量（归一化）。
    2.  获取对侧手柄原本的长度（模长）。
    3.  新对侧手柄位置 = 关键帧点 + (反向单位向量 * 对侧原长度)。
*   **例外情况**：如果对侧原本长度极短（接近0），则可能需要赋予一个默认长度或跟随当前长度，防止退化。

**更新后的行动计划**：
*   修改 `set_handle_type` 和 `update_opposite_handle`，从“全等镜像”改为“保留长度的方向对齐”。
