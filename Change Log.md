# 开发历史记录

## 2026-03-01 (Feature — 手柄时间归一化与稳定性修复)

### Context
1. **视觉缺陷**：用户反馈当 F-Curve 手柄的时间长度（X轴持续时间）不一致时，3D 运动路径手柄会出现“折角”（不相切）的现象。
2. **崩溃问题**：初步修复后，Blender 因垂直手柄导致的数值爆炸而崩溃。

### Changes
1. **时间归一化算法**：
   - 实现 `get_handle_correction_factors`：计算缩放系数 $Factor = S / dt$（其中 $S$ 为平均持续时间）。
   - 将系数应用到 `draw_motion_path_handles`，使 3D 手柄代表速度方向（切线），而不仅仅是数值差。
   - 在 `move_selected_handles` 中进行反向修正，确保 3D 交互时 F-Curve 数据更新正确。

2. **崩溃修复 (数值稳定性)**：
   - 增加 `MIN_HANDLE_SCALE` (0.1) 和 `MAX_HANDLE_SCALE` (100.0) 钳制，防止 $dt \to 0$ 时数值无限增大。
   - 增强 `draw_batched_billboard_circles` 鲁棒性，使用显式 `float()` 转换和单点 `try...except` 保护，防止 `EXCEPTION_ACCESS_VIOLATION`。

3. **文档更新**：
   - 更新 `motion_path_fix_plan.md`，增加了通俗解释、流程图、风险分析及崩溃修复细节。

### Status
- **Done**: 即使 F-Curve 手柄长度不一致，3D 手柄现在也能在视觉上与路径曲线保持对齐（平滑相切）。
- **Fixed**: 修复了由垂直手柄（零时间持续时间）导致的崩溃问题。

---

## 2026-02-28 (Fix — 空白区域取消选中漏洞)

### Context
修复空白区域点击无法取消选中的漏洞：当用户选中了关键帧但**未选中对应对象/骨骼**时，点击空白区域无法清除关键帧的选中状态。

### Root Cause
- Object 模式：空白区域清除逻辑只遍历 `context.selected_objects`
- Pose 模式：空白区域清除逻辑只遍历 `context.selected_pose_bones`
- 如果对象/骨骼没有被选中，它的关键帧选中状态就不会被清除

### Changes
- 修改 Object 模式空白区域清除逻辑，遍历 `_state.position_cache` 而非 `selected_objects`
- 修改 Pose 模式空白区域清除逻辑，遍历 `position_cache` 中的骨骼而非 `selected_pose_bones`
- 使用 `bpy.data.objects.get()` 安全获取对象，处理已删除对象的情况
- 确保只要运动路径在显示，就能清除其关键帧选中状态

### Status
- **Fixed**: 无论对象/骨骼是否被选中，点击空白区域都能清除关键帧选中状态

---

## 2026-02-28 (Feature — 关键帧多选后操作优化)

### Context
用户希望在使用 Shift/Ctrl 复选多个关键帧后，无需继续按住 Shift/Ctrl 即可对这些关键帧进行操作（移动、设置手柄类型等）。同时修复了实现过程中出现的回归问题。

### Changes

1. **保留多选状态逻辑**（LEFTMOUSE 关键帧点击）：
   - 添加 `hit_keyframe_already_selected` 检查
   - 只有未按住 Shift/Ctrl 且点击未选中的关键帧时才清除其他选中状态
   - 复选后点击已选中的关键帧可拖拽移动所有选中关键帧

2. **保留多选状态逻辑**（RIGHTMOUSE 右键菜单）：
   - 右键点击已选中的关键帧时不清除其他选中状态
   - 支持批量设置手柄类型

3. **手柄点击优化**：
   - 删除手柄点击时操作关键帧选中状态的代码
   - 复选后操作手柄时保持关键帧多选状态不变

4. **空白区域点击检测**：
   - 添加空白区域点击检测，清除所有选中状态
   - 支持 Object 模式和 Pose 模式

5. **`set_handle_type` 函数重构**：
   - 支持多对象/多骨骼批量设置手柄类型
   - 遍历所有选中对象（Object 模式）或所有选中骨骼（Pose 模式）

6. **代码优化**：
   - 提取 `is_keyframe_selected()` 辅助函数，消除重复代码
   - 优化空白区域检测注释，明确列出所有检测条件

### Status
- **Done**: 复选后无需按住 Shift/Ctrl 即可操作多个关键帧
- **Done**: 手柄操作时保持多选状态
- **Done**: 空白区域点击清除所有选中
- **Done**: 多对象/多骨骼批量设置手柄类型

---

## 2026-02-26 (Feature — 圆点自定义着色器抗锯齿)

### Context
POLYLINE 粗线圆持续出现星形/花瓣状，改用自定义片段着色器实现抗锯齿。

### Changes

1. **`_get_circle_aa_shader()`**：模块级缓存，`GPUShaderCreateInfo` 定义 quad 着色器，顶点 `pos`+`uv`，片段中用 `smoothstep` 实现软边缘 alpha。

2. **`draw_billboard_circle`**：由 POLYLINE 改为 quad（4 顶点）+ 自定义着色器，`feather=0.1`。

3. **`draw_batched_billboard_circles`**：由 POLYLINE 改为 quad 批量，每批最多 500 圆，共享同一着色器。

4. **unregister**：清空 `_circle_aa_shader` 缓存。

### Status
- **Done**: 圆点使用 quad + smoothstep 软边缘，像素级抗锯齿
- **Segment**: 线段/环仍用 POLYLINE

---

## 2026-02-26 (Fix — 圆点花花样式 + 移除 TRI_FAN 回退)

### Context
POLYLINE 粗线圆使用 `lineWidth = 2×radius` 时出现星形/花瓣状（花花）样式；用户建议 `lineWidth = radius` 以刚好填满。同时移除不再需要的 TRI_FAN 回退机制。

### Changes

1. **lineWidth 调整**：`draw_billboard_circle` 与 `draw_batched_billboard_circles` 中，`lineWidth` 从 `2.0 * radius_in_pixels` 改为 `radius_in_pixels`，减轻顶点处过度扩展导致的星形感。

2. **移除 TRI_FAN 回退**：
   - 删除 `MotionPathStyleSettings.use_polyline_antialiasing` 属性
   - 删除 `draw_billboard_circle` / `draw_batched_billboard_circles` 中的 `use_polyline` 判断及 TRI_FAN 分支
   - 删除偏好设置中的「Rendering / Anti-aliasing」开关
   - 删除 `translations.py` 中对应翻译

### Status
- **Fixed**: 圆点应显示为实心圆，不再呈星形
- **Simplified**: 仅保留 POLYLINE 路径，无回退逻辑

---

## 2026-02-26 (Feature — Unified POLYLINE Anti-aliasing)

### Context
运动路径 UI 绘制改用 Blender 内置 POLYLINE 着色器，实现像素级抗锯齿；统一使用 POLYLINE，不引入自定义着色器。

### Changes

1. **线段类改用 POLYLINE**：
   - 路径主线：`UNIFORM_COLOR` + `line_width_set` → `POLYLINE_UNIFORM_COLOR`，传入 `viewportSize`、`lineWidth`、`color`
   - 手柄连线：`SMOOTH_COLOR` → `POLYLINE_SMOOTH_COLOR`，保留顶点色（选中/未选中双色）
   - 原点环（RING/RING_DOT）：`LINE_LOOP` + `UNIFORM_COLOR` → `POLYLINE_UNIFORM_COLOR`

2. **圆点改用粗 LINE_LOOP + POLYLINE**：
   - `draw_billboard_circle`、`draw_batched_billboard_circles`：由 TRI_FAN/TRIS 改为 LINES（圆周边） + `POLYLINE_UNIFORM_COLOR`，`lineWidth = 2 × radius` 实现实心圆抗锯齿
   - 关键帧点、帧点、手柄端点、原点 DOT 均走新路径

3. **TRI_FAN 回退**：
   - 新增 `MotionPathStyleSettings.use_polyline_antialiasing`（默认 True）
   - 关闭后圆点回退为原 TRI_FAN 绘制，便于在粗 LINE_LOOP 效果不佳时切换

4. **翻译**：新增 "Rendering"、"Anti-aliasing" 等条目

### Status
- **Done**: 所有绘制统一 POLYLINE，抗锯齿生效
- **Fallback**: 偏好设置中可关闭抗锯齿，圆点回退 TRI_FAN

---

## 2026-02-26 (Bug Fix — Skeleton Object Keyframe Drag After Pose→Object Switch)

### Context
用户测试发现：骨架对象有位移动画，开启运动路径后在物体模式显示与交互正常；进入 Pose 模式后显示骨骼运动路径，交互也正常；切回物体模式时路径正确切换回骨架对象路径，但**无法对关键帧点进行拖拽操作**，手柄点拖拽则正常。开关按钮刷新后可恢复，但重复上述流程会再次复现。

### Root Cause Analysis

1. **`move_selected_points` / `move_selected_handles` 未按模式解析 `bone_name`**：  
   两函数使用 `bone_name = _state.selected_bone_name`，未根据 `obj.mode` 判断。Pose→Object 切换后 `selected_bone_name` 仍保留骨骼名，导致过滤 `pose.bones["X"].location` 而忽略对象级 `location` fcurve，`selected_frames` 为空，拖拽无效果。

2. **`selected_bone_name` 未在模式切换时清空**：  
   Modal 仅在活动对象变化时清空状态，Pose→Object 时未重置。`_get_bone_selection_state` 虽会触发缓存重建，但不会清空 `selected_bone_name`。

3. **手柄拖拽正常的原因**：  
   `move_handle_point` 使用 `handle_point.get('bone_name')`，来源为绘制时写入，对象模式下手柄的 `bone_name` 为 `None`，故行为正确。

### Changes

1. **`move_selected_points` / `move_selected_handles` 按模式解析**：  
   `bone_name = _state.selected_bone_name if (obj and obj.mode == 'POSE') else None`，确保物体模式下始终使用 `bone_name = None` 以匹配对象级 location fcurve。

2. **Pose→Object 时清空 `selected_bone_name`**：  
   在 `MOTIONPATH_AutoUpdateMotionPaths.modal` 的 `current_bone_selection != self._last_bone_selection` 分支中，当 `current_bone_selection is None` 时清空 `_state.selected_bone_name`。

3. **关键帧/手柄/右键命中时显式清空（防御性）**：  
   LEFTMOUSE 关键帧点命中、`get_motion_path_handle_at_mouse` 手柄命中、RIGHTMOUSE 右键菜单分支中，在 Object 模式下均增加 `else: _state.selected_bone_name = None`，避免残留骨骼名影响交互。

### Status
- **Fixed**: 骨架对象 Pose→Object 切换后，关键帧点可正常拖拽。
- **No Regression**: Pose 模式骨骼交互、手柄拖拽行为不变。

---

## 2026-02-26 (Feature — Multi-Object/Multi-Bone Path Display)

### Context
用户需求：开启运动路径后，希望同时显示**所有选中对象**的运动路径，而非仅活动对象。原先选中第二个对象时，路径会切换为只显示第二个对象的路径。

### Changes

1. **`_state` 数据结构重构**：
   - `position_cache`：由单对象键改为 `{obj_name: {cache_key: {frame: {...}}}}`，`cache_key` 为 `None`（对象模式）或骨骼名（Pose 模式）。
   - `path_vertices`：由单一路径列表改为 `{(obj_name, bone_name_or_None): [Vector, ...]}`，支持多对象/多骨骼路径线。

2. **`build_position_cache` 多目标构建**：
   - 物体模式：遍历 `context.selected_objects`，为每个有动作的对象构建稀疏关键帧缓存和稠密路径线。
   - Pose 模式：遍历所有选中骨骼 + 活动骨骼，为每个骨骼分别构建缓存；`path_vertices` 按 `(obj_name, bone_name)` 存储。

3. **`draw_motion_path_overlay` 多路径绘制**：
   - 路径线：遍历 `_state.path_vertices`，按 `pv_obj_name` 解析对象、按 `pv_bone_name` 解析骨骼，各自计算 `parent_matrix` 后绘制。
   - 增强路径（关键帧点 + 手柄）：`draw_enhanced_path` 新增 `obj_name` 参数，在物体模式下按 `obj_name` 从 `position_cache` 取数据；Pose 模式下遍历 `bones_to_draw` 逐骨骼绘制。

4. **AutoUpdate modal 选中对象变化检测**：
   - 新增 `_get_selected_obj_names`、`_last_selected_obj_names`，当选中对象集合变化时触发缓存重建。

### Status
- **New Feature**: 物体模式下可同时显示多条运动路径；Pose 模式下可同时显示多骨骼路径。
- **No Regression**: 单对象/单骨骼行为保持不变。

---

## 2026-02-26 (Feature — Pose Mode Full Path Lines for All Selected Bones)

### Context
多骨骼路径显示初期，Pose 模式出现异常：非活动骨骼仅显示关键帧点，不显示路径线，而活动骨骼显示完整路径。用户期望所有选中骨骼都显示完整路径（线 + 点）。

### Root Cause Analysis
`build_position_cache` 在 Pose 模式下只为活动骨骼构建 `path_vertices`，其他选中骨骼只进入 `position_cache`（稀疏关键帧），未生成稠密路径线数据。

### Changes
- Pose 模式下，对 `bones_to_cache` 中每个骨骼均调用 `calculate_path_from_fcurves(..., frames_range, ...)` 生成稠密路径，并写入 `_state.path_vertices[(obj_name, bone_name)]`。
- `draw_motion_path_overlay` 中路径线循环已支持按 `(obj_name, bone_name)` 迭代，无需额外修改。

### Status
- **Fixed**: Pose 模式下所有选中骨骼均显示完整路径线与关键帧点。

---

## 2026-02-26 (Feature — Interaction Extension to All Displayed Paths)

### Context
多路径显示后，用户希望关键帧点、手柄的点击与拖拽交互能作用于**所有已显示路径**，而非仅活动对象/骨骼的路径。

### Changes

1. **命中检测扩展**：
   - `get_motion_path_point_at_mouse`（物体模式）：遍历 `_state.position_cache` 中所有对象，命中时设置 `_state.selected_drag_object_name = draw_obj.name`。
   - `get_motion_path_handle_at_mouse`（物体模式）：遍历所有 `position_cache` 对象，命中手柄时设置 `_state.selected_drag_object_name = draw_obj.name`。
   - `get_handle_point_at_mouse`：基于 `_state.handle_points` 中每条记录的 `obj_name` 判断所属对象。

2. **拖拽目标解析**：
   - `move_selected_points`、`move_selected_handles`、`move_handle_point`、`capture_initial_handle_values`、`get_keyframe_position_for_handle` 等统一使用 `_state.selected_drag_object or context.active_object` 作为操作目标，实现非活动对象的拖拽。（后续崩溃修复中将该引用改为名称字符串并引入 `_get_drag_obj`。）

3. **手柄数据传递**：
   - `draw_motion_path_handles` 为每个 `handle_point` 增加 `obj_name` 字段，供命中与拖拽时识别所属对象。

### Status
- **New Feature**: 物体模式与 Pose 模式下，均可对任意显示路径的关键帧点和手柄进行选中与拖拽。

---

## 2026-02-26 (Bug Fix — Non-Active Object First/Last Frame Handle Interaction)

### Context
多路径交互测试发现：非活动对象的**首尾帧手柄**无法拖拽，即便手柄与关键帧点视觉上距离较远；且拖拽非活动对象首尾帧手柄时，有时会误操作活动对象的其它关键帧手柄。Pose 模式无此问题。

### Root Cause Analysis

**Bug 1 — 零偏移手柄拦截点击**  
首尾帧使用 AUTO 手柄时，切线可能为零，导致手柄世界坐标与关键帧点重合。`get_motion_path_handle_at_mouse` 先于 `get_motion_path_point_at_mouse` 执行，会错误命中该“退化手柄”，进入手柄拖拽分支，而非关键帧拖拽，视觉上表现为无法移动位置。

**Bug 2 — 手柄数据缺少对象上下文**  
`_state.handle_points` 中仅存 `position`、`side`、`frame`、`bone`，无 `obj_name`。手柄命中后若 `selected_drag_object` 尚未设置，LEFTMOUSE 处理器会以 `context.active_object` 作为操作目标；若活动对象在该帧也有关键帧，则会错误操作活动对象的手柄。

### Changes

1. **`check_handles_at_frame` 跳过零偏移手柄**：
   - 在左右手柄命中检测前增加 `world_vector_left.length > 1e-4`、`world_vector_right.length > 1e-4` 判断，位移接近零时跳过该手柄，避免退化手柄拦截点击。

2. **`handle_points` 增加 `obj_name`**：
   - `draw_motion_path_handles` 写入 `handle_point` 时增加 `obj_name`（及后续的 `bone_name`），供命中与拖拽使用。

3. **手柄命中时设置拖拽目标**：
   - LEFTMOUSE 处理器中，`get_handle_point_at_mouse` 命中后，根据 `handle_point.get('obj_name')` 设置 `_state.selected_drag_object_name`，再调用 `capture_initial_handle_values` 与后续拖拽逻辑，确保操作正确的对象。

### Status
- **Fixed**: 非活动对象首尾帧手柄可正常拖拽。
- **Fixed**: 拖拽非活动对象手柄时不再误操作活动对象。

---

## 2026-02-26 (Crash Stability Fix — Stale RNA Reference Elimination)

### Context
用户反馈在完成“多对象/多骨骼路径显示与交互”后，Blender 崩溃频率显著上升。三份崩溃日志显示为 `EXCEPTION_ACCESS_VIOLATION`，并集中出现在绘制回调和交互路径相关调用链。

### Root Cause Analysis

根因是 `_state` 中长期保存了 Blender RNA 直接引用（对象/骨骼）。当底层 C++ 数据被删除或重建后，Python 侧旧引用变为悬空引用，后续在 draw / hit-test / drag 过程中访问这些引用会触发底层访问冲突。

### Changes

1. **状态字段改为名称字符串（避免悬空 RNA）**：
   - `selected_drag_object` → `selected_drag_object_name`
   - `selected_bone` → `selected_bone_name`
   - `handle_points` 内 `bone` 引用改为 `bone_name` 字符串

2. **新增安全对象解析函数**：
   - 增加 `_get_drag_obj(context)`，统一通过 `bpy.data.objects.get(name)` 动态查找拖拽目标，找不到时回退 `context.active_object`。

3. **多处交互流程改为“按名称临时解析”**：
   - 关键帧拖拽、手柄拖拽、命中检测、初值捕获等路径统一使用 `obj_name / bone_name` 解析，移除对持久 RNA 对象的依赖。

4. **绘制与缓存热路径增强异常防护**：
   - `get_current_parent_matrix`、`draw_motion_path_overlay`、`build_position_cache` 的关键循环补充异常防护，遇到失效对象/骨骼时跳过当前项，避免整条绘制链中断。

5. **Code Review 后续修正（本次同步落实）**：
   - 修复 POSE 命中检测中 `list(context.selected_pose_bones)` 的空值风险，改为 `list(context.selected_pose_bones or [])`。
   - `handle_point` 路径中 `_state.selected_drag_object_name` 改为显式赋值 `hp_obj_name or None`，避免残留旧对象名。
   - 统一异常写法为 `except Exception`，并补充注释说明：Python 层异常可兜底，C++ 级访问冲突需靠“消除悬空引用”从根源解决。

### Decisions
- **主修复优先级放在“去引用化”**：`try/except` 只能兜住 Python 层异常，无法保证拦截 C++ 崩溃；将 `_state` 改为字符串键是决定性修复。
- **绘制阶段实时查找对象/骨骼**：以轻微查找成本换取生命周期安全，适配对象删除、重命名、切换选择等高频编辑场景。
- **Review 问题与稳定性修复合并落地**：同一批改动集中清理，减少后续二次回归测试成本。

### Status
- **Fixed**: `_state` 不再持有对象/骨骼的长期 RNA 直接引用。
- **Fixed**: 多对象/多骨骼拖拽路径中的目标解析一致性提升，降低误命中风险。
- **Fixed**: POSE 命中检测空选择边界条件修复。
- **Stabilized**: 绘制与缓存流程对失效数据容错能力增强，崩溃风险显著下降。

---

## 2026-02-26 (Bug Fix — Parent-Child Path Offset in Object & Pose Mode)

### Context
用户测试发现：当选中对象有父级时，运动路径会偏移到父级的原点位置，而不是显示在子级的实际位置。问题同时存在于物体模式（Object Mode）和 Pose 模式（子骨骼）。

### Root Cause Analysis

**两个独立的坐标空间计算错误**：

#### 1. 物体模式 — 缺少 `matrix_parent_inverse`

Blender 对象的世界变换公式为：
```
matrix_world = parent.matrix_world @ matrix_parent_inverse @ matrix_basis
```
其中 `matrix_parent_inverse` 是绑定父级那一刻存储的补偿矩阵（等于父级当时世界矩阵的逆），用于防止子级在绑定时跳变。

原代码 `get_current_parent_matrix` 对有父级的对象只返回 `parent.matrix_world`，遗漏了 `matrix_parent_inverse`。绘制时：
- **错误**：`parent.matrix_world @ fcurve_values` → 路径出现在父级原点
- **正确**：`parent.matrix_world @ matrix_parent_inverse @ fcurve_values` → 路径在子级实际位置

#### 2. Pose 模式 — 子骨骼矩阵公式错误

原子骨骼公式为：
```python
obj.matrix_world @ bone.parent.matrix @ bone.bone.matrix_local
```
`bone.parent.matrix`（父骨骼当前姿态，骨架空间）和 `bone.bone.matrix_local`（子骨骼静止矩阵，同样是骨架空间）**都是骨架空间的矩阵，直接相乘没有几何意义**，等于将父骨骼的静止位置多叠加了一次，导致即使父骨骼无动画路径也会偏移。

正确的转换链：子骨骼本地偏移 → 父骨骼本地空间（`parent.bone.matrix_local.inverted() @ child.bone.matrix_local`）→ 骨架空间（`bone.parent.matrix @`）→ 世界空间（`obj.matrix_world @`）：
```python
obj.matrix_world @ bone.parent.matrix @ bone.parent.bone.matrix_local.inverted() @ bone.bone.matrix_local
```
当父骨骼无动画时（`parent.matrix == parent.bone.matrix_local`），中间两项抵消为 Identity，退化为根骨骼公式。

### Changes

1. **`get_current_parent_matrix` — 物体模式父级分支**：
   - 将 `return parent_mat` 改为 `return parent_mat @ obj.matrix_parent_inverse`。
   - 同时覆盖普通对象父级和骨骼父级（`parent_type == 'BONE'`）两种情况。
   - 为 BONE 父级查找失败的降级路径补充注释说明。

2. **`get_current_parent_matrix` — Pose 模式子骨骼分支**：
   - 在 `bone.parent.matrix` 与 `bone.bone.matrix_local` 之间插入 `bone.parent.bone.matrix_local.inverted()`。
   - 提取局部变量 `parent_to_child_rest` 提升可读性。

3. **Code Review 后续清理**：
   - 删除 `_state.path_batch` 死代码（`MotionPathState.__init__`、`build_position_cache` 重置处、路径构建处共 3 处）：该 batch 在缓存阶段构建但绘制阶段从未使用，白白浪费一次 GPU 上传。
   - 移除 `get_current_parent_matrix` 的 `context` 参数（函数体内从未使用），同步更新全部 10 处调用点。

### Decisions
- **`matrix_parent_inverse` 而非重新推导**：直接使用 Blender 已存储的 `obj.matrix_parent_inverse` 是最简洁、最准确的方式，无需重新计算或依赖 `frame_set`，与插件"不调用 frame_set、不修改场景状态"的设计原则完全一致。
- **不在缓存阶段处理父级**：父级矩阵在绘制阶段实时乘以缓存的本地值，使路径能实时跟随父级移动，无需在父级变换时重建缓存。
- **子骨骼公式的几何推导**：关键在于 `bone.bone.matrix_local` 是骨架空间矩阵，不能与同空间的 `parent.matrix` 直接链式相乘；必须先用 `parent.bone.matrix_local.inverted()` 将其还原到父骨骼本地空间，再由 `parent.matrix` 带回骨架空间。

### Status
- **Fixed**: 物体模式下有父级的对象运动路径现在显示在子级正确位置。
- **Fixed**: Pose 模式下子骨骼运动路径偏移问题修复，父骨骼有无动画均正确。
- **Removed**: `path_batch` 死代码已清除。
- **Cleaned**: `get_current_parent_matrix` 接口精简，移除未使用的 `context` 参数。

---

## 2026-02-25 (Bug Fix — Object Mode Path Not Updating on Selection Switch)

### Context
用户测试发现：物体模式下，打开运动路径后选中一个对象能正常显示路径，但切换选中另一个对象时，路径不更新，仍显示第一个对象的运动路径。骨骼模式无此问题。新场景可稳定复现。

### Root Cause Analysis

**双重失效**：

1. **`on_depsgraph_update` 误判**：用户点击切换选中对象时，depsgraph 触发 `is_object_updated=True, is_action_updated=False`。handler 将此判定为"交互移动"（`is_interaction_update = True`）并直接 `return`，`build_position_cache` 从未被调用。该判断的原意是避免 G/R/S 变换时卡顿，但对象选择切换与 G/R/S 移动对 depsgraph 的信号完全相同，无法区分。

2. **modal 缺少对象切换检测**：`MOTIONPATH_AutoUpdateMotionPaths.modal` 仅跟踪骨骼选择变化（Pose 模式），没有等价的"活动对象切换检测"（Object 模式）。因此即便 handler 跳过，modal 也不会补充触发重建。骨骼模式之所以正常，是因为 modal 的 `_get_bone_selection_state` 检测了骨骼切换并主动触发更新。

### Changes

1. **`invoke` 初始化 `_last_active_obj_name` 和 `_last_bone_selection`**：
   - 在 `invoke` 中与 `_last_keyframe_values` 同级初始化两个状态变量，消除 `modal` 热路径中原有的 `hasattr` 检查（性能改善）。

2. **`modal` 新增活动对象切换检测**：
   - 在骨骼选择检测之前，插入对 `context.active_object.name` 的比对逻辑。
   - 当活动对象名称变化时：清除 `_state` 中 8 个过时的选择/拖拽状态字段（防止新对象渲染时显示旧对象遗留的选中高亮），并设 `_needs_update = True` 触发缓存重建。

3. **`modal` 重绘范围扩展**：
   - 将触发重绘从仅刷新 `context.area` 改为遍历所有窗口的全部 `VIEW_3D` 区域，与 `on_depsgraph_update` 保持一致，修复多视口场景下可能不刷新的问题。

### Decisions
- **修复位置选在 modal 而非 depsgraph handler**：在 handler 中区分"对象切换"和"G/R/S 移动"在技术上极为困难（两者 depsgraph 信号相同）。在 modal 中追踪活动对象名称变化是最小侵入、最稳定的方案，且与骨骼模式已有的检测模式完全对称。
- **清除 `_state` 选择状态**：对象切换后如不清理，旧对象的 `selected_frame`、`selected_bone` 等字段可能使新对象的路径出现错误的高亮渲染，需要主动重置。

### Status
- **Fixed**: 物体模式下切换活动对象，运动路径即时更新为新对象的路径。
- **Fixed**: 多视口场景下切换对象后所有 3D 视图正确刷新。
- **No Regression**: Pose 模式骨骼切换行为不变；G/R/S 交互避让逻辑不变。

---

## 2026-02-25 (Code Review — Comprehensive Optimization)

### Context
对插件代码进行全面 Code Review，识别性能热点、死代码、代码重复、异常处理问题，并在不破坏现有功能的前提下系统性优化。

### Changes

**P1 — 高优先级**

1. **绘制热路径 O(n×m) → O(n+m) 优化**：
   - **Issue**: 原 `draw_enhanced_object_path` / `draw_enhanced_bone_path` 对每一帧都调用 `get_fcurves(action)` 遍历全部 fcurve，复杂度为 O(帧数 × fcurve数)，每次重绘都执行。
   - **Fix**: 合并两函数为 `draw_enhanced_path(…, bone=None)`，进入帧循环前预先构建 `{frame_int: {array_index: keyframe}}` 字典及 `frame_selected` 集合，帧循环内直接 O(1) 查找，复杂度降至 O(n+m)。

2. **清理 modal 死代码块**：
   - **Issue**: `MOTIONPATH_DirectManipulation.modal` 的 MOUSEMOVE 分支中，点拖拽逻辑存在一个带大量误导性注释的 `pass` 分支，真正的点拖拽实现在下方重复判断，造成逻辑混乱（约15行死代码）。
   - **Fix**: 删除无效 `pass` 分支和冗余注释，将双重 `if selected_handle_side is None` 合并为清晰的 `if/else` 结构。

3. **裸 `except:` → `except Exception:`**：
   - **Issue**: 全文16处裸 `except:`，会吞噬 `KeyboardInterrupt`、`SystemExit` 等系统异常。
   - **Fix**: 全部替换为 `except Exception:`。

**P2 — 中优先级**

4. **`auto_sapty_active` 拼写错误修正**：
   - 全文 11 处将拼写错误的 `auto_sapty_active` 统一重命名为 `auto_update_active`。

5. **提取 `_find_and_start_motion_path_operators` / `_stop_motion_path_operators`**：
   - **Issue**: `MOTIONPATH_ToggleCustomDraw.execute` 与 `update_custom_path_active` 中的启用/禁用逻辑几乎完全重复（共约60行），后者还含有无效的 `if found_view3d: pass` 死代码。
   - **Fix**: 提取为两个模块级辅助函数，两处共用；同时移除无效死代码。

6. **合并 `draw_enhanced_object_path` / `draw_enhanced_bone_path`**：
   - **Issue**: 两函数除 cache key 和 bone_name 参数外逻辑完全一致，违反 DRY 原则。
   - **Fix**: 合并为单一 `draw_enhanced_path(context, obj, parent_matrix, collector, bone=None)`（已与 P1-1 合并实现）。

7. **提取 `_build_ring_vertices` 辅助函数**：
   - **Issue**: `draw_origin_indicator` 中 `RING` 与 `RING_DOT` 样式的环形顶点生成循环代码完全重复（约20行）。
   - **Fix**: 提取为 `_build_ring_vertices(px, py, pz, scale, rx, ry, rz, ux, uy, uz, segments=32)`，两个样式分支共用。

8. **删除两个从未调用的死方法**：
   - `MOTIONPATH_AutoUpdateMotionPaths._has_selected_keyframes_changed` 和 `_get_selected_keyframes_state`（约25行）从未在 `modal` 中调用，直接删除。

**P3 — 低优先级**

9. **修复重复导入**：删除冗余的 `import bpy_extras` 和 `import bpy_extras.view3d_utils`，只保留 `from bpy_extras import view3d_utils`。

10. **`iface_` 简化**：从2行函数定义改为1行别名 `from bpy.app.translations import pgettext_iface as iface_`。

11. **删除 `HANDLE_SIZE = 10`**：定义后从未引用的死常量。

12. **同步 `bl_info` 版本号**：`(2, 0, 1)` → `(2, 1, 0)`，与 `blender_manifest.toml` 保持一致。

13. **清理过时注释**：移除 `# New: Path Drawing Data` 等开发期注释。

### Decisions
- **P1-1 在绘制函数重构中一并完成**：合并函数（P2-6）与 O(n×m) 优化（P1-1）在同一函数上操作，一次改完避免二次重构。
- **不修改 depsgraph handler 的交互避让逻辑**：该逻辑对 G/R/S 交互平滑度至关重要，修改风险高；对象选择切换问题通过 modal 检测解决（见上方 Bug Fix 条目）。

### Status
- **Improved**: 绘制热路径复杂度从 O(n×m) 降至 O(n+m)，关键帧多的场景性能显著提升。
- **Removed**: 约 60 行死代码/重复代码已删除。
- **Cleaned**: 全文异常处理、导入声明、常量定义、注释均已规范化。
- **No Regression**: 所有现有功能行为不变。

---

## 2026-02-25 23:00:00 (Origin Indicator Overlay)

### Context
用户反馈：插件绘制的运动路径会遮挡选中对象的原点 UI，导致用户在操作时难以定位对象原点。需要在运动路径层之上额外补充绘制一个当前选中对象/骨骼的原点指示器，并允许用户在插件首选项中自定义样式。

### Changes

1. **`MotionPathStyleSettings` 新增原点指示器属性**：
   - `show_origin_indicator`（BoolProperty）：整体开关，默认开启。
   - `origin_indicator_style`（EnumProperty）：样式选择，三选一：
     - `RING`：空心圆环（LINE_LOOP）
     - `DOT`：实心圆点（TRI_FAN）
     - `RING_DOT`：外环 + 中心实心小圆（默认，类似 Blender 原生原点样式）
   - `origin_indicator_size`（FloatProperty）：尺寸，4~40px，默认 12px。
   - `origin_indicator_color`（FloatVectorProperty RGBA）：外环/主体颜色，默认白色（0.9 透明度）。
   - `origin_indicator_inner_color`（FloatVectorProperty RGBA）：内点颜色，默认橙色，仅在 DOT / RING_DOT 样式下显示。

2. **新增 `draw_origin_indicator()` 函数**：
   - 插入在 `draw_motion_path_overlay()` 之前。
   - 坐标计算：
     - 对象模式：`obj.matrix_world.translation`（当前帧世界原点，实时跟随变换）。
     - 姿态模式（活动骨骼）：`(obj.matrix_world @ bone.matrix).translation`（骨骼头部世界坐标）。
   - 绘制逻辑：
     - `RING`：32 段 `LINE_LOOP`，线宽 2px，颜色使用 `origin_indicator_color`。
     - `DOT`：复用现有 `draw_billboard_circle()`，颜色使用 `origin_indicator_inner_color`。
     - `RING_DOT`：先绘制 32 段外环，再绘制 1/3 大小的中心实心圆。
   - 包含完整的数值合法性检查（`SAFE_LIMIT` / `math.isfinite`），防止 GPU 驱动崩溃。

3. **`draw_motion_path_overlay()` 追加调用**：
   - 在 `collector.draw(context)` 之后追加 `draw_origin_indicator()` 调用。
   - 确保原点指示器始终渲染在路径、关键帧点、手柄等所有元素之上。

4. **`MOTIONPATH_AddonPreferences.draw()` 新增 UI 分区**：
   - 在首选项末尾追加"Origin Indicator"分区。
   - 开关关闭时折叠所有子选项；样式为 RING 时隐藏内点颜色（不相关）。

### Decisions
- **实时坐标而非缓存坐标**：原点指示器使用 `matrix_world.translation`（当前帧实时值），而非位置缓存中的某帧数据，确保指示器始终反映对象在当前帧的真实位置。
- **绘制顺序保证**：通过在 `collector.draw()` 之后调用，利用 GPU 绘制顺序保证叠加在路径之上，无需额外深度测试控制。
- **RING_DOT 为默认样式**：外环 + 内点的组合与 Blender 原生原点显示风格一致，用户认知成本最低。

### Status
- **New Feature**: 原点指示器正常绘制于运动路径之上，对象模式和姿态模式均已支持。
- **Configurable**: 首选项中可自定义样式、大小、颜色，默认值开箱即用。
- **No Regression**: 未修改任何现有绘制逻辑，无回归风险。

---

## 2026-02-25 21:00:00 (Code Review — Docstring & Comment Cleanup)

### Context
对全面 Fast Path 迁移后的代码进行 Code Review，发现三处非功能性缺陷并修复。

### Issues Fixed

1. **`get_current_parent_matrix` 骨骼模式 docstring 与实现不符**：
   - **Issue**: POSE 骨骼模式的注释仍描述旧行为（"仍用 post-constraint 的 `bone.matrix` 计算"，"骨骼约束问题留待以后处理"），与已实现的新公式完全脱节。
   - **Fix**: 重写该注释，准确描述新公式语义：`bone.bone.matrix_local`（REST 姿态，稳定）× `bone.parent.matrix`（父骨骼 pose，含父骨骼约束），并说明对 drag 操作（`parent_rot_inv @ world_offset`）同样正确有效。

2. **`build_position_cache` 内注释编号重复**：
   - **Issue**: 函数内部有两个 `# 1.` 标注——原子锁和关键帧缓存分别都是 `# 1.`，与随后的 `# 2.`（路径线）形成逻辑混乱。
   - **Fix**: 将原子锁注释的 `# 1.` 前缀去掉，原子锁不是逻辑步骤，不参与编号。`# 1. Build Keyframe Cache` 和 `# 2. Build Path Line Batch` 现在连续清晰。

3. **`sorted(list(set(...)))` 中多余的 `list()` 包裹（历史遗留）**：
   - **Issue**: `sorted()` 直接接受任意可迭代对象，`list(set(...))` 的 `list()` 是无意义的转换开销。
   - **Fix**: `sorted(list(set(...)))` → `sorted(set(...))`。

### Status
- **No functional change**: 以上三处均为文档和注释层面，不影响运行逻辑。
- **Improved**: 代码可读性和注释准确性提升；docstring 与实现完全同步。

---

## 2026-02-25 20:00:00 (Unified Fast Path — Slow Path Removed)

### Context
经过对 Slow Path 实际作用的深入分析，发现其从根本上无法达成原始设计目标（捕获约束对位置的影响），因为它读取的是 `matrix_basis.translation`（约束介入前的数据），与直接读 F-Curve 等价。在此基础上，决定彻底废弃 Slow Path，统一走 Fast Path。

### Changes

1. **全面迁移到 Fast Path（`build_position_cache`）**：
   - **OBJECT 模式**：删除 `has_constraints`/`has_drivers`/`use_fast_path` 判断逻辑，直接调用 `calculate_path_from_fcurves`。
   - **POSE 模式关键帧缓存**：删除 `fast_bones`/`slow_bones` 分类逻辑及整个 Slow Path 处理块，所有骨骼统一调用 `calculate_path_from_fcurves`。
   - **路径线（path line）**：删除两套路径线的约束检查和 Slow Path 分支，统一使用 `calculate_path_from_fcurves`。

2. **删除 `frame_changed` 标志及帧恢复逻辑**：
   - `scene.frame_set()` 不再被调用，`frame_changed`、`current_frame`、`view_layer` 变量也一并移除。

3. **修复骨骼模式 `get_current_parent_matrix`**：
   - **Issue**: 旧公式 `(obj.matrix_world @ bone.matrix) @ bone.matrix_basis.inverted()` 与 Object 模式旧公式有相同问题——`bone.matrix` 含约束旋转，产生残差。
   - **Fix**: 改为从父级链推导：
     - 子骨骼：`obj.matrix_world @ bone.parent.matrix @ bone.bone.matrix_local`
     - 根骨骼：`obj.matrix_world @ bone.bone.matrix_local`
   - `bone.bone.matrix_local` 是 REST 姿态矩阵（不含约束），`bone.parent.matrix` 是父骨骼的 pose 矩阵（包含父骨骼自身的约束，符合预期）。

4. **更新 `build_position_cache` docstring**：清晰描述统一 Fast Path 的坐标系契约。

### Decisions
- **彻底废弃 Slow Path 的理由**：Slow Path 读 `matrix_basis.translation`（约束前），与 Fast Path 读 F-Curve 结果等价，没有实质差异，但有大量性能开销和交互干扰风险。
- **无 location F-Curve 的骨骼（IK 等）**：`frames` 集合为空，`continue` 跳过，不显示路径——行为正确。
- **bone.bone.matrix_local 的稳定性**：该矩阵是 REST 姿态数据，不随帧变化，不含约束，是正确推导骨骼父矩阵的基础。

### Status
- **Removed**: Slow Path 完全移除，`frame_set` 永远不再被调用。
- **Fixed**: 带旋转约束骨骼的路径不再偏转（骨骼 parent_matrix 修复）。
- **Improved**: 代码净减少约 70 行，逻辑大幅简化。
- **Maintained**: 所有 Fast Path 原有行为不变；Smart Interaction 缓存复用机制不变。

## 2026-02-25 18:00:00 (Constraint Coordinate Space Fix)

### Context
用户在测试中发现：对象（以圆锥 + 阻尼跟踪约束为例）启用约束后，尽管约束只改变旋转，运动路径也会跟随旋转，表现得像是以对象自身为父级。深入分析后还发现 Slow Path 读取的坐标与其设计意图不符。

### Root Cause Analysis

1. **`get_current_parent_matrix` 中的旋转污染**：
   - 旧公式：`parent_matrix = obj.matrix_world @ obj.matrix_basis.inverted()`
   - 问题：`obj.matrix_world` 已包含约束叠加的旋转，而 `obj.matrix_basis` 不含约束旋转，二者相除后产生"旋转残差"。
   - 后果：所有缓存路径点被这个残差矩阵错误旋转，路径看起来随物体旋转。
   - 本质：无父级对象 `matrix_world @ matrix_basis.inverted()` 理想情况下应等于 `Identity`，但有旋转约束时 `matrix_world ≠ matrix_basis`，结果不再是 `Identity`。

2. **Slow Path 读取的是约束前坐标（`matrix_basis`）**：
   - 旧行为：Slow Path 切帧后读 `obj.matrix_basis.translation`，这是约束介入**之前**的原始 F-Curve 值。
   - 后果：Slow Path 对位置约束（Copy Location、Follow Path）与 Fast Path 读 F-Curve 的效果完全相同，完全无法表现约束对位移的影响——Slow Path 的设计初衷被架空。

### Changes

1. **重写 `get_current_parent_matrix` 的 OBJECT 模式逻辑**：
   - **Fix**: 改为直接从父级链推导，不再依赖对象自身的 `matrix_world`。
   - 无父级 → 返回 `Identity`（F-Curve 坐标即世界坐标）。
   - 有父级 → 返回 `obj.parent.matrix_world`（含骨骼父级修正）。
   - **Effect**: 彻底消除旋转约束（阻尼跟踪、Look At 等）造成的路径偏转。

2. **修复 Slow Path 位置读取（对象关键帧缓存与路径线缓存）**：
   - **Fix**: `obj.matrix_basis.translation` → 读 `obj.matrix_world.translation`（无父级）或 `(parent_inv @ obj.matrix_world).translation`（有父级）。
   - **Effect**: Slow Path 现在能正确捕获 Copy Location、Follow Path 等位置约束的效果；旋转约束只改旋转，不改 `matrix_world.translation`，所以旋转约束不再对路径位置产生影响。

3. **坐标系契约（Coordinate Space Contract）统一**：
   - 所有缓存坐标均存储在"父级本地空间"：无父级 = 世界空间，有父级 = 相对于 `parent.matrix_world`。
   - `get_current_parent_matrix` 返回值含义与此保持一致。
   - 绘制公式 `point_3d = parent_matrix @ cached_pos` 在任何情况下都能得到正确的世界坐标。

### Decisions
- **为何不改骨骼模式**：骨骼的坐标系更复杂（`matrix_basis` 在骨骼父空间，需要整条骨骼链变换），本次变更聚焦在对象模式，骨骼模式留作后续专项优化。
- **Slow Path 的存在价值重新确认**：修复后，Slow Path 的 `matrix_world.translation` 读取方式终于能正确表现位置约束的效果，相较于 Fast Path 具有实质差异，本次保留合理。
  > **后记（2026-02-25 20:00）**：经进一步分析，即便修复后的 Slow Path 在理论上可捕获位置约束，其性能代价（`frame_set` 逐帧切换）和交互干扰风险依然存在，且对动画师的实际工作流收益有限。最终决定全面废弃 Slow Path，统一使用 Fast Path，详见 20:00 条目。
- **Fast Path 不受影响**：Fast Path 对象没有约束，`matrix_world = parent_world @ matrix_basis`，旧公式和新公式等价（Identity / parent_world），无回归风险。

### Status
- **Fixed**: 带旋转约束（阻尼跟踪等）的对象路径不再随旋转偏转。
- **Fixed**: Slow Path 现在正确捕获位置约束效果（Copy Location、Follow Path 等）。
- **Maintained**: Fast Path 对象行为不变。
- **Maintained**: 骨骼模式行为不变（骨骼模式的约束坐标问题留后续处理）。
- **Superseded**: Slow Path 于 20:00 条目中被完全废弃。

## 2026-02-25 14:00:00 (Smart Mode Interaction & Slow Path Fixes)

### Context
用户反馈在 **Smart Mode** 下，当对象（尤其是带有位移动画或约束的对象）进行交互操作（如 G 键移动）时，会出现“锁死”或路径消失的问题。而在 Timer Mode 下则正常。

### Changes
1.  **修复“对象锁死”问题 (Recursive Lock)**:
    -   **Issue**: `build_position_cache` 中的 `frame_set()` 操作会触发 `depsgraph_update`，进而再次调用 `on_depsgraph_update`，形成递归死循环或高频阻塞，导致对象无法移动。
    -   **Fix**: 引入原子锁机制 (`_is_updating_cache`)。将锁的管理逻辑下沉到 `build_position_cache` 内部，确保函数具有原子性，任何递归调用都会被直接拦截。

2.  **修复“交互时位置重置”问题 (Fast Path)**:
    -   **Issue**: `build_position_cache` 即使在 Fast Path（只读 F-Curve）下，函数末尾也无条件执行了 `view_layer.update()` 和 `frame_current` 恢复。这会强制刷新场景，导致 G 键操作产生的临时变换状态被重置，对象“一动不动”。
    -   **Fix**: 引入 `frame_changed` 标志。只有在真正执行了 `frame_set`（Slow Path）的情况下，才会在计算结束后恢复帧并刷新视图。对于 Fast Path，函数变为纯只读，不再干扰场景状态。

3.  **优化“智能交互避让”策略 (Smart Interaction Detection)**:
    -   **Issue**: Slow Path 对象（带约束）在交互时必须切帧计算，这必然会打断用户的交互操作。如果为了避免打断而跳过计算（罢工），路径线会消失。
    -   **Fix**:
        -   在 `on_depsgraph_update` 中检测更新来源：如果只有 `OBJECT` 更新而 `ACTION`（关键帧数据）未变，判定为“正在交互”（G 键移动中）。
        -   此时直接 `return`，完全不调用 `build_position_cache`。
        -   **Result**: 利用 `_state.position_cache` 的持久性，在交互期间直接复用上一帧的缓存数据进行绘制。
        -   **Effect**: 无论是 Fast Path 还是 Slow Path，交互时对象移动丝般顺滑，路径线保持静止（显示移动前的状态），待用户确认操作（Action 更新）后，路径自动刷新。

4.  **代码审查与清理 (Refactoring)**:
    -   移除未使用的导入 (`re`)。
    -   简化 `build_position_cache` 的入口检查逻辑。
    -   添加详细文档字符串，解释新的智能交互逻辑。

### Decisions
-   **Cache Reuse Strategy**: 相比于在交互期间尝试计算（可能导致卡顿或状态冲突），直接复用旧缓存是最高效且体验最好的方案。用户在移动物体时，通常关注的是物体本身的位置，路径线暂时不动是可以接受的（且符合逻辑，因为关键帧数据确实还没变）。
-   **Atomic Lock Placement**: 将锁放在计算函数内部比放在 Handler 里更安全，能防止任何来源的调用导致递归。

### Status
-   **Fixed**: Smart Mode 下对象不再锁死。
-   **Fixed**: Fast Path 和 Slow Path 对象在交互时均不再卡顿或重置。
-   **Optimized**: 代码结构更清晰，文档更完善。
-   **Verified**: 用户确认功能修复并接受代码审查优化。

## 2026-02-25 10:00:00 (i18n & Registration Fixes)

### Context
用户反馈在 Blender 5.0 中插件无法加载（注册错误）以及界面无法显示中文翻译。

### Changes
1.  **修复 EnumProperty 注册错误**:
    -   **Issue**: `motion_path_update_mode` 和 `handle_type` 的 `items` 参数使用了动态回调函数 `get_update_mode_items`，但在插件注册阶段，Blender 的翻译系统可能尚未完全初始化，导致 `EnumProperty` 注册失败。
    -   **Fix**: 将 `items` 改回静态列表定义 `motion_path_update_mode_items` 和 `handle_type_items`。
    -   **Result**: 插件可以正常加载，无报错。

2.  **修复国际化 (i18n) 问题**:
    -   **Issue**: 插件虽然使用了 `bpy.app.translations`，但在 Blender Extension 环境下（包名动态变化），原有的 `msgctxt=__package__` 导致上下文匹配失败，中文翻译无法显示。
    -   **Fix**:
        -   **Universal Context**: 在 `translations.py` 中，将所有翻译字典的键从 `("Context", "Original")` 或 `"Original"` 统一修改为 `("*", "Original")`。通配符 `*` 确保翻译在任何上下文下都能生效。
        -   **Remove msgctxt**: 在 `__init__.py` 的 `iface_` 辅助函数中，移除了 `msgctxt` 参数，直接调用 `pgettext_iface(msg)`，使其匹配通用上下文。
    -   **Result**: 插件界面（包括 Header 菜单、下拉选项、Operator 描述）现在能正确跟随 Blender 的语言设置显示中文。

### Decisions
-   **Static vs Dynamic Enum Items**: 虽然动态 Items 更灵活，但在不需要动态改变选项内容的情况下，静态列表更稳定，且能利用 Blender 的自动翻译机制。
-   **Universal Translation Context**: 针对 Blender Extension 这种包名不确定的环境，使用 `*` 上下文是最稳健的翻译策略，避免了硬编码包名带来的维护成本和兼容性问题。

### Status
-   **Fixed**: 插件加载错误已修复。
-   **Fixed**: 中文翻译已完全恢复。
-   **Verified**: 用户确认插件功能正常且界面已显示中文。

## 2026-02-24 22:00:00 (UI Optimization: Header Menu & Preferences Migration)

### Context
用户希望优化插件的 UI 布局，减少侧边栏（N-Panel）的占用，并将设置项根据使用频率进行重新分类和安置。

### Changes

1. **新增 Header 菜单入口**：
   - 在 Graph Editor / 3D Viewport 的 Header 菜单中增加插件快捷入口，用户无需打开 N-Panel 即可启停路径显示和切换更新模式。
   - 降低了高频操作的点击层级。

2. **设置项迁移到 Preferences**：
   - 将不常用的配置选项（颜色、线宽、点大小、帧间距等风格参数）从 N-Panel 移入插件的 Blender Preferences 面板。
   - N-Panel 仅保留核心开关和当前帧范围等高频参数，界面更简洁。

3. **设置项分类重组**：
   - 按"使用频率"重新分组：高频操作（启停、更新模式）放顶层；风格调整（颜色、粗细）放 Preferences；高级选项（FPS、缓存策略）也归入 Preferences。

### Decisions
- **Header vs N-Panel**：Header 菜单适合"一次性开关"类操作，N-Panel 适合需要长期可见的参数。遵循 Blender 自身的 UI 规范。
- **Preferences 作为低频设置的归宿**：Blender 的 Preferences 系统提供了持久化存储，适合风格类参数；同时减少了 N-Panel 的信息密度，降低认知负担。

### Status
- **Improved**: N-Panel 内容精简，操作路径更短。
- **Maintained**: 所有原有功能均可访问，无功能退化。
