# Motion Path Pro 性能优化方案

## 1. 性能瓶颈分析

经过代码审查，当前插件存在以下主要的性能瓶颈：

### 1.1 CPU 计算瓶颈 (`build_position_cache`)
- **全场景重算**：在 `build_position_cache` 函数中，插件通过循环调用 `context.scene.frame_set(frame)` 来获取每一帧的物体位置。
- **高昂代价**：`frame_set` 会触发 Blender 完整的场景依赖图（Dependency Graph）更新。
- **父级关系分析**：当前插件的绘制逻辑其实是**基于局部空间（Local Space）**计算路径，然后乘以**当前帧**的父级矩阵进行显示。这意味着路径的形状并不依赖于父级在每一帧的历史位置，而只依赖于对象自身的 F-Curve 数据。
- **结论**：既然路径形状是相对于父级的，我们**完全不需要**为了获取父级的历史位置而调用 `frame_set`。

### 1.2 GPU 绘制瓶颈 (`draw_motion_path_overlay`)
- **绘制调用过多**：`draw_billboard_circle` 为每个点创建独立 Batch，导致数百次 Draw Call。
- **重复计算**：绘制循环中包含大量 Python 运算。

## 2. 优化策略

### 2.1 核心计算优化 (CPU) - 全面采用快速路径
**基于 F-Curve 的直接求值 (Direct F-Curve Evaluation)**：
- **原理**：利用 `fcurve.evaluate(frame)` 直接获取每一帧的局部位置 (Location)。
- **适用性**：
    - **物体模式 (Object Mode)**：即使物体有父级，`fcurve.evaluate` 获取的正是相对于父级的局部坐标。这完全符合当前插件“显示局部路径”的逻辑。因此，**无论是否有父级，都可以使用快速路径**。
    - **例外情况**：如果物体有复杂的**约束 (Constraints)** 或 **驱动 (Drivers)** 修改了最终位置，`fcurve.evaluate` 可能只显示 F-Curve 的原始路径。我们将保留一个选项或自动检测机制（如检测约束），在必要时回退到 `frame_set`。
    - **骨骼模式 (Pose Mode)**：骨骼的 `head` 坐标通常是骨架空间 (Armature Space) 的。如果骨骼有父骨骼，`evaluate` 得到的是相对于父骨骼的。我们需要递归计算父骨骼的变换，或者在骨骼模式下暂时保留 `frame_set`（除非是根骨骼）。

### 2.2 渲染优化 (GPU)
**批量绘制 (Batch Rendering)**：
- **合并批次**：将所有点、线合并为 3-4 个大的 Batch（路径线、手柄线、关键帧点、手柄端点）。
- **预计算几何**：使用 `gpu.shader.from_builtin('UNIFORM_COLOR')` 配合 `GL_POINTS` 或预生成的圆面片，一次性提交。

### 2.3 交互优化
- **实时反馈**：拖拽时不再触发任何 `frame_set`。直接修改 F-Curve 数据后，更新内存中的路径缓存，并触发重绘。

## 3. 实施计划

### 第一阶段：重构核心计算 (CPU 优化)
1.  **实现 `calculate_path_from_fcurves` 函数**：
    - 输入：Object, Action, Frame Range。
    - 逻辑：遍历 Location F-Curves，使用 `evaluate` 获取每一帧的 (X, Y, Z)。
    - 输出：局部坐标列表。
2.  **集成到 `build_position_cache`**：
    - 对于 **Object Mode**：默认使用新函数。
    - 添加检测逻辑：如果 `obj.constraints` 非空，则回退到 `frame_set`（或提供用户开关）。
    - 对于 **Pose Mode**：暂时保持 `frame_set`，或仅对无父级骨骼优化。

### 第二阶段：重构绘制系统 (GPU 优化)
1.  **创建 `BatchCollector`**：用于收集顶点和颜色数据。
2.  **重写 `draw_motion_path_overlay`**：
    - 移除循环中的 `draw_billboard_circle`。
    - 使用 `batch_for_shader` 统一绘制所有点和线。

### 第三阶段：验证
1.  **父级动画测试**：验证在父物体移动/旋转时，子物体的路径显示是否正确（应跟随父物体移动，但形状不变）。
2.  **性能测试**：对比拖拽时的 FPS。

## 4. 预期效果
- **全场景适用**：即使在深层父子级层级中，只要没有复杂约束，都能获得 100倍+ 的计算性能提升。
- **极速交互**：拖拽手柄将变得丝般顺滑。
