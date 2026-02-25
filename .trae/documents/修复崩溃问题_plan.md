# 修复 Motion Path 崩溃问题计划

## 问题分析

用户反馈在骨骼模式测试时发生了崩溃 (`EXCEPTION_ACCESS_VIOLATION`)。崩溃发生在 `draw_batched_billboard_circles` 函数中。虽然具体崩溃点指向了 Python 循环，但这通常意味着底层 GPU 驱动或 `gpu` 模块在处理数据时遇到了非法状态（如无效内存访问、NaN/Inf 值漏网、或数据类型不匹配）。

### 潜在原因

1.  **数据类型不匹配**：`gpu.shader.uniform_float` 对传入的数据类型比较敏感。尽管它支持 Vector，但在某些情况下（尤其是多线程环境或特定驱动下），显式转换为 tuple of floats 更安全。
2.  **GPU 批处理数据异常**：虽然我们有 `math.isfinite` 检查，但在极少数情况下，数据结构可能为空或索引越界（尽管代码逻辑看起来正确）。
3.  **上下文 (Context) 问题**：`get_pixel_scale` 依赖 `context.region` 和 `context.space_data.region_3d`。如果在绘制回调执行时上下文不匹配（例如鼠标在 Header 上），坐标转换可能返回异常值。

## 解决方案

我们将采取防御性编程策略来增强绘制代码的鲁棒性：

1.  **增强 `draw_batched_billboard_circles` 的安全性**：
    -   增加对 `segments` 和 `radius` 的有效性检查。
    -   在调用 `batch_for_shader` 前，确保 `all_vertices` 和 `all_indices` 不为空且结构正确。
    -   扩大 `try-except` 范围，捕获更多潜在的 Python 异常，防止它们传递到底层。

2.  **显式类型转换**：
    -   在 `draw_motion_path_overlay` 中，将颜色（Vector）显式转换为 Python `tuple` (floats)，确保传递给 Shader 的数据是纯粹的基础类型。

3.  **上下文检查**：
    -   在 `get_pixel_scale` 中增加对 `co2d` 和 `co2d_offset` 的额外检查。

## 实施计划

1.  修改 `c:\Users\Windows\AppData\Roaming\Blender Foundation\Blender\5.0\extensions\user_default\Motion_Path_Pro\__init__.py`。
2.  更新 `draw_batched_billboard_circles` 函数。
3.  更新 `draw_motion_path_overlay` 函数中的颜色传递。

## 预期结果

通过这些修改，即使在边缘情况下（如数据无效或上下文异常），插件也应能避免硬崩溃，改为跳过绘制或捕获异常。
