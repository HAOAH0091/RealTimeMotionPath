# RealTimeMotionPath - 开发者文档

## 项目概述

RealTimeMotionPath 是一个 Blender 动画插件，用于在 3D 视口中实时显示和编辑物体/骨骼的运动路径。该插件支持直接在 3D 视图中拖拽关键帧、调整贝塞尔手柄，并与图形编辑器保持同步。

**兼容版本**: Blender 5.0+
**当前版本**: 1.0.0
**作者**: HAOAH

---

## 项目结构

```
RealTimeMotionPath/
├── __init__.py              # 插件入口，注册类和属性
├── state.py                 # 全局状态管理
├── cache.py                 # 位置缓存和 F-Curve 读取
├── drawing.py               # GPU 绘制逻辑
├── interaction.py           # 用户交互处理（点击、拖拽等）
├── ui.py                    # UI 界面（首选项、Header 菜单）
├── translations.py          # 国际化翻译
├── Change Log.md            # 开发历史记录
├── README.md                # 用户文档
└── README_DEV.md            # 本文档
```

---

## 核心模块详解

### 1. `__init__.py` - 插件入口

**职责**:
- 定义 `bl_info` 元数据
- 注册/注销所有 Operator 和 Panel 类
- 定义 WindowManager 级别的属性
- 注册国际化翻译

**关键属性** (`bpy.types.WindowManager`):
- `custom_path_draw_active` - 运动路径显示开关
- `direct_manipulation_active` - 直接编辑模式开关
- `auto_update_active` - 自动更新模式开关
- `motion_path_update_mode` - 更新模式 ('SMART' | 'TIMER')
- `motion_path_fps_limit` - 交互帧率限制
- `auto_update_fps` - 计时器模式更新频率
- `handle_type` - 默认手柄类型
- `handle_snap` - 手柄吸附开关
- `global_handle_visual_scale` - 手柄视觉缩放

**注册流程**:
1. 注册翻译
2. 注册所有类
3. 向 WindowManager 添加自定义属性
4. 向 VIEW3D_HT_header 添加绘制按钮

---

### 2. `state.py` - 全局状态管理

**核心类**: `MotionPathState`

**状态字段**:
```python
class MotionPathState:
    is_dragging                    # 是否正在拖拽关键帧
    drag_start_mouse               # 拖拽起始鼠标位置
    drag_start_3d                  # 拖拽起始 3D 位置
    selected_path_point            # 选中的路径点
    selected_frame                 # 选中的帧号
    selected_handle_side           # 选中的手柄侧 ('LEFT' | 'RIGHT')
    selected_bone_name             # 选中的骨骼名称（字符串，避免 RNA 悬空引用）
    handle_points                  # 手柄点列表 [{position, side, frame, obj_name, bone_name}, ...]
    selected_handle_point          # 选中的手柄点
    selected_handle_data           # 选中的手柄数据
    handle_dragging                # 是否正在拖拽手柄
    selected_drag_object_name      # 正在拖拽的对象名称（字符串）
    position_cache                 # 位置缓存 {obj_name: {cache_key: {frame: {'position': Vector}}}}
    initial_handle_values          # 手柄初始值（用于拖拽计算）
    draw_handler                   # GPU 绘制回调句柄
    path_vertices                  # 路径顶点 {(obj_name, bone_name_or_None): [Vector, ...]}
```

**重要设计决策**:
- **不保存 RNA 引用**: 所有对象/骨骼引用都使用名称字符串，避免悬空引用导致崩溃
- **原子锁**: `_is_updating_cache` 防止 `build_position_cache` 递归调用

**常量**:
- `HANDLE_SELECT_RADIUS = 20` - 手柄点击检测半径（像素）
- `SAFE_LIMIT = 1000000.0` - 坐标安全限制，防止 GPU 崩溃
- `MIN_HANDLE_SCALE = 0.1` - 手柄最小缩放系数
- `MAX_HANDLE_SCALE = 100.0` - 手柄最大缩放系数

---

### 3. `cache.py` - 缓存和 F-Curve 处理

**核心函数**:

#### `get_fcurves(action)`
从 Action 中提取 F-Curve 列表（兼容 Blender 5.0+ 的新动画系统）。

#### `calculate_path_from_fcurves(obj, action, frames, bone_name=None)`
从 F-Curve 计算指定帧的位置数据。
- **坐标系**: 父级本地空间（无父级 = 世界空间）
- **返回**: `{frame: {'position': Vector}}`

#### `build_position_cache(context)`
构建位置缓存和路径顶点数据。
- **原子锁保护**: 使用 `_is_updating_cache` 防止递归
- **物体模式**: 遍历 `context.selected_objects`
- **姿态模式**: 遍历选中骨骼 + 活动骨骼
- **双缓存**:
  - `position_cache`: 稀疏关键帧数据（用于交互）
  - `path_vertices`: 稠密路径线数据（用于绘制）

#### `get_current_parent_matrix(obj, bone=None)`
计算父级变换矩阵。
- **物体模式**:
  - 无父级 → `Identity`
  - 有父级 → `parent.matrix_world @ obj.matrix_parent_inverse`
- **姿态模式**:
  - 根骨骼 → `obj.matrix_world @ bone.bone.matrix_local`
  - 子骨骼 → `obj.matrix_world @ bone.parent.matrix @ parent.bone.matrix_local.inverted() @ bone.bone.matrix_local`

---

### 4. `drawing.py` - GPU 绘制

**绘制流程**:
1. `enable_draw_handler()` → 注册 `draw_motion_path_overlay` 回调
2. `draw_motion_path_overlay()` → 主绘制函数
3. 使用 `GPUBatch` 批量绘制，提升性能

**核心绘制元素**:
- 路径线（POLYLINE）
- 帧点（自定义抗锯齿着色器）
- 关键帧点（自定义抗锯齿着色器）
- 手柄线和端点
- 原点指示器

**自定义着色器**: `_get_circle_aa_shader()`
- 使用 quad + 片段着色器实现抗锯齿圆点
- `smoothstep()` 实现软边缘 alpha 混合
- 模块级缓存，避免重复创建

**手柄时间归一化**: `get_handle_correction_factors()`
- 解决 F-Curve 手柄时间长度不一致导致的 3D 视觉折角问题
- 计算缩放系数 `Factor = S / dt`（S 为平均持续时间）
- 绘制时正向缩放，交互时反向修正

---

### 5. `interaction.py` - 用户交互

**核心 Operator**:

#### `MOTIONPATH_DirectManipulation`
Modal Operator，处理鼠标点击和拖拽。

**事件处理**:
- `LEFTMOUSE`: 命中检测 → 选中 → 拖拽
- `RIGHTMOUSE`: 右键菜单（设置手柄类型）
- `MOUSEMOVE`: 拖拽更新
- `ESC`/`RIGHTMOUSE` (未命中): 取消

**命中检测函数**:
- `get_motion_path_point_at_mouse()` - 检测关键帧点
- `get_motion_path_handle_at_mouse()` - 检测手柄线
- `get_handle_point_at_mouse()` - 检测手柄端点

**拖拽更新函数**:
- `move_selected_points()` - 移动选中的关键帧
- `move_selected_handles()` - 移动选中的手柄
- `move_handle_point()` - 移动单个手柄端点

#### `MOTIONPATH_AutoUpdateMotionPaths`
Modal Operator，负责自动更新缓存。

**检测内容**:
- 活动对象切换
- 选中对象集合变化
- 骨骼选择变化
- 关键帧值变化（计时器模式）

**智能更新 Handler**: `on_depsgraph_update()`
- 监听 `depsgraph_update_post`
- 区分「交互更新」（仅 OBJECT 更新）和「数据更新」（ACTION 更新）
- 交互时复用上一帧缓存，避免卡顿

---

### 6. `ui.py` - 用户界面

**类**:
- `MOTIONPATH_AddonPreferences` - 插件首选项面板
- `MOTIONPATH_PT_header_settings` - Header 设置弹出面板
- `MOTIONPATH_MT_context_menu` - 右键上下文菜单
- `MOTIONPATH_ToggleCustomDraw` - 开关 Operator
- `MOTIONPATH_ResetPreferences` - 重置设置 Operator

**首选项设置分类**:
1. Style Settings - 路径样式
2. Frame Points - 帧点
3. Keyframes - 关键帧
4. Handles - 手柄
5. Origin Indicator - 原点指示器

---

## 核心数据流

```
用户操作
   ↓
depsgraph_update_post 或 AutoUpdate modal 检测
   ↓
build_position_cache()
   ├─ 读取 F-Curve
   ├─ calculate_path_from_fcurves()
   └─ 填充 position_cache 和 path_vertices
   ↓
draw_motion_path_overlay() 回调
   ├─ 从 cache 读取数据
   ├─ 乘以 get_current_parent_matrix()
   └─ GPU 绘制
   ↓
用户点击/拖拽
   ↓
命中检测 → 操作 F-Curve → 触发 depsgraph 更新 → 循环
```

---

## 关键设计决策

### 1. 去 RNA 引用化
**问题**: 长期保存 Blender RNA 对象引用会导致悬空引用和崩溃。
**方案**: 所有对象/骨骼引用改为名称字符串，使用时通过 `bpy.data.objects.get(name)` 动态查找。
**位置**: `state.py` 全文件，`interaction.py` 的 `_get_drag_obj()`

### 2. Fast Path 统一
**问题**: Slow Path 使用 `frame_set()` 逐帧切换，性能差且干扰交互。
**方案**: 完全移除 Slow Path，统一从 F-Curve 读取数据。
**位置**: `cache.py` 的 `build_position_cache()`

### 3. 智能交互避让
**问题**: 用户按 G 键移动物体时，路径计算会干扰交互。
**方案**: 在 `on_depsgraph_update()` 中检测「仅 OBJECT 更新，无 ACTION 更新」，判定为交互中，直接复用缓存。
**位置**: `interaction.py` 的 `on_depsgraph_update()`

### 4. 手柄时间归一化
**问题**: F-Curve 手柄时间长度不一致时，3D 手柄会出现折角。
**方案**: 计算缩放系数 `Factor = S / dt`，绘制时缩放手柄，交互时反向修正。
**位置**: `drawing.py` 的 `get_handle_correction_factors()`

---

## 代码约定

### 异常处理
- 使用 `except Exception:` 而非裸 `except:`，避免吞噬系统异常
- 绘制和缓存热路径添加异常防护，遇到失效数据跳过当前项

### 性能优化
- 绘制热路径使用 `GPUBatch` 批量绘制
- 预先构建 `{frame: {array_index: keyframe}}` 字典，避免 O(n×m) 复杂度
- 模块级缓存着色器和其他昂贵资源

### 国际化
- 所有用户可见字符串使用 `iface_()` 包裹
- 翻译字典键使用 `("*", "Original")` 通用上下文

---

## 扩展开发指南

### 添加新的绘制元素
1. 在 `drawing.py` 中添加绘制函数
2. 在 `draw_motion_path_overlay()` 中调用
3. 如需样式配置，在 `ui.py` 的 `MOTIONPATH_AddonPreferences` 中添加属性

### 添加新的交互功能
1. 在 `interaction.py` 的 `MOTIONPATH_DirectManipulation.modal()` 中添加事件处理
2. 如需状态，在 `state.py` 的 `MotionPathState` 中添加字段
3. 操作 F-Curve 后会自动触发更新，无需手动调用

### 添加新手柄类型
1. 在 `__init__.py` 的 `handle_type_items` 中添加选项
2. 在 `interaction.py` 的 `set_handle_type()` 中添加处理逻辑
3. 在 `translations.py` 中添加翻译

---

## 调试建议

### 启用调试打印
在关键位置添加 `print()` 语句，输出到 Blender 系统控制台。

### 检查缓存状态
```python
from RealTimeMotionPath.state import _state
print(_state.position_cache.keys())
print(_state.path_vertices.keys())
```

### 验证坐标系
在 `draw_motion_path_overlay()` 中临时添加调试圆点，验证坐标转换是否正确。

### 常见问题排查
- **崩溃**: 检查是否有 RNA 引用长期保存
- **路径不更新**: 检查 `build_position_cache()` 是否被调用
- **位置偏移**: 检查 `get_current_parent_matrix()` 的计算
- **手柄异常**: 检查 `get_handle_correction_factors()` 的缩放系数

---

## 开发历史

详细的开发记录请参考 `Change Log.md`，包含：
- 功能演进过程
- Bug 修复的根因分析
- 性能优化细节
- 架构决策记录

---

## 联系方式

- 作者: HAOAH
- 问题反馈: 请通过 Blender 插件页面或 GitHub Issues 反馈
