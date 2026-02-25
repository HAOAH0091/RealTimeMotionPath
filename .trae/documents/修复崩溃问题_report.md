# 修复报告：Motion Path 崩溃问题

## 问题根源
经过分析崩溃日志 (`bb3.crash.txt`)，确认崩溃发生在 GPU 绘制阶段 (`draw_batched_billboard_circles` 函数)。
主要原因是在特定情况下（如多线程环境或特定 GPU 驱动），传递给 Shader 的数据可能不符合严格的类型要求（例如 `Vector` 类型未显式转换为基础类型），或者在极端视角下产生的数据导致了底层的 `EXCEPTION_ACCESS_VIOLATION`。

## 已执行的修复

1.  **增强 `draw_batched_billboard_circles` 鲁棒性**：
    -   **显式类型转换**：在传递给 GPU Shader 之前，强制将颜色数据 (`Vector`) 转换为 Python 原生 `tuple`。这消除了潜在的类型兼容性问题。
    -   **异常捕获**：将整个批处理绘制逻辑包裹在 `try-except` 块中。如果某一批次的数据导致计算错误或绘制失败，插件将跳过该批次而不是导致整个 Blender 崩溃。
    -   **有效性检查**：增加了对 `points`（点列表）、`radius`（半径）和 `segments`（段数）的空值和范围检查。

2.  **安全性优化**：
    -   确保 `batch_for_shader` 接收到的所有顶点和索引数据都是结构确定的。
    -   在计算像素比例 (`get_pixel_scale`) 失败时安全退出。

## 验证建议
请在 Blender 中重新加载脚本或重启 Blender，然后再次测试骨骼模式：
1.  切换到 Pose Mode。
2.  选择骨骼并移动/旋转。
3.  观察是否还会出现崩溃。
4.  检查控制台是否有 "Error drawing batch" 的警告信息（如果有，说明插件成功拦截了潜在的崩溃）。
