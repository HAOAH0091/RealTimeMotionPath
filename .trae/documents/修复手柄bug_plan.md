# Motion Path Pro 手柄Bug修复计划

## 📋 总体情况
- 问题：父级变换后手柄方向偏移
- 根因：对象模式下绘制手柄时矩阵错误
- 优先级：P0（致命bug）

---

## [x] 任务 1：修复对象模式绘制时的矩阵
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 修复 `draw_motion_path_handles()` 函数中的对象模式矩阵
  - 将单位矩阵改为 `obj.matrix_world.to_3x3()`
- **Success Criteria**:
  - 父级旋转后手柄方向正确
  - 默认值下仍然正常工作
- **Test Requirements**:
  - `programmatic` TR-1.1: 代码修改正确，行号匹配 ✅
  - `human-judgement` TR-1.2: 父级旋转-90°后手柄与路径相切 (待验证)
- **Notes**: 
  - 文件：`__init__.py`
  - 函数：`draw_motion_path_handles()`
  - 行号：358-359
  - **状态**: ✅ 已完成

---

## [x] 任务 2：检查并修复骨骼模式的一致性
- **Priority**: P1
- **Depends On**: 任务 1
- **Description**: 
  - 检查 `get_motion_path_handle_at_mouse()` 与 `draw_motion_path_handles()` 的矩阵一致性
  - 确保两个函数使用相同的矩阵计算逻辑
- **Success Criteria**:
  - 骨骼模式下手柄绘制和碰撞检测一致
- **Test Requirements**:
  - `programmatic` TR-2.1: 两个函数使用相同的矩阵逻辑 ✅
  - `human-judgement` TR-2.2: 骨骼模式下手柄点击检测准确 (待验证)
- **Notes**:
  - 已修复：两个函数现在都用 `obj.matrix_world @ bone.matrix`
  - **状态**: ✅ 已完成

---

## [/] 任务 3：验证修复效果
- **Priority**: P0
- **Depends On**: 任务 1, 任务 2
- **Description**: 
  - 运行完整的验证清单
  - 确保所有场景都正常工作
- **Success Criteria**:
  - 所有验证项目通过
- **Test Requirements**:
  - `human-judgement` TR-3.1: 默认值下（无父级变换）手柄正常 (待验证)
  - `human-judgement` TR-3.2: 父级旋转后手柄方向正确 (待验证)
  - `human-judgement` TR-3.3: 父级缩放后手柄长度正确 (待验证)
  - `human-judgement` TR-3.4: 父级位移后手柄位置正确 (待验证)
  - `human-judgement` TR-3.5: 骨骼模式下同样正常 (待验证)
  - `human-judgement` TR-3.6: 拖动手柄功能仍然正常 (待验证)
  - `human-judgement` TR-3.7: 手柄拖动后能正确更新F-Curve (待验证)
- **Notes**: 按验证清单逐一验证
  - **状态**: 🟡 进行中 - 需要用户在Blender中测试验证

---

## 📝 快速修改参考

### 修改 1（任务1）
```python
# 修改前（行 358-359）
else:
    rotation_matrix = mathutils.Matrix.Identity(3)

# 修改后
else:
    rotation_matrix = obj.matrix_world.to_3x3()
```

---

## 📅 计划日期
2026-02-20
