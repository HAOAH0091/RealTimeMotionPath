# Slow Path 优化方案：保持旧数据 (No Strike)

确实，"罢工"（完全不画）会导致路径线在交互期间突然消失，体验很差。
您想要的效果是：**即使是 Slow Path，在交互期间也尽量画出东西来（哪怕是旧的），而不是消失。**

### 核心问题回顾
Slow Path 无法像 Fast Path 那样"只读 F-Curve 算出旧路径"。
*   Fast Path: 可以凭空算出旧位置。
*   Slow Path: 如果不切帧 (`frame_set`)，就**无法算出**任何位置（甚至是旧位置）。

**但是！**
我们有一个现成的宝贝：**缓存 (`_state.position_cache`)**。

### 解决方案：复用缓存 (Cache Reuse)

既然我们刚刚（在交互开始前）才计算过一次完整的路径，那份数据还在内存里呢！
当检测到交互（`is_interaction_update`）时：

1.  **Fast Path**: 继续算（因为它快且无害）。
2.  **Slow Path**:
    *   **不要罢工** (不要 `pass` 什么都不做)。
    *   **不要切帧** (不要 `frame_set`)。
    *   **直接保留现有数据**！
    *   既然我们不清除 `_state.position_cache`，也不覆盖它，那它里面存的就是上一刻（交互前）的路径数据。
    *   我们只需要确保 `build_position_cache` 在跳过计算时，**不会清空**现有的缓存。

### 代码审查
现在的 `build_position_cache` 开头有一句：
```python
    _state.position_cache = {}
    _state.path_vertices = []
```
这会在每次调用时清空缓存。这导致了"罢工"（如果不重新填数据，就没东西画了）。

### 修改计划

我们需要在检测到 `is_interaction_update` 时，**不仅跳过计算，还要跳过清空缓存的操作**。或者更简单地，如果检测到交互，对于 Slow Path 部分，直接**不做任何事情**（既不计算也不清空）。

但问题是，`build_position_cache` 是一个整体。如果我们在开头清空了，后面跳过了，那就真没了。

**策略调整**：
在 `build_position_cache` 开头：
1.  **不要无条件清空**。
2.  如果是 Fast Path，或者是全量更新，才清空并重算。
3.  如果是 Slow Path 且处于交互中，**保留旧数据**。

**更安全的做法**：
让 `build_position_cache` 只负责**更新**。
如果 Slow Path 分支决定跳过，它就不去动 `_state.position_cache` 里的那些条目。
但是 `_state.position_cache = {}` 这行必须改。

**修改方案**：
```python
def build_position_cache(context, is_interaction_update=False):
    # ...
    
    # 只有当非交互更新时，或者我们要重新计算所有东西时，才清空。
    # 但混合模式下（有些骨骼是 Fast，有些是 Slow），比较麻烦。
    
    # 更好的办法：
    # 创建一个新的临时缓存 new_cache。
    # 计算完后，用 new_cache 替换 _state.position_cache。
    # 如果是交互模式下的 Slow Path，我们从 _state.position_cache 里把旧数据抄过来（或者直接不处理，复用旧的）。
    
    # 最简单的改法：
    # 如果是 interaction_update，且对象需要 Slow Path，直接 return！
    # 这样函数提前结束，_state.position_cache 完全没被动过，还保留着上次的数据。
    # 这样 Fast Path 也不会运行了？
    # 不行，Fast Path 必须运行，因为它能实时响应（虽然也是旧数据，但它是新算的旧数据...听起来有点绕，但 Fast Path 的"旧数据"其实就是当前 F-Curve 的数据）。
    
    # 修正：
    # Fast Path 的"实时计算"其实算出来的就是旧位置（因为 Action 没变）。
    # 所以，直接复用缓存对于 Fast Path 也是一样的效果！
    
    # 结论：
    # 如果检测到 is_interaction_update (交互中)，且当前对象包含任何需要 Slow Path 的成分（有约束/驱动）：
    # 直接 RETURN！什么都不做！
    # 这样 _state.position_cache 保持原样。绘制代码会继续画旧的线。
    # 这就是您要的"保持旧数据"。
```

### 为什么 Fast Path 也可以直接 Return？
Fast Path 在交互期间（Action 没变），算出来的结果和缓存里的结果是一模一样的。
所以，**只要是交互期间，我们完全可以不计算，直接用缓存！**

这比我之前想的还要简单。
只要 `is_interaction_update` 为 True，我们就假装没听到，直接返回。
这样：
1.  **Fast Path**: 路径不动（显示旧的）。
2.  **Slow Path**: 路径不动（显示旧的）。
3.  **性能**: 极佳（完全不计算）。

**唯一例外**：
如果我们想要 Fast Path "实时响应" F-Curve 的变化（比如你在 Graph Editor 里拖曲线，同时看着 3D 视图），那这时候 `depsgraph` 会报告 `ACTION` 变了。
我们的逻辑是 `is_object_updated and not is_action_updated`。
如果是 Graph Editor 拖拽，`is_action_updated` 是 True，所以会触发重算。没问题。
如果是 G 键移动，`is_action_updated` 是 False，触发 `is_interaction_update`。此时 Action 没变，算出来的结果肯定也没变。
所以，**直接 Return 是安全的！**

### 终极简化版
在 `on_depsgraph_update` 里：
如果 `is_interaction_update` 为 True，**不要调用 `build_position_cache`**。
完事。

不需要改 `build_position_cache` 内部逻辑。只需要在调用前拦截。
之前我是传参进去，现在我连调都不调了。

### 确认逻辑
*   用户按 G 移动 -> `OBJECT` 变，`ACTION` 没变 -> `is_interaction_update = True`。
*   `on_depsgraph_update` 看到标志 -> 决定不调用计算。
*   `_state.position_cache` 保持不变。
*   `draw_handler` 继续画旧数据。
*   结果：对象动，线不动。完美。

**等等，之前为什么 Fast Path 能"跟随"？**
我在之前的回复说"Fast Path 算出来是旧数据"。
其实，如果用户开启了自动插帧，或者某种情况下 F-Curve 被临时修改了？不，G 移动期间 F-Curve 绝对是不变的。
所以 Fast Path 算出来的一定是旧数据。
既然算出来是旧的，那我何必算呢？直接用缓存不就行了？

**所以，策略调整为：在交互期间（Object 变但 Action 没变），彻底跳过更新。**

这将同时解决 Fast Path 和 Slow Path 的问题，且性能最好。
