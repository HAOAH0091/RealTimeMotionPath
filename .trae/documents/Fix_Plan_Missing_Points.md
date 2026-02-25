# 帧点消失修复计划 (Fix Plan for Missing Frame Points)

## 1. 问题分析 (Analysis)

*   **现象**: 路径线（Red Line）和关键帧点（Keyframes）正常显示，但路径上的细分帧点（Frame Points, 小白点）消失了。
*   **原因**:
    1.  **前情提要**: 为了修复 Vulkan 驱动崩溃问题，我们在 `draw_motion_path_overlay` 中将传递给 GPU 的坐标数据从 `mathutils.Vector`（Blender 向量对象）强制转换为了 Python 原生 `tuple`（元组，即纯数字列表）。
    2.  **冲突点**: 绘制帧点时会调用 `get_pixel_scale` 函数来计算点的大小。该函数包含一行代码：
        ```python
        offset_pos = pos + right * 0.001
        ```
    3.  **类型错误**:
        *   `pos` 现在是 `tuple` (因为我们的修复)。
        *   `right` 是 `Vector`。
        *   在 Python 中，**`tuple` 不能直接与 `Vector` 相加**。这会抛出 `TypeError`。
    4.  **静默失败**: `draw_batched_billboard_circles` 函数外部包裹了 `try...except` 块（为了防止崩溃而加的），这个 `TypeError` 被捕获并忽略了，导致循环直接跳过，因此没有任何点被绘制出来。

## 2. 修复方案 (Solution)

我们需要修改 `get_pixel_scale` 函数，确保在进行加法运算前，数据的类型是兼容的。

### 修改代码
文件: `c:\Users\Windows\AppData\Roaming\Blender Foundation\Blender\5.0\extensions\user_default\Motion_Path_Pro\__init__.py`

将:
```python
offset_pos = pos + right * 0.001
```
修改为:
```python
# Ensure pos is a Vector for math operations
offset_pos = mathutils.Vector(pos) + right * 0.001
```

这会将 `pos`（无论是元组还是向量）统一转换为向量进行计算，从而修复加法错误。

## 3. 通俗解释 (Explanation for User)

**为什么点没了？**
这就好比我们之前的修复是把“特殊的乐高积木”（Vector）换成了“普通的木头积木”（Tuple）以防止机器卡死。
但是，计算“点的大小”的那台机器（`get_pixel_scale`）只懂得怎么把“乐高积木”拼在一起。当我们给它“木头积木”时，它拼不上去，就报错罢工了。因为我们有防崩溃机制，所以它没有让整个软件崩溃，而是选择默默地不干活（不画点）。

**怎么修？**
我们只需要在给那台机器送积木之前，给“木头积木”套上一个“乐高外壳”（`mathutils.Vector(pos)`），这样它就能正常工作了。
