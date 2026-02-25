# Motion Path Pro 重构分析报告：从世界坐标系转向本地坐标系

## 1. 背景与目标 (Background & Goal)

当前插件的运动路径（Motion Path）和手柄（Handles）绘制及交互是基于**绝对世界坐标系（World Space）**实现的。
这意味着插件需要计算每一帧物体的世界位置，并且在绘制手柄时，需要通过有限差分法（Finite Difference）来估算包含父级运动在内的“世界速度”，从而确定手柄的方向。

**用户痛点**：
- 当父级对象（Parent）也有动画变换时，世界坐标系下的路径和手柄形状会受到父级运动的复合影响。
- 在交互时（拖动手柄），由于参照系是动态变化的（父级在动），导致拖动操作“不跟手”（Slippery/Unpredictable）。
- 计算逻辑复杂，容易出现精度误差（如之前遇到的手柄跳变问题）。

**重构目标**：
- **推翻现有逻辑**，将核心参考系改为**本地坐标系（Local Space）**。
- 路径和手柄的数据均基于子对象相对于父对象的本地变换。
- 绘制时，利用父对象的**当前变换矩阵**将本地路径投射到视图中。
- 实现效果：路径形状仅反映子对象的本地动画曲线；当父对象移动/旋转时，整条路径作为一个整体跟随父对象移动（“挂”在父对象上），而不是每一帧都发生形变。

---

## 2. 现状分析 (Current State Analysis)

基于 `__init__.py` 的代码分析：

### 2.1 数据缓存 (`build_position_cache`)
- **当前逻辑**：
  - 遍历关键帧范围，调用 `context.scene.frame_set(f)`。
  - 获取 `obj.matrix_world`（世界坐标矩阵）。
  - 计算前后 0.01 帧的世界坐标，用 `(pos_next - pos_prev)` 计算**世界速度**。
  - 缓存数据包含：`position` (World), `parent_matrix` (World), `velocity` (World)。
- **问题**：
  - 强依赖 `frame_set` 和全场景求值，性能开销大。
  - “世界速度”混合了父级和子级的速度，难以逆向解耦回 F-Curve 的本地数据。

### 2.2 绘制逻辑 (`draw_motion_path_handles`)
- **当前逻辑**：
  - 读取缓存的**世界位置**和**世界速度**。
  - 手柄方向由**世界速度**决定（即切线方向）。
  - 手柄长度由 F-Curve 的本地手柄经过 `parent_matrix` 旋转后计算得出。
  - 最终在世界空间绘制。
- **问题**：
  - 视觉上，手柄是“真实轨迹”的切线。如果父级旋转很快，真实轨迹的切线可能与子级朝向完全不同，导致视觉上的手柄与物体本地轴向看似“分离”。

### 2.3 交互逻辑 (`move_selected_handles`)
- **当前逻辑**：
  - 获取鼠标在世界空间的位移 (`total_offset_world`)。
  - 获取**关键帧时刻**的父级矩阵 (`parent_matrix` from cache)。
  - 逆向计算本地位移：`delta_local = parent_matrix.inverted() @ delta_world`。
- **问题**：
  - 严重依赖缓存的 `parent_matrix`。如果缓存过期或精度不够，计算会出错。
  - 交互是基于“这一帧的世界状态”，但用户往往是在“当前帧”去编辑“那一帧”的数据，这种时间维度的错位感加剧了操作的不直观。

---

## 3. 重构方案 (Refactoring Proposal)

### 3.1 核心概念：本地坐标空间 (Local Space)

我们将不再关注物体最终在世界哪里，而是关注**物体相对于父级在哪里**。

- **对象 (Object)**: 使用 `obj.matrix_local` (即 `obj.parent.matrix_world.inverted() @ obj.matrix_world`)。
- **骨骼 (Bone)**: 使用 `pose_bone.matrix` (骨架空间) 或 `pose_bone.location` (父骨骼空间)。*建议统一使用“父级空间”概念。*

### 3.2 绘制逻辑变革

**旧模式 (World Baked)**：
$$ P_{draw}(t) = Matrix_{Parent}(t) \times P_{local}(t) $$
(点的位置被“烘焙”在它那个时间点的世界位置)

**新模式 (Parent Relative)**：
$$ P_{draw}(t) = Matrix_{Parent}(t_{current}) \times P_{local}(t) $$
(所有点都使用**当前帧**的父级矩阵进行变换)

- **优势**：
  - 无论父级怎么动，路径的**形状**保持不变（因为它只反映本地动画）。
  - 路径会像一个刚体一样“挂”在父级上，实时跟随父级当前的移动/旋转。
  - 手柄方向直接对应 F-Curve 的切线方向，不再受父级速度干扰。

### 3.3 数据获取优化

我们不再需要通过 `frame_set` 去计算世界速度。我们可以直接读取 F-Curve 数据！

1. **位置数据**：
   - 依然需要 `frame_set` 获取 `obj.matrix_local` (为了处理约束/驱动器对本地变换的影响)。
   - **优化**：如果确定没有驱动器/约束，可以直接用 `fcurve.evaluate(t)` 计算位置，速度极快（毫秒级）。*保守起见，第一版仍建议用 `frame_set` 读取 `matrix_local`。*

2. **手柄/切线数据**：
   - **直接读取 F-Curve**：`keyframe.co`, `keyframe.handle_left`, `keyframe.handle_right`。
   - 本地手柄向量 = `handle_right - co`。
   - 不需要计算速度！不需要有限差分！完全精准。

### 3.4 交互逻辑变革

当用户拖动手柄时：

1. **鼠标射线** $\rightarrow$ **世界目标点** ($P_{mouse\_world}$).
2. **世界转本地**：利用**当前父级矩阵** ($M_{parent\_current}$).
   $$ P_{target\_local} = M_{parent\_current}^{-1} \times P_{mouse\_world} $$
3. **应用数据**：直接将 $P_{target\_local}$ 应用于 F-Curve。

由于绘制和交互都使用同一个 $M_{parent\_current}$，由于 $M \times M^{-1} = I$，交互将非常精准、线性，没有任何“滑移”感。

---

## 4. 详细实施计划 (Implementation Plan)

### 步骤 1：重写数据缓存 (`build_position_cache`)
- **修改内容**：
  - 存储 `local_position` 而不是 `world_position`。
  - 对于 Object：存 `obj.matrix_local.translation`。
  - 对于 Bone：存 `obj.matrix_world.inverted() @ (obj.matrix_world @ bone.head)` (即骨架空间坐标，因为骨骼通常是在骨架空间绘制，或者相对于父骨骼)。
    - *更正*：为了统一，建议存储**相对于由于父级变换确定的参考系**的坐标。
    - 简单方案：存储 `obj.matrix_local`。绘制时乘上 `obj.parent.matrix_world`。
- **移除**：删除所有关于 `velocity_prev`, `velocity_next` 的计算代码。

### 步骤 2：重写绘制函数 (`draw_motion_path_overlay`)
- **修改内容**：
  - 获取当前的父级变换矩阵 `current_parent_matrix`。
    - Object: `obj.parent.matrix_world` (若无父级则为 Identity)。
    - Bone: `obj.matrix_world` (因为 PoseBone 坐标通常是在 Object 空间/Armature 空间)。*注：如果骨骼有父骨骼，需确认 F-Curve 是相对于谁。F-Curve 是相对于父骨骼的。但 Blender 绘制通常在 Object 空间。建议：将所有骨骼数据转换到 Object 空间缓存，绘制时应用 Object.matrix_world。*
  - 在 Shader 中设置 `uniform mat4 ModelMatrix` 或者在 Python 里手动 `current_parent_matrix @ local_point`。
  - **手柄绘制**：直接使用 `keyframe.handle_right - keyframe.co` 作为向量，经过 `current_parent_matrix` 旋转后绘制。

### 步骤 3：重写交互操作 (`MOTIONPATH_DirectManipulation`)
- **修改内容**：
  - `MOUSEMOVE` 事件中，获取鼠标对应的世界位置。
  - 获取 `current_parent_matrix`（即绘制时用的那个矩阵）。
  - 计算 `delta_local = current_parent_matrix.inverted().to_3x3() @ delta_world`。
  - 直接更新 F-Curve。

### 步骤 4：清理无用代码
- 删除有限差分逻辑。
- 删除旧的父级速度补偿逻辑。

---

## 5. 预期效果对比

| 特性 | 旧方案 (World Space) | 新方案 (Local Space) |
| :--- | :--- | :--- |
| **路径形状** | 随父级运动而扭曲 (真实世界轨迹) | 形状固定，随父级整体移动 (相对轨迹) |
| **手柄方向** | 世界速度切线 (含父级速度) | 本地 F-Curve 切线 |
| **父级动画影响** | 父级动，路径每一帧都变 | 父级动，路径整体平移/旋转 |
| **交互手感** | 复杂，可能有滑移 | 精准，所见即所得 |
| **性能** | 较慢 (需计算差分) | 较快 (直接读数据) |

## 6. 结论

这个重构方向是非常正确的。它将插件从“模拟器”（模拟真实轨迹）转变为“编辑器”（可视化编辑 F-Curve 数据）。对于动画师调整动作（尤其是角色动画、层级动画）来说，本地坐标系的视图更加直观且易于控制。

**建议立即执行重构。**
