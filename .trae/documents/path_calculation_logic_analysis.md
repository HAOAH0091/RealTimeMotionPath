# 路径计算逻辑分析 (Fast Path vs Slow Path)

## 1. 核心区分逻辑

插件目前的路径计算分为两种模式：**Fast Path（快速路径）** 和 **Slow Path（慢速路径）**。

### 判断依据
主要依据是**物体的复杂性**（是否存在约束或驱动）以及**当前模式**（Object vs Pose）。

| 模式 | 条件 | 路径类型 | 备注 |
| :--- | :--- | :--- | :--- |
| **Object Mode** | 无约束 且 无位置驱动 | **Fast Path** | 纯数学计算，极快 |
| **Object Mode** | 有约束 或 有位置驱动 | **Slow Path** | 切换帧计算，较慢 |
| **Pose Mode** | 任意情况 | **Slow Path** | **骨骼目前强制使用慢速路径** |

---

## 2. 详细实现分析

### 2.1 Fast Path (快速路径)
*   **适用场景**: 仅限 Object Mode 下的简单物体（无约束/驱动）。
*   **实现原理**: 
    *   直接读取 F-Curve 数据，使用 `fcurve.evaluate(frame)` 获取每一帧的数值。
    *   结合 `obj.delta_location` 计算最终位置。
    *   完全绕过 `scene.frame_set()` 和 `view_layer.update()`，性能极高。
*   **代码位置**: `__init__.py` 中的 `calculate_path_from_fcurves` 函数。

### 2.2 Slow Path (慢速路径)
*   **适用场景**: 
    *   所有 Pose Mode 下的骨骼（PoseBone）。
    *   Object Mode 下带有约束（Constraints）或位置驱动（Drivers）的物体。
*   **实现原理**: 
    *   使用 `context.scene.frame_set(frame)` 切换时间轴。
    *   调用 `view_layer.update()` 强制更新场景依赖图。
    *   直接读取物体/骨骼在当前帧的最终世界坐标（`matrix_world` 或 `matrix_channel`）。
    *   保证了视觉上的绝对准确性，但性能开销大。
*   **代码位置**: `__init__.py` 中的 `build_position_cache` 函数。

---

## 3. 代码审计确认 (2026-02-24)

经过对 `__init__.py` (Line 402-428) 的再次详细审计，确认 **Pose Mode 确实是全部强制使用 Slow Path**。

具体证据：
1.  在 `build_position_cache` 函数中，检测到 `obj.mode == 'POSE'` 后，直接进入 `frame_set` 循环。
2.  代码中不存在任何针对 PoseBone 的 Fast Path 分支逻辑。
3.  `calculate_path_from_fcurves` 函数目前不支持传入 `bone_name`，无法用于骨骼计算。

这意味着即使是一个没有任何约束的简单骨骼，插件也会逐帧切换场景来计算路径，这在大场景中会造成显著的性能瓶颈。

## 4. 优化建议

建议为骨骼实现 Fast Path，逻辑如下：
1.  检查骨骼是否有约束（`pose_bone.constraints`）。
2.  检查骨骼是否有位置驱动。
3.  如果都没有，使用修改后的 `calculate_path_from_fcurves`（支持骨骼）进行计算。
4.  计算时需注意坐标系转换：F-Curve 数据是相对于父级骨骼的（Pose Space），需要乘以父级矩阵才能得到世界坐标。
