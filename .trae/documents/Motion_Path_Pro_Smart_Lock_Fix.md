# Smart Mode 对象锁定问题修复计划

## 1. 深度分析与根本原因

### 现象
在 **Smart Mode** 下，只要对象有位移动画数据，用户尝试移动对象时会感到“锁死”或极其卡顿。切换到 Timer Mode 则正常。

### 根本原因：递归死循环 (Recursive Death Loop)
1.  **触发点**: 用户移动对象 -> Blender 触发 `depsgraph_update`。
2.  **处理程序**: `on_depsgraph_update` 被调用。它检查 `_is_updating_cache`（此时为 False），然后调用 `build_position_cache`。
3.  **计算函数**: `build_position_cache` 开始执行。
    *   为了计算路径，它可能需要遍历帧。
    *   在“慢速路径（Slow Path）”逻辑中（针对有约束或驱动的对象，或者特定条件下的普通对象），代码执行了 `context.scene.frame_set(f)`。
4.  **灾难发生**: `frame_set(f)` 会强制刷新场景，**立即再次触发** `depsgraph_update` 事件！
5.  **递归**: `on_depsgraph_update` 再次被调用。由于此时外层的 `_is_updating_cache` 锁是由 `on_depsgraph_update` 自己管理的，且在调用 `build_position_cache` 之前已经加锁，理论上应该能挡住。
    *   **但是**，如果 `build_position_cache` 是由其他地方（如 Operator）调用的，或者锁的粒度不够细，或者 `frame_set` 触发的更新在当前 Python 栈帧中被同步处理了，就可能导致问题。
    *   更严重的是，即使锁生效了，频繁的 `frame_set` 也会导致 Blender 的 UI 线程被大量计算任务阻塞，表现为“锁死”。

### 为什么 Timer Mode 没问题？
Timer Mode 是定时的（例如每 0.1秒一次），它不会因为一次 `frame_set` 就立即触发下一次计算。它有天然的“冷却时间”，所以不会形成死循环。

## 2. 修复方案：原子化锁管理 (Atomic Lock Management)

我们必须确保 `build_position_cache` 是一个**原子操作**，且绝不会引起递归更新。

### 策略 A: 锁下沉 (Lock Pushdown)
将 `_is_updating_cache` 的管理逻辑从 `on_depsgraph_update` 移动到 `build_position_cache` 内部。
无论谁调用 `build_position_cache`，它首先检查锁。如果没有锁，它就锁定自己，执行计算，然后解锁。

### 策略 B: 抑制更新 (Update Suppression)
在 `build_position_cache` 内部进行 `frame_set` 时，我们要明确知道“这是我引发的更新，请忽略”。

### 策略 C: 优化帧恢复 (Frame Restoration Optimization)
目前代码在计算结束后恢复当前帧：`context.scene.frame_current = current_frame`。这也会触发更新。

## 3. 实施步骤

1.  **修改 `build_position_cache`**:
    *   在函数入口处添加 `global _is_updating_cache`。
    *   如果 `_is_updating_cache` 为 True，直接返回（防止递归）。
    *   设置 `_is_updating_cache = True`。
    *   使用 `try...finally` 块包裹所有计算逻辑，确保在 `finally` 中 `_is_updating_cache = False`。

2.  **简化 `on_depsgraph_update`**:
    *   移除其内部的锁管理逻辑（因为已经下沉了）。
    *   保留对 `_is_updating_cache` 的检查（作为快速失败路径）。

3.  **验证**:
    *   在 Smart Mode 下，对有动画的对象进行 G 键移动，观察是否流畅。
    *   观察控制台是否有递归报错。

## 4. 代码变更预览

```python
def build_position_cache(context):
    global _state, _is_updating_cache  # Add global lock
    
    # Recursion Guard
    if _is_updating_cache:
        return

    _is_updating_cache = True  # Acquire Lock
    
    try:
        # ... 原有的计算逻辑 ...
        # 包括 frame_set 等操作
    finally:
        _is_updating_cache = False # Release Lock
```

```python
def on_depsgraph_update(scene, depsgraph):
    # ...
    if _is_updating_cache:
        return
    # ...
    # 直接调用，不再需要 try...finally 管理锁
    build_position_cache(context) 
```
