# Smart Update 故障分析与修复计划

## 1. 故障深度分析 (Deep Analysis)

经过代码审查和逻辑推演，我们确认了 **Smart Update (智能更新)** 导致运动路径消失和严重卡顿的根本原因：**递归调用与重复计算 (Recursion & Double Calculation)**。

### A. 为什么会卡顿 (Lag)?
当您在 3D 视图中拖拽手柄时，发生了以下连锁反应：
1.  **Operator**: `MOTIONPATH_DirectManipulation` 修改了 F-Curve 数据。
2.  **Blender**: 检测到数据变化，触发 Dependency Graph (依赖图) 更新。
3.  **Handler**: `on_depsgraph_update` 监听到更新，立即调用 `build_position_cache`。
4.  **Operator**: 同时，您的鼠标移动事件 (`MOUSEMOVE`) 也调用了 `build_position_cache`（为了实时反馈）。

**结果**: 每一帧鼠标移动，`build_position_cache` 被执行了**两次**。
更糟糕的是，`build_position_cache` 内部可能会调用 `scene.frame_set()`，这会**再次**触发依赖图更新，导致 `on_depsgraph_update` **再次** 运行，形成潜在的**无限递归**或极高频的循环调用。

### B. 为什么路径会消失 (Disappear)?
在递归或高频调用中，如果 `build_position_cache` 被中断、或者上下文 (`context`) 在 Handler 中不正确（例如在 `frame_set` 过程中），`_state.position_cache` 可能被清空后未能正确填充。
此外，Operator 和 Handler 同时写入全局变量 `_state`，虽然 Python 是单线程的，但逻辑上的交错可能导致状态不一致。

## 2. 解决方案 (Fix Plan)

我们需要建立一套 **"互斥机制" (Mutual Exclusion)** 和 **"防递归锁" (Recursion Guard)**。

### 策略 1: 拖拽时禁用 Handler
当用户在 3D 视图中进行拖拽操作时（即 `_state.is_dragging` 或 `_state.handle_dragging` 为 True），Operator 已经全权负责更新了。
此时，**Handler 必须闭嘴**，不要插手。

### 策略 2: 防递归锁 (Re-entrancy Lock)
即使不在拖拽时（例如在 Graph Editor 编辑），`build_position_cache` 可能会改变帧，从而触发新的 Depsgraph 更新。
我们需要一个模块级的标志位 `is_updating_cache`，确保 Handler 不会因为自身的更新操作而再次触发自己。

## 3. 代码实施细节

### 修改 `__init__.py`

#### A. 添加全局锁
```python
# Global lock to prevent recursion in smart update
_is_updating_cache = False
```

#### B. 优化 `on_depsgraph_update`
```python
@persistent
def on_depsgraph_update(scene, depsgraph):
    global _state, _is_updating_cache
    
    # 1. Check Recursion Lock
    if _is_updating_cache:
        return

    # 2. Check Dragging State (Conflict Resolution)
    # If operator is handling it, we do nothing.
    if _state.is_dragging or _state.handle_dragging:
        return

    wm = bpy.context.window_manager
    if not wm.custom_path_draw_active or wm.motion_path_update_mode != 'SMART':
        return

    if depsgraph.id_type_updated('OBJECT') or depsgraph.id_type_updated('ACTION'):
        try:
            if bpy.context.active_object:
                # Set lock
                _is_updating_cache = True
                
                build_position_cache(bpy.context)
                
                for window in wm.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()
        except Exception as e:
            print(f"Error in smart update: {e}")
        finally:
            # Release lock
            _is_updating_cache = False
```

## 4. 预期效果
-   **3D 视图交互**: 流畅度恢复。因为拖拽时 Handler 会被屏蔽，只有 Operator 在受控 FPS 下运行。
-   **路径消失问题**: 解决。消除了并发/递归修改状态的风险。
-   **其他面板交互**: 依然有效。当您在 Graph Editor 操作时，Operator 不活动，Handler 会接管更新，且防递归锁会防止死循环。

## 5. 待办事项
- [ ] 在 `__init__.py` 顶部添加 `_is_updating_cache` 变量。
- [ ] 重写 `on_depsgraph_update` 函数，加入 `_state` 检查和 `_is_updating_cache` 锁。
