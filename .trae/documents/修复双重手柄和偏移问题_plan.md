# 修复双重手柄、部分偏移、不相切问题 - 实现计划

## 🐛 问题分析

### 问题1：双重手柄

**现象**：每个关键帧有两个手柄重叠
**原因**：`draw_enhanced_object_path()` 中调用了两次 `draw_motion_path_handles()`

* 第1次：通过 `draw_motion_path_point()` 内部调用

* 第2次：在第254行直接调用
  **解决**：删除第247-254行的重复手柄绘制代码

***

### 问题2：部分手柄偏移

**现象**：一些手柄还是随父级动画偏移
**原因**：`draw_enhanced_object_path()` 调用 `draw_motion_path_point()` 时，没有传递 `parent_matrix` 参数
**对比**：

* `draw_enhanced_bone_path()` ✅ 传递了 `parent_matrix=parent_matrix`

* `draw_enhanced_object_path()` ❌ 没有传递
  **解决**：在第245行加上 `parent_matrix=parent_matrix`

***

### 问题3：修改父级动画后，缓存不自动更新

**现象**：修改父级的动画后，手柄还是不对，需要手动刷新
**原因**：`MOTIONPATH_AutoUpdateMotionPaths` 只检测**当前对象**的关键帧变化，没有检测**父级对象**的关键帧变化。
虽然缓存是在子级关键帧时间点通过插值获取父级变换的，但父级的任何关键帧变化（即使不在子级关键帧时间点）都会影响插值结果，因此需要检测父级所有关键帧的变化。
**解决**：修改 `_get_keyframe_values()` 函数，使其递归收集父级（包括物体父级）的关键帧数据。

***

## \[ ] 任务1：删除 `draw_enhanced_object_path()` 中重复的手柄绘制

* **Priority**: P0

* **Depends On**: None

* **Description**:

  * 删除第247-254行的重复手柄绘制代码

* **Success Criteria**:

  * 每个关键帧只有一个手柄

***

## \[ ] 任务2：修复 `draw_enhanced_object_path()` 传递 parent\_matrix

* **Priority**: P0

* **Depends On**: 任务1

* **Description**:

  * 在调用 `draw_motion_path_point()` 时添加 `parent_matrix=parent_matrix` 参数

* **Success Criteria**:

  * 所有手柄都使用缓存的父级矩阵

***

## \[ ] 任务3：修改 `_get_keyframe_values()` - 检测父级对象的所有关键帧

* **Priority**: P0

* **Depends On**: 任务2

* **Description**:

  * 修改 `_get_keyframe_values()` 函数

  * 编写辅助函数 `_collect_object_keyframes(obj)` 来获取单个对象的关键帧数据

  * 在主函数中，不仅获取 `active_object` 的数据，还要通过 `obj.parent` 循环向上获取所有父级对象的数据

  * 将所有这些数据合并作为指纹，用于检测变化

* **Success Criteria**:

  * 修改父级动画后，缓存会自动刷新

***

## \[ ] 任务4：验证修复效果

* **Priority**: P0

* **Depends On**: 任务1-3

* **Description**:

  * 验证上述修复是否有效

* **Success Criteria**:

  * 所有问题都解决

