# 性能优化与帧率控制计划

## 1. 核心目标
在不牺牲现有功能稳定性的前提下，通过引入 **"智能更新模式"** 和 **"全局 FPS 限制"**，显著降低插件在静止和交互时的硬件功耗。

## 2. 深度风险分析 (Risk Analysis)

在实施优化前，我们必须清醒地认识到潜在风险并制定规避策略：

### A. 关于 "Smart Update" (智能更新)
*   **风险 1: 漏检测 (Missing Updates)**
    *   *场景*: 某些特殊操作（如通过 Python 脚本修改、撤销/重做、特定的快捷键组合）可能不会触发标准的 depsgraph 事件。
    *   *后果*: 3D 视图中的路径与实际数据不一致，误导用户。
    *   *规避*: 保留 **Timer Mode (Legacy)** 作为兜底方案。在 UI 中明确标注 Smart Mode 为 "推荐"，但允许用户切回 Timer Mode。同时，在 Smart Mode 中监听尽可能广泛的事件类型。
*   **风险 2: 过度触发 (Over-triggering)**
    *   *场景*: 播放动画时，每一帧都会触发 depsgraph 更新。
    *   *后果*: 如果在播放时进行重重的路径计算，会导致播放帧率下降。
    *   *规避*: 在 `depsgraph_update_post` 回调中，首先检查 `screen.is_animation_playing`。如果正在播放动画，则**暂停**路径的实时重算（或降级为低频更新），因为播放时用户通常关注的是动画效果而非路径编辑。

### B. 关于 "全局 FPS 上限" (Unified FPS Limit)
用户希望将 "拖拽帧率" 和 "视图绘制" 统一限制。
*   **技术限制说明**: Blender 的视图绘制 (`draw_handler`) 是由宿主程序控制的（通常垂直同步于 60/144Hz）。插件**不能**直接跳过某帧的绘制，否则会导致画面闪烁（物体消失一帧）。
*   **实现策略**: 我们通过限制 **"请求重绘的频率" (`tag_redraw`)** 和 **"计算数据的频率"** 来间接达到 FPS 限制的效果。
*   **风险 1: 高刷屏体验下降**
    *   *场景*: 用户使用 144Hz 显示器，但将插件限制在 60 FPS。
    *   *后果*: 拖拽手柄时，手柄的移动会有肉眼可见的"残影"或不流畅感（相比于原生光标）。
    *   *规避*: 默认值设为 60（平衡点），但允许最大设为 144。
*   **风险 2: 快速拖拽时的轨迹断层**
    *   *场景*: 鼠标极速移动，而 FPS 限制导致中间采样点丢失。
    *   *后果*: 路径变化看起来是"跳变"的而不是平滑过渡。
    *   *规避*: 确保在鼠标释放 (Release) 的那一瞬间，强制进行一次高精度的最终计算和重绘。

---

## 3. 详细实施方案 (Implementation Specs)

### 模块 1: 统一 FPS 设置 (Unified FPS Settings)
在 `__init__.py` 中添加统一的控制参数，取代零散的设置。

*   **属性名**: `wm.motion_path_fps_limit`
*   **类型**: IntProperty
*   **范围**: Min 1, Max 144
*   **默认值**: 60
*   **UI 显示**: "Max FPS Limit" (FPS 上限)
*   **作用范围**:
    1.  **拖拽交互**: 限制 `MOTIONPATH_DirectManipulation` 的计算和重绘频率。
    2.  **自动更新 (Timer Mode)**: 限制后台轮询的频率（如果是 Smart Mode 则忽略此值，由事件驱动）。

### 模块 2: 智能更新模式 (Smart Update Mode)
重构 `MOTIONPATH_AutoUpdateMotionPaths` 操作符。

*   **新增属性**: `wm.motion_path_update_mode`
    *   Enum: `['SMART', 'TIMER']`
    *   Default: `'SMART'`
*   **逻辑分支**:
    *   **IF TIMER**: 保持现有逻辑，使用 `1.0 / fps_limit` 作为定时间隔。
    *   **IF SMART**:
        *   注册 `bpy.app.handlers.depsgraph_update_post`。
        *   回调函数 `on_depsgraph_update(scene, depsgraph)`:
            *   检查 `depsgraph.id_type_updated('OBJECT')` 或 `('ACTION')`。
            *   如果相关物体更新 -> 触发缓存重建 -> `tag_redraw`。
            *   **防抖动 (Debounce)**: 如果在极短时间内连续触发（小于 1/60秒），合并为一次更新。

### 模块 3: 拖拽性能优化 (Interaction Optimization)
修改 `MOTIONPATH_DirectManipulation.modal` 方法。

*   **引入时间控制**:
    ```python
    target_interval = 1.0 / context.window_manager.motion_path_fps_limit
    current_time = time.time()
    
    # 只有当时间间隔满足要求时，才进行计算和重绘
    if (current_time - self._last_draw_time) > target_interval:
        # 1. 执行鼠标位置计算
        # 2. 更新手柄位置数据
        # 3. 强制重绘 context.area.tag_redraw()
        self._last_draw_time = current_time
    else:
        # 跳过，节省 CPU/GPU
        pass
    ```

## 4. 预期改进对比

| 指标 | 优化前 | 优化后 |
| :--- | :--- | :--- |
| **静止功耗** | **10Hz 持续轮询** (Timer Mode) | **0Hz** (Smart Mode) |
| **拖拽 FPS** | **无限制** (可达 300+ FPS) | **锁定 60 FPS** (可自定义) |
| **高刷屏功耗** | 极高 (满载运行) | 低 (按需运行) |
| **功能稳定性** | 依赖定时器 | 双模式保障 (Smart + Timer) |

## 5. 待办事项 (Todos)
- [ ] **Core**: 在 `__init__.py` 中添加 `motion_path_fps_limit` 和 `motion_path_update_mode` 属性。
- [ ] **UI**: 在 `MOTIONPATH_CustomDrawPanel` 中添加 "Performance" 子面板，暴露上述设置。
- [ ] **Logic (Drag)**: 重构 `MOTIONPATH_DirectManipulation`，实现基于时间的 FPS 限制。
- [ ] **Logic (Update)**: 实现 `depsgraph_update_post` 监听器逻辑，完成 Smart Mode。
- [ ] **Cleanup**: 移除旧的 `auto_midawq_timer_interval` 及其相关逻辑（确保平滑迁移）。
- [ ] **Test**: 验证 Smart Mode 在 Graph Editor、Dope Sheet 操作下的响应情况。
