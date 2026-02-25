# Motion Path Pro 手柄Bug完整修复计划（含新问题）

## 📋 总体情况
- 问题 1：父级变换后手柄偏移（已部分修复，但引入新问题）
- 问题 2：对象自身旋转后手柄也旋转（新发现）
- 根因：当前使用的矩阵包含了不应该包含的对象自身变换
- 优先级：P0（致命bug）

---

## 📊 三个阶段的对比

| 阶段 | 对象模式矩阵 | 骨骼模式矩阵 | 问题 |
|------|-------------|-------------|------|
| 原始代码 | 单位矩阵 | `obj.matrix_world @ bone.matrix` | ❌ 忽略父级变换 |
| 第一次修复 | `obj.matrix_world.to_3x3()` | 保持不变 | ❌ 包含对象自身变换 |
| **最终方案** | **只含父级的矩阵** | **只含父级的矩阵** | ✅ 完美！ |

---

## [x] 任务 1：修复对象模式绘制时的矩阵（正确版本）
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 修复 `draw_motion_path_handles()` 函数中的对象模式矩阵
  - 提取**只包含父级变换**的矩阵（排除对象自身变换）
- **Success Criteria**:
  - 父级旋转后手柄方向正确
  - 对象自身旋转后手柄**不**跟着旋转
  - 默认值下仍然正常工作
- **Test Requirements**:
  - `programmatic` TR-1.1: 代码修改正确，使用 `obj.matrix_world @ obj.matrix_local.inverted()` ✅
  - `human-judgement` TR-1.2: 父级旋转-90°后手柄与路径相切 (待验证)
  - `human-judgement` TR-1.3: 对象自身旋转90°后，手柄保持原方向 (待验证)
- **Notes**: 
  - 文件：`__init__.py`
  - 函数：`draw_motion_path_handles()`
  - 行号：358-359
  - **状态**: ✅ 已完成

---

## [x] 任务 2：修复骨骼模式绘制时的矩阵（一致性）
- **Priority**: P0
- **Depends On**: 任务 1
- **Description**: 
  - 修复 `draw_motion_path_handles()` 函数中的骨骼模式矩阵
  - 提取**只包含父级骨骼变换**的矩阵
  - 如果没有父骨骼，用 `obj.matrix_world`
- **Success Criteria**:
  - 骨骼父级旋转后手柄方向正确
  - 骨骼自身旋转后手柄**不**跟着旋转
- **Test Requirements**:
  - `programmatic` TR-2.1: 代码修改正确，判断 `bone.parent` 并使用对应矩阵 ✅
  - `human-judgement` TR-2.2: 骨骼父级旋转后手柄与路径相切 (待验证)
  - `human-judgement` TR-2.3: 骨骼自身旋转后，手柄保持原方向 (待验证)
- **Notes**: 
  - 文件：`__init__.py`
  - 函数：`draw_motion_path_handles()`
  - 行号：352-357
  - **状态**: ✅ 已完成

---

## [x] 任务 3：修复对象模式拖动时的矩阵
- **Priority**: P0
- **Depends On**: 任务 1
- **Description**: 
  - 修复 `move_handle_point()` 函数中的对象模式矩阵
  - 与绘制时保持一致，使用相同的父级变换矩阵
- **Success Criteria**:
  - 拖动手柄功能在各种变换下都正常
- **Test Requirements**:
  - `programmatic` TR-3.1: 代码修改正确，与绘制逻辑一致 ✅
  - `human-judgement` TR-3.2: 拖动手柄后F-Curve正确更新 (待验证)
- **Notes**: 
  - 文件：`__init__.py`
  - 函数：`move_handle_point()` 和 `move_selected_handles()`
  - **状态**: ✅ 已完成

---

## [x] 任务 4：修复骨骼模式拖动时的矩阵
- **Priority**: P0
- **Depends On**: 任务 2
- **Description**: 
  - 修复 `move_handle_point()` 函数中的骨骼模式矩阵
  - 与绘制时保持一致
- **Success Criteria**:
  - 骨骼模式下拖动手柄功能正常
- **Test Requirements**:
  - `programmatic` TR-4.1: 代码修改正确，与绘制逻辑一致 ✅
  - `human-judgement` TR-4.2: 拖动手柄后F-Curve正确更新 (待验证)
- **Notes**: 
  - 文件：`__init__.py`
  - 函数：`move_handle_point()` 和 `move_selected_handles()`
  - **状态**: ✅ 已完成

---

## [x] 任务 5：修复碰撞检测时的矩阵（对象+骨骼模式）
- **Priority**: P0
- **Depends On**: 任务 1, 任务 2
- **Description**: 
  - 修复 `get_motion_path_handle_at_mouse()` 函数中的矩阵
  - 与绘制和拖动保持一致
- **Success Criteria**:
  - 碰撞检测在各种变换下都准确
- **Test Requirements**:
  - `programmatic` TR-5.1: 对象模式矩阵正确 ✅
  - `programmatic` TR-5.2: 骨骼模式矩阵正确 ✅
  - `human-judgement` TR-5.3: 点击手柄能准确选中 (待验证)
- **Notes**: 
  - 文件：`__init__.py`
  - 函数：`get_motion_path_handle_at_mouse()`
  - **状态**: ✅ 已完成

---

## [x] 任务 6：全面验证修复效果
- **Priority**: P0
- **Depends On**: 任务 1-5
- **Description**: 
  - 运行完整的验证清单
  - 确保所有场景都正常工作
- **Success Criteria**:
  - 所有验证项目通过
- **Test Requirements**:
  - `human-judgement` TR-6.1: 默认值下（无变换）手柄正常 ✅
  - `human-judgement` TR-6.2: 父级旋转后手柄方向正确 ✅
  - `human-judgement` TR-6.3: 父级缩放后手柄长度正确 ✅
  - `human-judgement` TR-6.4: 父级位移后手柄位置正确 ✅
  - `human-judgement` TR-6.5: **对象自身旋转后，手柄不跟着旋转** ✅
  - `human-judgement` TR-6.6: **对象自身缩放后，手柄不跟着缩放** ✅
  - `human-judgement` TR-6.7: 骨骼模式下同样正常 ✅
  - `human-judgement` TR-6.8: 拖动手柄功能仍然正常 ✅
  - `human-judgement` TR-6.9: 手柄拖动后能正确更新F-Curve ✅
- **Notes**: 按验证清单逐一验证
  - **状态**: ✅ 已完成 - 用户确认问题修复！

---

## 📝 修复参考代码

### 修复 1：对象模式绘制
```python
# 修改前
else:
    rotation_matrix = obj.matrix_world.to_3x3()

# 修改后
else:
    parent_matrix = obj.matrix_world @ obj.matrix_local.inverted()
    rotation_matrix = parent_matrix.to_3x3()
```

---

### 修复 2：骨骼模式绘制
```python
# 修改前
if context.mode == 'POSE' and bone is not None:
    try:
        bone_matrix = obj.matrix_world @ bone.matrix
        rotation_matrix = bone_matrix.to_3x3()
    except:
        rotation_matrix = mathutils.Matrix.Identity(3)

# 修改后
if context.mode == 'POSE' and bone is not None:
    try:
        if bone.parent:
            parent_matrix = obj.matrix_world @ bone.parent.matrix
        else:
            parent_matrix = obj.matrix_world
        rotation_matrix = parent_matrix.to_3x3()
    except:
        rotation_matrix = mathutils.Matrix.Identity(3)
```

---

## 📅 计划日期
2026-02-20
