# Slow Path 优化方案：基于操作来源的智能判断

您的思路非常清晰且具有启发性！

确实，我们不需要精确知道用户是不是按了 G 键。我们只需要知道：**这次 `depsgraph_update` 是谁引发的？**

### 1. 核心判断依据
*   **如果是 F-Curve 变了**：说明用户在调整动画曲线（比如在 Graph Editor 里拖动关键帧），或者在插件里拖动了路径点。这时候，我们需要重新计算路径。
*   **如果是 Object Transform 变了**：说明用户在移动对象（G/Gizmo）。
    *   **关键点**：如果用户正在移动对象（交互中），此时去跑 Slow Path（切帧计算）是**危险且无意义的**。因为对象的位置是临时的，切帧会打断它。
    *   **策略**：对于 Slow Path 对象，如果是 TRANSFORM 引起的更新，**直接跳过计算**（或者只读旧数据）。

### 2. 如何区分？
在 `on_depsgraph_update` 中，我们可以通过 `depsgraph.id_type_updated('ACTION')` 和 `('OBJECT')` 来区分。

*   **Case A: 仅 ACTION 更新**
    *   **场景**: 用户编辑关键帧、拖动 F-Curve、或者我们的插件修改了关键帧数据。
    *   **处理**: **必须更新**。无论是 Fast 还是 Slow，都应该算，因为数据变了，路径得跟着变。而且这种操作通常不涉及视图交互冲突。

*   **Case B: 仅 OBJECT 更新 (或 OBJECT+ACTION)**
    *   **场景**: 用户在 3D 视图中移动对象 (G/Gizmo)。
    *   **处理**:
        *   **Fast Path**: 继续算（无害，且能实时预览路径变化，虽然路径其实没变）。
        *   **Slow Path**: **跳过！** (这就是您想要的逻辑)。
            *   为什么跳过？因为 Slow Path 需要 `frame_set`，这会重置交互。
            *   跳过意味着什么？路径线保持在上一帧的状态（旧线）。
            *   用户体验：对象移动很流畅，路径线暂时不动。等用户松手确认（写入关键帧/Action更新）后，路径线再刷新。

### 3. 实施方案

我们需要在 `on_depsgraph_update` 中传递这个上下文信息给 `build_position_cache`，或者直接在 Handler 里做拦截。

**修改逻辑**：
1.  在 `on_depsgraph_update` 中检测更新类型。
2.  如果是 **Slow Path 对象**（有约束/驱动）：
    *   如果检测到是 `OBJECT` 变换引起的更新（而 `ACTION` 可能没变，或者我们认为交互优先）：
    *   **不执行 `frame_set`**。
    *   或者干脆**不执行 `build_position_cache`**。

但是，`depsgraph.id_type_updated` 有个问题：当你移动对象时，如果开启了自动插帧，Action 也会跟着变。
不过，通常 G 移动过程中（未确认），Action 是不变的。只有确认那一瞬间 Action 才变。

**更精准的策略**:
我们可以在 `build_position_cache` 内部判断：
"如果是 Slow Path，且当前并没有明确的 Action 变化信号（或者我们处于一种保守模式），我就不切帧了。"

**最简单的实现**:
在 `build_position_cache` 的 Slow Path 分支前加一个判断：
如果 `context.mode == 'OBJECT'` 且 `depsgraph.id_type_updated('OBJECT')` 但 `not depsgraph.id_type_updated('ACTION')`：
说明用户正在移动对象（且没插帧），此时 Action 数据没变。
-> **Slow Path 直接跳过计算（return）**。

### 4. 预期效果
*   **Fast Path**: 照常工作（只读 F-Curve，流畅）。
*   **Slow Path**:
    *   当您 G 移动对象时：插件检测到只有 Object 变了，Action 没变 -> **跳过计算**。
    *   对象移动流畅，路径线保持不动。
    *   当您左键确认（写入关键帧）时：Action 变了 -> **触发计算**。
    *   路径线刷新到新位置。

这完美符合您的需求！

### 代码变更预览

在 `on_depsgraph_update` 中：

```python
    # ...
    is_action_updated = depsgraph.id_type_updated('ACTION')
    is_object_updated = depsgraph.id_type_updated('OBJECT')
    
    # 如果只是对象动了（G操作），但数据没变
    if is_object_updated and not is_action_updated:
        # 对于 Slow Path 对象，直接忽略这次更新
        if is_slow_path_object(obj):
             return
```

我们需要提取一个 `is_slow_path_object` 的判断逻辑。
或者更简单，把这个判断放进 `build_position_cache` 的 Slow Path 分支里。
