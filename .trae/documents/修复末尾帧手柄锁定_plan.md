# 修复末尾帧手柄锁定问题计划

## 1. 目标
修复在动画末尾帧（或静止状态）时，由于计算出的世界速度（world_velocity）为零，导致手柄被强制绘制在关键帧位置上，从而引发手柄消失且无法操作关键帧的问题。

## 2. 核心逻辑
在绘制手柄和检测手柄交互时，增加对 `world_velocity` 长度的检测。如果速度极小（说明速度法失效），则回退到使用原始 F-Curve 数据和父级旋转矩阵来计算手柄位置。

## 3. 具体步骤

### 3.1 修改手柄绘制逻辑
**文件**: `__init__.py`
**函数**: `draw_motion_path_handles`
**位置**: 约第 374 行
**修改**:
将 `if world_velocity is not None:`
改为 `if world_velocity is not None and world_velocity.length > 0.0001:`

### 3.2 修改手柄交互检测逻辑
**文件**: `__init__.py`
**函数**: `get_motion_path_handle_at_mouse`
**位置**:
1.  **骨骼模式 (Selected Bones)**: 约第 1334 行
    将 `if world_velocity is not None:` 改为 `if world_velocity is not None and world_velocity.length > 0.0001:`
2.  **骨骼模式 (Active Bone)**: 约第 1407 行
    将 `if world_velocity is not None:` 改为 `if world_velocity is not None and world_velocity.length > 0.0001:`
3.  **对象模式**: 约第 1478 行
    将 `if world_velocity is not None:` 改为 `if world_velocity is not None and world_velocity.length > 0.0001:`

## 4. 验证计划
1.  打开包含动画的 Blender 场景。
2.  选中带动画的物体或骨骼。
3.  将时间轴移动到最后一帧。
4.  **验证 1**: 确认末尾帧的手柄是否可见（不再是一个点）。
5.  **验证 2**: 尝试拖动手柄，确认手柄交互正常。
6.  **验证 3**: 尝试点击关键帧中心点，确认可以选中并拖动关键帧位置，而不是误触手柄。
