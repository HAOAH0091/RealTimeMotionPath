# Tasks

- [ ] Task 1: UI 重构与简化
  - [ ] SubTask 1.1: 创建一个新的 UI 面板类（或修改现有 `AutoMOTIONPATHSPanel`），仅保留核心开关“启用自定义路径线”。
  - [ ] SubTask 1.2: 将该开关放置在动画相关面板下方的控制台/时间线区域（参考用户图示位置）。
  - [ ] SubTask 1.3: 移除旧版复杂的“Calculate”, “Update”, “Clear”等原生 Motion Path 操作按钮。

- [ ] Task 2: 数据层增强与采样优化
  - [ ] SubTask 2.1: 修改 `build_position_cache` 函数，确保它能按帧（步长=1）生成完整的世界空间位置列表，不仅限于关键帧。
  - [ ] SubTask 2.2: 在 `MotionPathState` 中添加用于存储路径线顶点数据（`path_vertices`）的结构。
  - [ ] SubTask 2.3: 实现基于 `path_vertices` 生成 GPU Batch 的逻辑（`path_batch`），并在缓存更新时同步更新。

- [ ] Task 3: 绘制层实现
  - [ ] SubTask 3.1: 在 `draw_motion_path_overlay` 函数中，添加绘制路径线 Batch 的逻辑。
  - [ ] SubTask 3.2: 使用 `gpu.shader.from_builtin('UNIFORM_COLOR')` 或 `SMOOTH_COLOR` 设置线条颜色和样式。
  - [ ] SubTask 3.3: 确保路径线绘制在关键帧点和手柄之下（或之上，视需求而定），并处理好深度测试（如果需要）。

- [ ] Task 4: 交互与实时更新
  - [ ] SubTask 4.1: 在 `MOTIONPATH_DirectManipulation` 的拖拽结束逻辑中，确保触发 `build_position_cache` 和 `path_batch` 的重建。
  - [ ] SubTask 4.2: 验证拖拽手柄时，路径线是否实时跟随变化（如果不实时，需在拖拽过程中每帧更新部分数据）。
  - [ ] SubTask 4.3: 处理好选中/未选中对象的路径线显示逻辑（如仅显示选中对象，或不同颜色）。

- [ ] Task 5: 清理与优化
  - [ ] SubTask 5.1: 移除 `__init__.py` 中所有调用 `bpy.ops.object.paths_*` 和 `bpy.ops.pose.paths_*` 的代码。
  - [ ] SubTask 5.2: 清理不再使用的 Operator 类（如 `FRO_OT_Delet_Path_*` 等）。
  - [ ] SubTask 5.3: 确保存档/读档后路径线能正确恢复显示（如果需要持久化状态，虽然目前是运行时缓存）。

# Task Dependencies
- [Task 3] depends on [Task 2] (绘制依赖数据)
- [Task 4] depends on [Task 3] (交互验证绘制)
- [Task 5] depends on [Task 1] (清理依赖 UI 移除)
