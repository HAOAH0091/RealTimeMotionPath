# Blender 崩溃原因分析与修复计划

## 1. 崩溃日志分析
- **崩溃类型**: `EXCEPTION_ACCESS_VIOLATION (0xc0000005)`
- **崩溃位置**: `blender.exe` 内部，由 Python 脚本调用触发。
- **Python 堆栈追踪**:
  ```
  File "...\__init__.py", line 289 in draw_batched_billboard_circles
  File "...\__init__.py", line 715 in draw_motion_path_overlay
  ```
- **场景**: 用户在 Pose Mode 下交互骨骼运动路径手柄。

## 2. 问题根源分析
崩溃发生在 `draw_batched_billboard_circles` 函数中，这是用于绘制路径点和手柄端点的函数。
虽然代码中已经包含了一些 `math.isfinite` 检查，但在 Pose Mode 下，骨骼的矩阵运算（特别是涉及父级变换和约束时）极易产生 `NaN` (Not a Number) 或 `Inf` (无穷大) 数据。

具体可能的原因：
1.  **无效的骨骼矩阵**: 在 `get_current_parent_matrix` 中，如果骨骼缩放为 0 或存在退化的约束，矩阵求逆可能产生无效值。
2.  **手柄坐标计算溢出**: 在 `draw_motion_path_handles` 中，`handle_left_pos` 和 `handle_right_pos` 的计算依赖于 `parent_matrix` 和 `global_scale`。如果这些值为无效值，计算出的坐标也会是无效的。
3.  **GPU 数据污染**: 尽管 `draw_batched_billboard_circles` 内部有检查，但如果 `batch_for_shader` 接收到了包含 `NaN` 的数据（即使是颜色或法线），或者在某些边缘情况下检查被绕过，会导致 GPU 驱动程序崩溃。

## 3. 修复方案

我们将采取**多层防御**策略，从数据源头到最终绘制全方位拦截无效数据。

### 步骤 1: 强化矩阵计算的安全性
- **位置**: `get_current_parent_matrix`
- **操作**: 在返回矩阵前，检查矩阵的所有元素是否为有限值 (`isfinite`)。如果矩阵无效，回退到单位矩阵，防止无效数据向下游传播。

### 步骤 2: 强化手柄计算的验证
- **位置**: `draw_motion_path_handles`
- **操作**: 在计算出 `handle_left_pos` 和 `handle_right_pos` 后，立即检查坐标的有效性。如果是 `NaN` 或 `Inf`，则**不**将其添加到绘制收集器 (`collector`) 中。这能从源头上切断无效数据的产生。

### 步骤 3: 优化绘制函数的防御机制
- **位置**: `draw_batched_billboard_circles`
- **操作**: 
    - 增加对 `rx`, `ry`, `rz` (视口基向量) 的有效性检查。
    - 增加对 `scale` (像素缩放比) 的有效性检查。
    - 确保传给 GPU 的颜色值也是有效的。

### 步骤 4: 验证修复
- 在 Pose Mode 下模拟各种极端情况（如缩放为 0，父级极其遥远），确保不再崩溃。

## 4. 任务列表
- [ ] 修改 `get_current_parent_matrix` 添加矩阵有效性检查。
- [ ] 修改 `draw_motion_path_handles` 添加手柄坐标有效性检查。
- [ ] 修改 `draw_batched_billboard_circles` 增强异常捕获和数据验证。
- [ ] 验证修复是否解决了崩溃问题。
