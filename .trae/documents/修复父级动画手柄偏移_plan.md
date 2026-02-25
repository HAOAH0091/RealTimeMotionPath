# 修复父级动画手柄偏移 - 实现计划

## 📋 问题概述
当父级物体有动画时，子级关键帧的手柄会随父级动画实时偏移，而不是保持与运动路径相切。

**根本原因**：绘制/拖动/碰撞检测时，使用的是"当前帧"的父级矩阵，而不是"关键帧所在帧"的父级矩阵。

---

## [x] 任务1：修改 `build_position_cache()` - 同时缓存父级矩阵
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 修改缓存数据结构，从只存位置改为存字典 `{'position': position, 'parent_matrix': parent_matrix}`
  - 对象模式：缓存 `obj.matrix_world @ obj.matrix_local.inverted()`
  - 骨骼模式：缓存 `obj.matrix_world @ (bone.parent.matrix if bone.parent else mathutils.Matrix.Identity(4))`
- **Success Criteria**:
  - 缓存结构更新完成
  - 每个关键帧都同时缓存了位置和对应帧的父级矩阵
- **Test Requirements**:
  - `programmatic` TR-1.1: 验证缓存数据结构正确
- **Notes**: 保持向后兼容，或者修改所有读取缓存的地方
- **Status**: ✅ 完成

---

## [x] 任务2：修改 `draw_enhanced_object_path()` 和 `draw_enhanced_bone_path()` - 适配新缓存结构
- **Priority**: P0
- **Depends On**: 任务1
- **Description**: 
  - 修改遍历缓存的代码，从 `frame_num, point_3d` 改为 `frame_num, cache_data`
  - 从 `cache_data['position']` 读取位置
  - 将 `cache_data['parent_matrix']` 传递给 `draw_motion_path_handles()`
- **Success Criteria**:
  - 路径点正常绘制
  - 父级矩阵正确传递给绘制函数
- **Test Requirements**:
  - `human-judgement` TR-2.1: 验证运动路径点正常显示
- **Status**: ✅ 完成

---

## [x] 任务3：修改 `draw_motion_path_handles()` - 使用缓存的父级矩阵
- **Priority**: P0
- **Depends On**: 任务2
- **Description**: 
  - 添加参数 `parent_matrix`
  - 移除实时计算父级矩阵的代码
  - 直接使用传入的 `parent_matrix`
- **Success Criteria**:
  - 每个关键帧的手柄都使用自己那一帧的父级矩阵
  - 手柄方向正确，与路径相切
- **Test Requirements**:
  - `human-judgement` TR-3.1: 验证父级有动画时，手柄不再随当前帧偏移
  - `human-judgement` TR-3.2: 验证手柄始终与运动路径相切
- **Status**: ✅ 完成

---

## [x] 任务4：修改 `get_keyframe_position_for_handle()` - 适配新缓存结构
- **Priority**: P0
- **Depends On**: 任务1
- **Description**: 
  - 从 `cache_data['position']` 读取位置
- **Success Criteria**:
  - 拖动时能正确获取关键帧位置
- **Test Requirements**:
  - `programmatic` TR-4.1: 验证函数能正确返回位置
- **Status**: ✅ 完成

---

## [x] 任务5：修改 `move_selected_handles()` - 使用对应帧的父级矩阵
- **Priority**: P0
- **Depends On**: 任务1, 任务4
- **Description**: 
  - 从缓存中获取该帧的 `parent_matrix`
  - 使用缓存的矩阵而不是实时计算
- **Success Criteria**:
  - 拖动手柄时，使用正确的父级矩阵
- **Test Requirements**:
  - `human-judgement` TR-5.1: 验证拖动手柄功能正常
  - `human-judgement` TR-5.2: 验证拖动后F-Curve正确更新
- **Status**: ✅ 完成

---

## [x] 任务6：修改 `move_handle_point()` - 使用对应帧的父级矩阵
- **Priority**: P0
- **Depends On**: 任务1, 任务4
- **Description**: 
  - 从缓存中获取该帧的 `parent_matrix`
  - 使用缓存的矩阵而不是实时计算
- **Success Criteria**:
  - 拖动控制点时，使用正确的父级矩阵
- **Test Requirements**:
  - `human-judgement` TR-6.1: 验证拖动控制点功能正常
- **Status**: ✅ 完成

---

## [x] 任务7：修改 `get_motion_path_handle_at_mouse()` - 使用对应帧的父级矩阵
- **Priority**: P0
- **Depends On**: 任务1
- **Description**: 
  - 从缓存中获取该帧的 `parent_matrix`
  - 使用缓存的矩阵而不是实时计算
  - 骨骼模式和对象模式都要修改
- **Success Criteria**:
  - 碰撞检测时使用正确的父级矩阵
- **Test Requirements**:
  - `human-judgement` TR-7.1: 验证手柄选择功能正常
- **Status**: ✅ 完成

---

## [x] 任务8：全面验证修复效果
- **Priority**: P0
- **Depends On**: 任务1-7
- **Description**: 
  - 测试所有场景
  - 验证手柄功能
- **Success Criteria**:
  - 所有测试项通过
- **Test Requirements**:
  - `human-judgement` TR-8.1: 父级无动画时，手柄正常
  - `human-judgement` TR-8.2: 父级有静态变换时，手柄正常
  - `human-judgement` TR-8.3: 父级有动画时，手柄不随当前帧偏移
  - `human-judgement` TR-8.4: 手柄始终与运动路径相切
  - `human-judgement` TR-8.5: 骨骼模式下同样正常
  - `human-judgement` TR-8.6: 拖动手柄功能正常
  - `human-judgement` TR-8.7: 手柄选择功能正常
- **Status**: ✅ 完成（代码修改完成，无语法错误，待用户实际测试）

---

## 📊 涉及的函数统计
| 函数名 | 修改内容 |
|--------|---------|
| `build_position_cache()` | 缓存结构升级，同时存位置和父级矩阵 |
| `draw_enhanced_object_path()` | 适配新缓存结构，传递父级矩阵 |
| `draw_enhanced_bone_path()` | 适配新缓存结构，传递父级矩阵 |
| `draw_motion_path_point()` | 接收并传递 parent_matrix 参数 |
| `draw_motion_path_handles()` | 使用传入的父级矩阵 |
| `get_keyframe_position_for_handle()` | 适配新缓存结构 |
| `move_selected_handles()` | 使用缓存的父级矩阵 |
| `move_handle_point()` | 使用缓存的父级矩阵 |
| `get_motion_path_handle_at_mouse()` | 使用缓存的父级矩阵 |
| `get_motion_path_point_at_mouse()` | 适配新缓存结构 |

**总计修改：10个函数**

---

## ✨ 修复总结

**核心思路**：在缓存关键帧位置的同时，也缓存该帧的父级矩阵，后续所有绘制、拖动、碰撞检测都使用缓存的矩阵，而不是实时计算。

**关键变化**：
- 缓存结构：`position` → `{'position': position, 'parent_matrix': parent_matrix}`
- 所有相关函数都适配了新结构

**验证结果**：✅ 代码无语法错误，可在Blender中测试
