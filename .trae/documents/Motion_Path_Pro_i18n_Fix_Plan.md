# 翻译修复与调试计划

## 目标
解决 Blender 5.0 中插件无法显示中文翻译的问题。

## 分析
当前使用了 `bpy.app.translations.register(__package__, dict)` 和 `pgettext_iface(msg, msgctxt=__package__)`。
在 Blender Extension 环境下，`__package__` 可能包含复杂的命名空间（如 `bl_ext.user_default.Motion_Path_Pro`），导致 context 匹配变得脆弱。
最稳健的解决方案是使用通配符 Context `*`，这样无论插件被如何加载（Legacy Addon 或 Extension），翻译都能生效。

## 计划步骤

### 1. 修改 `translations.py`
将翻译字典的键从简单的字符串 `"Msg"` 改为元组 `("*", "Msg")`。
这明确指定了这些翻译属于通用 Context (`*`)，不依赖于具体的包名或模块名。

**当前格式**:
```python
translations_dict = {
    "zh_HANS": {
        "Motion-path pro": "运动路径 Pro",
        ...
    }
}
```

**目标格式**:
```python
translations_dict = {
    "zh_HANS": {
        ("*", "Motion-path pro"): "运动路径 Pro",
        ...
    }
}
```

### 2. 修改 `__init__.py`
1.  **更新 `iface_` 函数**: 移除 `msgctxt` 参数，直接调用 `pgettext_iface(msg)`。当字典中使用 `*` context 时，查找时不需要指定 context 也能匹配（或者指定特定 context 也能回退到 `*`，但最好是不指定）。
2.  **验证注册**: 保持 `translations.register(__package__)` 不变，因为字典内的 `*` 会覆盖默认 context。

### 3. 验证
用户重启 Blender 后，检查 Header 菜单和下拉选项是否显示中文。

## 执行细节
由于 `translations.py` 内容较多，我将使用脚本或精确的查找替换来批量修改字典格式。
同时，我会确保 `translations.py` 的编码声明和导入保持正确。
