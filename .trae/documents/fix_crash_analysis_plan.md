# 崩溃日志分析与修复计划

## 问题分析

用户提供的崩溃日志 (`blender.crash.txt`) 显示 Blender 发生了 `EXCEPTION_ACCESS_VIOLATION (0xc0000005)` 错误。这是一个内存访问违规错误，通常发生在 C/C++ 层面的代码中，尤其是在与 GPU 交互时。

### 关键信息
- **错误代码**: `EXCEPTION_ACCESS_VIOLATION` (空指针或非法内存访问)。
- **Python 回溯**:
  ```python
  File "...\__init__.py", line 197 in draw_batched_billboard_circles
  File "...\__init__.py", line 395 in draw_motion_path_overlay
  ```
- **堆栈跟踪**: 涉及 `blender::gpu::VKDevice::submission_runner` 和 `OpenImageIO` 等线程，但主线程似乎在处理异常。崩溃发生在绘图调用期间。

### 代码审查
在 `__init__.py` 中，`draw_motion_path_overlay` 函数负责绘制运动路径的线条和关键帧点。

1.  **路径线条绘制 (Lines 390-399)**:
    ```python
    world_points = [parent_matrix @ v for v in _state.path_vertices]
    # ...
    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": world_points})
    # ...
    batch.draw(shader)
    ```
    **潜在问题**: 这里直接使用了 `world_points` 创建 GPU Batch 并进行绘制，**没有检查坐标的有效性**（是否包含 NaN 或 Inf）。如果 `parent_matrix` 或 `path_vertices` 包含无效数据，传给 GPU 可能会导致驱动程序崩溃。

2.  **关键帧点绘制 (Line 403 -> draw_batched_billboard_circles)**:
    调用了 `draw_batched_billboard_circles`。虽然该函数内部有 `math.isfinite` 检查 (Line 172)，但如果 `LINE_STRIP` 绘制（在它之前执行）已经导致了 GPU 状态异常或崩溃，那么回溯可能会指向附近的代码。此外，崩溃日志中的行号可能略有偏移，或者是指向了 Python 栈帧中最后执行的位置。

### 结论
崩溃最可能的原因是 **向 GPU 传递了无效的 3D 坐标 (NaN 或 Infinity)**。这通常发生在对象矩阵异常、约束计算错误或未初始化的数据中。当 `batch.draw()` 尝试渲染这些无效坐标时，底层图形驱动（Vulkan/OpenGL）发生了崩溃。

## 修复计划

### 1. 增强数据验证
在将数据传递给 GPU 之前，必须确保所有坐标都是有限数值。

-   **修改 `draw_motion_path_overlay`**:
    -   在计算 `world_points` 后，立即过滤掉包含 NaN 或 Inf 的点。
    -   如果过滤后的点数量不足以绘制（< 2），则跳过绘制。

### 2. 优化 `draw_batched_billboard_circles`
-   虽然该函数已有验证逻辑，但可以进一步加强，确保在 `batch_for_shader` 创建前数据绝对安全。

### 3. 安全的 Context 获取（次要）
-   虽然崩溃主要指向 GPU 数据问题，但在 Draw Handler 中使用 `bpy.context` 也可能存在风险。我们将保持现有的 `if not context.space_data...` 检查，这在目前看来是足够的。

## 验证步骤
1.  修改代码添加验证逻辑。
2.  模拟无效坐标数据（如果可能）或在正常使用中进行压力测试（大幅度移动、缩放对象）。
3.  确认插件不再导致 Blender 崩溃。
