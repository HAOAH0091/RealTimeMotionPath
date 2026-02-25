# Motion Path Pro 父子级关系修正计划

## 1. 问题分析

用户反馈：当应用对象存在父级时，运动路径显示位置错误（显示到了父级所在的坐标附近）。

**根本原因分析**：
当前插件的快速路径计算（Fast Path）和绘制逻辑简化了 Blender 的坐标变换链，缺失了两个关键环节：

1.  **父级逆矩阵 (Parent Inverse Matrix)**：
    *   在 Blender 中，当建立父子关系（特别是使用 "Keep Transform"）时，为了保持子物体在世界空间的位置不变，Blender 会计算一个 `matrix_parent_inverse`。
    *   子物体的世界坐标计算公式为：
        $$ P_{world} = M_{parent\_world} \times M_{parent\_inverse} \times P_{local} $$
    *   **当前逻辑**：只计算了 $P_{world} = M_{parent\_world} \times P_{local}$。这导致子物体的位置被错误地变换，看起来就像是相对于父级原点的偏移，没有考虑建立父子关系时的初始相对位置。

2.  **增量变换 (Delta Transforms)**：
    *   F-Curve 只驱动基础的 `Location` 属性。
    *   Blender 允许设置 `Delta Location`，这是叠加在基础 Location 之上的。
    *   **当前逻辑**：只读取了 F-Curve，忽略了 `Delta Location`，导致路径位置偏差。

## 2. 修正方案

### 2.1 修正父级矩阵获取逻辑 (`get_current_parent_matrix`)
我们需要在获取父级矩阵时，将对象的 `matrix_parent_inverse` 考虑进去。

**修改目标**：
在 `get_current_parent_matrix` 函数中，当处理 Object 模式且存在父级时：
*   **旧逻辑**：`return obj.parent.matrix_world`
*   **新逻辑**：`return obj.parent.matrix_world @ obj.matrix_parent_inverse`

**注意**：对于骨骼（Pose Bone），其父级矩阵通常就是 Armature 对象的 `matrix_world`，且骨骼的位置通常是在对象空间（Object Space）定义的，不需要应用 `matrix_parent_inverse`（或者是已经包含在骨骼层级计算中了）。因此，此修改**仅针对 Object 模式**。

### 2.2 修正局部坐标计算逻辑 (`calculate_path_from_fcurves`)
我们需要确保计算出的局部坐标包含了所有的静态偏移。

**修改目标**：
在 `calculate_path_from_fcurves` 函数中：
*   获取 `obj.delta_location`。
*   在返回最终坐标前，将 `delta_location` 加到 F-Curve 计算出的位置上。
*   公式：`Final_Local_Pos = F_Curve_Value + Delta_Location`

## 3. 验证推演

假设场景：
*   父物体 P 在 (10, 0, 0)。
*   子物体 C 在 (12, 0, 0)。
*   建立父子关系 (Keep Transform)。
    *   `P.matrix_world` = Translation(10, 0, 0)
    *   `C.matrix_parent_inverse` = Translation(-10, 0, 0) (P 的逆)
    *   `C.location` = (2, 0, 0) (相对于 P 的 Local)
    *   或者 `C.location` = (12, 0, 0) 且 `ParentInverse` Identity?
    *   通常 Keep Transform 会让 `C.location` 保持 (12, 0, 0) 吗？不，Local Location 应该变。
    *   **标准情况**：`C.location` 变为 (0, 0, 0) 如果原点重合，或者保持其相对于世界原点的数值？
    *   让我们用公式验证：
        $P_{world} = P_{parent} @ P_{inverse} @ P_{local}$
        $(12) = (10) @ (-10) @ (12)$ -> $12 = 10 - 10 + 12$。成立。

**修正后的绘制流程**：
1.  `calculate_path` 返回 `P_{local}` (例如 12, 0, 0)。
2.  `get_parent_matrix` 返回 `P_{parent} @ P_{inverse}` (即 10 + (-10) = Identity，或者包含旋转的组合矩阵)。
3.  `Draw` 计算 `(P_{parent} @ P_{inverse}) @ P_{local}`。
4.  结果正确还原为世界坐标。

## 4. 实施步骤

1.  编辑 `__init__.py`，修改 `get_current_parent_matrix` 函数。
2.  编辑 `__init__.py`，修改 `calculate_path_from_fcurves` 函数。
