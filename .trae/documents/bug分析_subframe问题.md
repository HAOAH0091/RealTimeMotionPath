# 🎯 问题分析：为什么手柄只有一端？

## 1. 现象复现
用户反馈：
1.  **所有关键帧**都只有一端有手柄（只有右手柄）。
2.  **末尾帧**依然完全没有手柄（左手柄也没了）。

## 2. 代码审查
我们在 `build_position_cache` 函数中使用了这样的代码来获取“上一帧”的时间点：

```python
context.scene.frame_set(int(frame), subframe=-0.01)
```

## 3. 原因定位
Blender 的 API `scene.frame_set(frame, subframe=0.0)` 对 `subframe` 参数有严格要求：
-   `subframe` 必须在 **0.0 到 1.0** 之间。
-   如果我们传入负数（如 `-0.01`），Blender 并不会自动借位到上一帧，而是**直接忽略负号或钳制为0**。

### 结果推演：
1.  **计算前一帧位置**：
    -   预期：`frame - 0.01`
    -   实际：`frame_set(frame, subframe=0)` -> **当前帧**
    -   导致 `pos_prev` == `pos_curr`。
    -   导致 `velocity_prev` = `(pos_curr - pos_prev) / 0.01` = **0**。

2.  **计算后一帧位置**：
    -   代码：`frame_set(int(frame), subframe=0.01)`
    -   这是正确的。
    -   导致 `velocity_next` 计算正确。

### 结论：
-   因为 `velocity_prev` 恒为0，所以**所有左手柄都不显示**。
-   因为末尾帧只有 `velocity_prev`（`velocity_next` 因钳制也为0），所以**末尾帧完全没有手柄**。
-   中间帧因为 `velocity_next` 正常，所以**只有右手柄**。

这完美解释了用户看到的所有现象。

## 4. 修复方案
我们需要正确计算 `frame` 和 `subframe`：

```python
prev_time = frame - 0.01
next_time = frame + 0.01

# 正确设置上一帧时间
context.scene.frame_set(int(prev_time), subframe=prev_time - int(prev_time))
# 正确设置下一帧时间
context.scene.frame_set(int(next_time), subframe=next_time - int(next_time))
```
例如：
-   `frame = 10`
-   `prev_time = 9.99` -> `frame_set(9, subframe=0.99)` -> **正确！**
-   `next_time = 10.01` -> `frame_set(10, subframe=0.01)` -> **正确！**

我将立即应用此修复。
