# 骨骼 Fast Path 实现方案评估

## 1. 目标
为 Blender 插件实现针对骨骼（PoseBone）的 **Fast Path**（快速路径计算），以解决当前强制使用 Slow Path（全场景逐帧更新）导致的性能问题。

## 2. 核心原理
与 Object Fast Path 类似，Bone Fast Path 的核心在于**绕过 Blender 的依赖图更新**，直接通过数学公式计算骨骼在不同帧的位置。

**基本公式**:
$$ P_{world}(t) = M_{parent\_current} \times P_{local\_evaluated}(t) $$

*   $P_{local\_evaluated}(t)$: 通过 F-Curve 直接求值得到的局部坐标。
*   $M_{parent\_current}$: **当前帧**下，从“F-Curve 空间”到“世界空间”的转换矩阵。

**注意**: 这种方法计算的是“在当前父级姿态下，子骨骼的运动轨迹”。如果父骨骼本身有动画，Fast Path 画出的轨迹在世界空间中可能不完全准确（它不会随父级动画变形，而是作为一个整体随父级移动），但这通常符合动画师调整局部动作的需求。

## 3. 具体实现步骤

### 3.1 修改 `calculate_path_from_fcurves`
扩展此函数以支持骨骼数据提取。

*   **参数**: 增加 `bone_name` 参数（默认为 `None`）。
*   **F-Curve 过滤**: 使用 `is_location_fcurve(fc, bone_name)` 过滤出目标骨骼的曲线。
*   **默认值获取**:
    *   如果 `bone_name` 存在，使用 `obj.pose.bones[bone_name].location` 作为默认值。
    *   骨骼通常没有 `delta_location`，需忽略。
*   **返回值**: 返回局部空间坐标字典。

### 3.2 在 `build_position_cache` 中增加逻辑分支
在处理 `obj.mode == 'POSE'` 时，增加 Fast Path 判断：

1.  **约束检查**: `if pose_bone.constraints:` -> 强制 Slow Path。
2.  **驱动检查**: 检查是否有驱动该骨骼 Location 的 Driver -> 有则 Slow Path。
3.  **父级检查 (可选)**: 如果追求绝对世界坐标准确性，需检查父级是否有动画。但为了性能，通常忽略此项（与 Object Fast Path 保持一致）。

### 3.3 绘制时的矩阵变换
在 `draw_enhanced_bone_path` 中，需要正确计算变换矩阵。

*   对于骨骼，F-Curve 驱动的是 **Local Basis Matrix**。
*   变换矩阵 $M$ 应为：
    ```python
    # 将局部 F-Curve 坐标转换到世界空间的矩阵
    parent_matrix = obj.matrix_world @ bone.matrix @ bone.matrix_basis.inverted()
    ```
    或者直接利用现有的 `get_current_parent_matrix` 函数（它已经处理了这部分逻辑）。

## 4. 潜在风险与注意事项 (Gotchas)

### 4.1 坐标空间混淆
*   **问题**: 骨骼的 `location` 属性是相对于谁的？
*   **解答**: `pose_bone.location` 是相对于其父骨骼（或 Armature 原点）的局部位移。它直接对应 `matrix_basis` 的位移分量。必须确保 F-Curve 的值直接映射到这个属性。

### 4.2 约束 (Constraints)
*   **风险**: IK（反向动力学）、Copy Location 等约束会完全覆盖或修改 F-Curve 的结果。
*   **对策**: 只要骨骼有**任何**启用的约束，必须强制回退到 Slow Path。Fast Path 无法模拟约束求解器。

### 4.3 驱动器 (Drivers)
*   **风险**: 驱动器可以用复杂的 Python 表达式控制位置。
*   **对策**: 检查 `obj.animation_data.drivers`，如果发现目标骨骼的 location 被驱动，强制 Slow Path。

### 4.4 继承变换 (Inherit Transform)
*   **风险**: 骨骼属性 `use_inherit_rotation`, `use_inherit_scale` 等会影响最终矩阵。
*   **分析**: F-Curve 仅仅控制 `matrix_basis`。无论是否继承父级变换，`matrix_basis` 本身的值只由 F-Curve 决定。Fast Path 计算的是 `matrix_basis` 的位移。只要我们的变换矩阵 $M$ 正确地从 `matrix_basis` 变换到 World，这些继承标志应该由 $M$ 自动处理（因为 $M$ 是从当前帧的最终矩阵反推回来的）。

### 4.5 性能预期
*   **Slow Path**: 100 帧动画，FPS 可能降至 10-20（取决于场景复杂度）。
*   **Fast Path**: 同样动画，FPS 应接近实时（60+），因为只涉及简单的数学运算。

## 5. 结论
实现骨骼 Fast Path 是**可行且高收益**的。关键在于严格的条件过滤（无约束、无驱动）以及正确的矩阵空间转换。
