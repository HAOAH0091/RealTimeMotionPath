# 修复计划：Motion Path 手柄折角问题 (基于用户反馈修正)

## 1. 重新分析
用户提供了关键的观察信息：
1.  **现象**：在大幅度拖动手柄时，被拖动侧的手柄（Active Side）在 Graph Editor 中位置正确（仅 Y 轴变化，X 轴/时间锁死），但对侧手柄（Opposite Side）出现了“偏移”，导致关键帧处出现折角（不共线）。
2.  **关键线索**：用户指出“必须保证 Graph Editor 中手柄点的相对 X 轴位置不变，才能保证没有折角”。
3.  **根因推导**：
    *   当前的 `move_handle_point` 逻辑中，**被拖动手柄**的 X 轴（时间）是被锁定的（代码中只更新了 `[1]` 即 Value，重置了 `[0]` 即 Frame）。
    *   当前的 `update_opposite_handle` 逻辑采用的是 **“保持长度” (Length Preservation)** 算法：`new_pos = co + vec * old_length`。
    *   **冲突点**：当被拖动手柄仅在 Y 轴移动（改变斜率）时，如果要保持对侧手柄的长度不变，对侧手柄必须同时调整 X 和 Y 坐标（旋转）。
    *   这导致对侧手柄的 X 轴发生了移动。而在 Blender 的 F-Curve 编辑中，如果 X 轴发生意外移动，可能会导致手柄行为异常或视觉上的“偏移/折角”。
    *   **结论**：用户的建议是正确的。为了配合被拖动手柄“锁 X”的特性，对侧手柄也必须 **“锁 X”**，并通过调整 Y 轴来匹配斜率（这意味着对侧手柄的长度会发生变化，但这在 F-Curve 编辑中是更合理的行为）。

## 2. 解决方案
修改 `update_opposite_handle` 函数的算法，从 **“向量旋转（保长）”** 改为 **“斜率投影（保 X）”**。

### 核心改动
在 `update_opposite_handle` 中：
1.  计算被拖动手柄相对于关键帧中心 (`co`) 的 **斜率 (Slope)**。
    *   `slope = (co.y - handle_active.y) / (co.x - handle_active.x)`
2.  获取对侧手柄当前的 **X 轴偏移量**。
    *   `dx = handle_opposite.x - co.x`
3.  利用斜率计算对侧手柄新的 **Y 轴位置**，保持 X 轴不变。
    *   `new_y = co.y + (slope * dx)`
    *   `handle_opposite.y = new_y`
    *   `handle_opposite.x` 保持不变。

### 边界情况处理
*   **垂直手柄**：如果手柄垂直（`dx ≈ 0`），斜率计算会除以零。需要添加保护，或者在垂直情况下维持原状/特殊处理。但在 F-Curve 中，手柄通常不会完全垂直（因为是函数曲线）。

## 3. 执行步骤
1.  修改 `__init__.py` 中的 `update_opposite_handle` 函数。
2.  实现斜率投影逻辑，替换原有的向量长度逻辑。
3.  保留类型检查逻辑（仅对 `ALIGNED/AUTO` 生效）。
