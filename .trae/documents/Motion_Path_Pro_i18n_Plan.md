# 插件国际化修复计划

## 问题分析
用户反馈 Blender 设置为中文时，插件界面仍然显示为英文。
从提供的截图看，主要涉及 Header 菜单中的 "Update Mode"、"Smart (Event)"、"Timer (Polling)"、"Interaction FPS" 等文本。
此前为了修复注册错误，我们将 `EnumProperty` 的 `items` 从动态 `iface_()` 调用改为静态字符串列表。这可能导致了翻译失效，或者原本的翻译注册机制就存在问题。

需要排查以下几点：
1.  `translations.py` 中的翻译字典是否包含所有需要翻译的词条。
2.  `__init__.py` 中是否正确注册了翻译模块。
3.  UI绘制代码（`draw` 函数）中是否使用了翻译函数（如 `iface_` 或 `pgettext`）。
4.  `EnumProperty` 的静态项是否能被 Blender 自动翻译，或者需要特定的上下文。

## 待执行任务

### 1. 代码审计
- [ ] 检查 `c:\Users\Windows\AppData\Roaming\Blender Foundation\Blender\5.0\extensions\user_default\Motion_Path_Pro\translations.py`，确认所有英文字符串都有对应的中文翻译。
- [ ] 检查 `__init__.py` 中的 `register` 和 `unregister` 函数，确认 `translations.register` 被正确调用。
- [ ] 检查 UI 面板类（如 `MOTIONPATH_PT_header_settings`）的 `draw` 方法，确认文本标签是否使用了翻译函数。

### 2. 翻译机制修复
- [ ] **针对 EnumProperty**: Blender 的 `EnumProperty` 如果使用静态列表，通常会自动在 UI 显示时尝试翻译 `name` 和 `description`，前提是这些字符串在翻译字典中。如果失效，可能需要确认 context 是否匹配（通常是 `*` 或插件包名）。
- [ ] **针对 UI 标签**: 确认 `layout.label(text="...")` 中的文本是否被包裹在翻译函数中，或者依赖 Blender 的自动翻译（通常插件需要显式调用翻译）。
- [ ] **修复方案**:
    - 确保 `translations.py` 字典结构正确。
    - 在 UI 绘制代码中，对于动态生成的文本或直接传递给 UI 布局的文本，显式使用 `bpy.app.translations.pgettext_iface` 或类似机制。
    - 对于 `EnumProperty`，尝试恢复 `iface_` 但确保在模块级别定义时不报错，或者确认 Blender 是否能自动翻译静态定义的 Enum items。

### 3. 验证
- [ ] 模拟修复后的代码结构。
- [ ] 确保修改不会再次导致注册错误。

## 解决方案预演
如果 `EnumProperty` 的静态定义导致无法翻译，我们可以尝试：
1.  使用 `bpy.app.translations.pgettext_iface` 包裹字符串，但要确保它在运行时被调用，而不是在模块加载时（模块加载时 context 可能未准备好导致报错，这就是之前报错的原因）。
    - *修正*: 之前报错是因为 `iface_` 返回的是字符串，但在注册期间调用可能早于翻译系统初始化？或者是因为 `iface_` 在定义类属性时被立即求值了。
2.  最稳妥的方式是保留静态字符串，但确保 `translations.py` 注册的字典可以被 Blender 查找到。Blender 插件翻译通常注册到 `__package__` 名字空间下。

我们将首先检查 `translations.py` 和 `__init__.py` 的当前状态。
