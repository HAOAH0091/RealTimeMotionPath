# 修复运动路径偏移与交互问题计划

## 问题分析

用户反馈骨骼模式下的运动路径完全偏移，手柄不相切，且交互失效。

经过分析，这是由于我们上一轮修改了 `get_current_parent_matrix` 实现了统一的父级矩阵计算逻辑（$M_{parent} = M_{final} \times M_{local}^{-1}$），但**没有更新数据源（缓存）的坐标空间**。

### 根本原因：坐标空间不匹配

1.  **绘制逻辑（Drawing Logic）**：
    -   现在的 `parent_matrix` 是将 **局部基空间（Basis Space）** 转换到 **世界空间（World Space）** 的矩阵。
    -   这意味着它期望输入的点坐标是在 **局部基空间**（即 F-Curve 直接驱动的空间，如 `bone.location`）。

2.  **数据源（Data Source）**：
    -   目前的 `build_position_cache` 函数中，骨骼的位置是取自 `bone.head`。
    -   `bone.head` 是 **骨架物体空间（Armature Object Space）** 的坐标。
    -   物体的位置是取自 `obj.matrix_local.translation`，这是 **父级相对空间（Parent Relative Space）** 的坐标（包含 `ParentInverse`）。

3.  **后果**：
    -   绘制时，代码执行了 `parent_matrix @ point`。
    -   实际上变成了 `(World @ Bone @ Basis^-1) @ (Bone @ Origin)`。
    -   这相当于把已经包含骨骼变换的点，再次叠加了除 Basis 外的骨骼变换，导致位置严重偏移（双重变换）。
    -   由于位置不对，显示的手柄自然也不切于显示的路径（因为路径本身就是错的）。
    -   交互时，虽然计算逻辑是对的，但因为视觉反馈是错的，用户感觉到"不跟随鼠标"。

## 解决方案

必须确保**缓存的数据（点坐标）**与**绘制矩阵的期望输入（局部基空间）**一致。

我们需要修改 `build_position_cache` 函数，使其存储 **局部基空间** 的坐标。

### 修改细节

1.  **骨骼（Pose Bone）**：
    -   **旧代码**：`pos = bone.head.copy()` （物体空间）
    -   **新代码**：`pos = bone.matrix_basis.translation.copy()` 或 `pos = bone.location.copy()` （局部基空间）
    -   **理由**：F-Curve 驱动的是 `location`，即 `matrix_basis` 的平移分量。

2.  **物体（Object）**：
    -   **旧代码**：`pos = obj.matrix_local.translation.copy()` （含 ParentInverse）
    -   **新代码**：`pos = obj.matrix_basis.translation.copy()` 或 `pos = obj.location.copy()` （局部基空间）
    -   **理由**：与统一后的 `parent_matrix` 逻辑（已包含 ParentInverse 处理）匹配。

3.  **路径线（Path Line）**：
    -   同样需要更新密集路径点的采集逻辑，使用 `target_bone.location` 代替 `target_bone.head`。

## 验证逻辑

-   **公式验证**：
    -   `World_Pos` = `Parent_Matrix` @ `Local_Pos`
    -   `Parent_Matrix` = `World_Final` @ `Basis^-1`
    -   `Local_Pos` = `Basis.translation` = `Basis @ (0,0,0)` (忽略旋转缩放对原点的影响)
    -   `World_Pos` = `World_Final` @ `Basis^-1` @ `Basis` @ `(0,0,0)`
    -   `World_Pos` = `World_Final` @ `(0,0,0)`
    -   `World_Pos` = `Object_World_Location`
    -   **结论**：正确。路径点将准确绘制在物体/骨骼的当前世界位置上。

## 实施计划

1.  修改 `c:\Users\Windows\AppData\Roaming\Blender Foundation\Blender\5.0\extensions\user_default\Motion_Path_Pro\__init__.py`。
2.  更新 `build_position_cache` 中的骨骼和物体位置获取逻辑。
3.  更新绘制路径线（dense path）部分的逻辑。

该修复将彻底解决偏移问题，并使交互恢复正常。
