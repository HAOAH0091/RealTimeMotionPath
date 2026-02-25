# Smart Mode "一动不动" 问题修复计划

## 1. 现象复盘
您在 Smart Mode 下按 G 键移动对象，对象**纹丝不动**。
而在 Timer Mode 下正常。
这说明 Smart Mode 的某些操作**强行重置**了对象的交互状态。

## 2. 深度病理分析 (Why is it stuck?)

当您按 `G` 键移动物体时，您处于 **Blender 的变换模态 (Transform Modal)** 中。此时，您看到的对象位置是一个**临时状态**（还没有写入关键帧）。

在 Smart Mode 下，您的鼠标移动触发了 `depsgraph_update`，进而触发了 `build_position_cache`。

**凶手找到了**：在 `build_position_cache` 函数的最后，有这样两行代码：
```python
    context.scene.frame_current = current_frame  # 恢复帧
    view_layer.update()                          # <--- 凶手！强制刷新视图层
```

*   **即使是 Fast Path (快速模式)**，代码虽然没有切帧，但最后依然执行了 `view_layer.update()`。
*   `view_layer.update()` 会告诉 Blender："请根据当前的动画数据（关键帧）重新计算所有对象的位置。"
*   **冲突**: 动画数据说"对象在原点"，您的 G 键说"对象在 (10, 0, 0)"。
*   **结果**: `view_layer.update()` 的权限高于 G 键的临时预览，于是它把对象**拽回**了原点。
*   这就是为什么您感觉对象"一动不动"——它每一帧都被尝试移动，然后瞬间被重置回去了。

## 3. 修复方案 (手术级精准修复)

我们需要确保：**如果是 Fast Path（绝大多数情况），绝对不要触碰场景的时间轴和视图更新状态。**

### 修改逻辑：
1.  引入一个标志位 `frame_changed = False`。
2.  只有在必须进入 **Slow Path**（有约束/驱动）时，才调用 `scene.frame_set()`，并将 `frame_changed` 设为 True。
3.  **移除** 函数末尾无条件的 `view_layer.update()`。
4.  **仅当** `frame_changed` 为 True 时，才恢复当前帧 `context.scene.frame_current = current_frame`。
    *   注意：恢复帧后通常需要 update，但在交互期间，我们可能宁愿不 update 也不要重置对象。或者，只有在 Slow Path 这种破坏性操作后才 update。
    *   更安全的做法是：**完全移除末尾的 `view_layer.update()`**。因为 `frame_current` 的赋值本身就会标记场景为 dirty，Blender 会在下一个循环自动处理，不需要我们强制 update。

### 预期效果
*   **Fast Path (无约束对象)**: 插件只读取数据计算路径，**完全不干扰** 场景状态。G 键移动将丝般顺滑。
*   **Slow Path (有约束对象)**: 必须切帧计算，可能依然会有冲突，但在交互期间（Smart Mode）可能需要进一步策略（如检测到交互就跳过更新）。但首先解决 Fast Path 的问题。

## 4. 实施代码预览

```python
def build_position_cache(context):
    # ... (前置锁代码) ...
    
    frame_changed = False # <--- 新增标志位
    
    # ...
    
    # Fast Path 分支
    if use_fast_path:
        # 纯数学计算，不碰场景
        path_data = ...
    else:
        # Slow Path 分支
        frame_changed = True # <--- 标记已修改
        for frame in frames:
            context.scene.frame_set(int(frame))
            # ...
            
    # ... (Line Drawing 逻辑同理) ...
    
    # 结尾恢复逻辑优化
    if frame_changed:
        context.scene.frame_current = current_frame
        # 移除 view_layer.update()，避免重置交互状态
```
