# 修复手柄拖动跳变问题

## 问题分析

用户反馈在拖动手柄时（特别是父级旋转、子级位移的场景），手柄起始位置会发生跳变。
经分析，原因是**绘制逻辑**与**点击检测逻辑**不一致：

1. **绘制 (`draw_motion_path_handles`)**：已更新为使用 `world_velocity`（世界速度）缓存，确保手柄视觉上与路径相切。
2. **点击检测 (`get_motion_path_handle_at_mouse`)**：仍然使用旧的 `parent_matrix`（父级矩阵）旋转逻辑。

**后果**：用户点击的是“视觉上的新手柄”，但系统捕捉到的起始位置是“隐形的旧手柄”。拖动一开始，位置差值计算就会基于旧位置，导致瞬间跳变。

## 解决方案

更新 `get_motion_path_handle_at_mouse` 函数，使其位置计算逻辑与绘制函数完全保持一致。

## 执行计划

1. **修改** **`get_motion_path_handle_at_mouse`**：

   * 从 `_state.position_cache` 中尝试获取 `world_velocity`。

   * 如果存在：使用 `point_3d + (world_velocity * dt) * global_scale` 公式计算手柄的世界坐标。

   * 如果不存在：保留原有的父级矩阵回退逻辑。

## 验证目标

* 点击手柄时，不应发生任何位置跳变。

* 鼠标悬停检测（Hit Testing）应准确对应当前视觉上的手柄位置。

