# 崩溃分析与修复计划 (Crash Analysis & Fix Plan)

## 1. 崩溃日志分析 (Re-analysis of bb9.crash.txt)

### 关键发现
*   **崩溃位置**: 依然是 `EXCEPTION_ACCESS_VIOLATION (0xc0000005)`，但这次发生在 `python311.dll` 内部，具体是在 `PyTuple_GetItem` 函数中。
*   **Python 调用栈**: 错误指向 `draw_motion_path_overlay` 函数中的列表推导式/生成器表达式 (Line 716 附近)。
    ```python
    File "...\__init__.py", line 716 in <genexpr>
    File "...\__init__.py", line 716 in <listcomp>
    File "...\__init__.py", line 716 in draw_motion_path_overlay
    ```
    这对应于我们代码中的点位验证逻辑：
    `[p for p in raw_world_points if all(math.isfinite(c) ... for c in p)]`
*   **渲染后端**: 日志中同时出现了 `nvoglv64.dll` (OpenGL) 和 `blender::gpu::VKDevice` (Vulkan)。
    *   这意味着 Blender **确实正在使用 Vulkan 后端** 运行（或者是混合模式）。
    *   崩溃发生在 Python 尝试读取/验证数据时，这表明 `mathutils.Vector` 对象在列表推导式中的迭代可能与 Python 3.11 的内部优化存在冲突，或者数据本身存在某种极其隐晦的内存问题。

## 2. 关于 Vulkan vs OpenGL 的确认

*   **现状**: 您的日志证实 Blender 5.0 正式版在您的环境中启用了 **Vulkan** 后端 (`VKDevice` 线程活动)。
*   **插件机制**: 我们的插件使用的是 Blender 的 `gpu` 模块 (`import gpu`)。这是一个抽象层，理论上它会自动适配 OpenGL、Vulkan 或 Metal。插件本身不直接调用 OpenGL 指令。
*   **问题所在**: 尽管 `gpu` 模块是抽象的，但 Vulkan 后端在 Blender 5.0 中仍处于早期/实验性阶段。日志显示崩溃发生在 Python 层面的数据处理上，这可能意味着在 Vulkan 模式下，Python 对象 (`mathutils.Vector`) 的内存管理或线程安全性变得更加敏感。

## 3. 修复策略

既然崩溃发生在“为了防止崩溃而进行的数据验证”这一行，我们需要将验证逻辑变得**极其基础和显式**，移除所有高级的 Python 语法糖（如列表推导式和生成器），以规避 Python 解释器内部的潜在 Bug 或内存访问冲突。

### 计划步骤

1.  **重构验证逻辑**:
    *   废弃 `[... for ... if all(...)]` 这种复杂的列表推导式。
    *   改为使用最原始的 `for` 循环和显式的 `x, y, z` 访问。
    *   避免在循环中使用迭代器访问 `Vector` 分量，直接通过索引访问。

2.  **强制类型转换**:
    *   在将数据传给 GPU 之前，显式地将 `mathutils.Vector` 转换为纯 Python `tuple`。这虽然会增加一点点 CPU 开销，但能确保传给 `gpu` 模块的数据是绝对“干净”的原生类型，不受底层 C++ 对象生命周期的影响。

3.  **Vulkan 兼容性增强**:
    *   在 Shader 传参时，更加严格地检查数据类型，确保不触发 Vulkan 驱动的边界情况。

## 4. 待执行操作

我们将修改 `__init__.py` 中的 `draw_motion_path_overlay` 函数，采用上述的“笨办法”来保证绝对的安全。

**下一步**: 如果您同意此计划，我将开始编辑代码。
