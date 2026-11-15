# ScreenPenPlus
在整个屏幕上进行涂画（Draw on the screen）

为了简洁，工具条上只有8个按钮：操，笔，擦，撤，重，清，设

**操：** 操作（正常操作计算机，但程序不会退出。⚠这会清空所有痕迹）
**笔：** 画笔（让鼠标在屏幕上涂画。）
**擦：** 擦除（鼠标拖动以擦除之前留下的痕迹。）
**撤：** 撤销（返回上一步操作。）
**重：** 重做（重新进行撤销的操作。）
**清：** 清空（清空屏幕上的所有痕迹。）
**设：** 设置（弹出一个菜单，选择颜色、粗细等。）

### **⚠注意：**
1. uiaccesstools.exe只是用来提权到uiaccess作为更高级的置顶方法。不提供源代码。在程序是py源代码时禁用。
2. 笔的快捷键是"p"，擦的快捷键是"e"。
3. 程序部分由AI生成。
4. 程序中设置是由一个菜单进行，弹出在工具条左上角。


### 用到的python库
- os
- subprocess
- sys

这两个用于**提权**至uiaccess。

- math

用于计算绘画轨道。

- sys
- PyQt6

用于实现界面（有QApplication(sys.argv)）。

- ctypes

用于实现窗口属性

大部分时标准库，但需要：
```
pip install PyQt6
```
慢的话：
```
pip install PyQt6 -i https://pypi.tuna.tsinghua.edu.cn/simple
```
