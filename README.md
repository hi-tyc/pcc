# pcc MVP (Windows AOT Python-subset Compiler)

目标：在 Windows 上从零实现一个 AOT 编译器 pcc：
输入 .py（Python 子集）→ 生成 C → 用 cl.exe 或 clang-cl 编译链接为 .exe。

## 当前 MVP 支持的 Python 子集

### 数据类型
- **任意精度整数（BigInt）**：支持超大整数运算，无溢出限制
  - 运算：`+ - *`
  - 比较：`== != < <= > >=`
- **字符串**：字面量、变量、拼接（仅 `+`）
- **布尔值**：比较运算的结果（int 类型的 0/1）

### 控制流
- `if ... else ...`
- `while ...`
- `for i in range(start, stop, step)`
- `break` / `continue`（在 while/for 循环内）

### 函数
- 函数定义与调用
- 递归支持
- 参数与返回值（当前仅支持 int 类型）

### 变量
- 赋值与变量声明
- 类型系统：int/str/bool 编译时类型检查
- 变量首次赋值决定类型，后续类型不一致会编译时报错

### 语句
- `print(expr)` - 打印整数或字符串
- `return expr` - 返回值
- 赋值语句 `x = expr`
- 表达式语句（函数调用）

### 表达式
- 整数常量（包括超大整数）
- 字符串字面量
- 变量引用
- 二元运算：`+ - *`（仅整数）
- 比较运算：`== != < <= > >=`
- 函数调用

### 限制
- **不支持**：`//` 和 `%` 运算符（编译时报错）
- **不支持**：`int + str` 或 `str + int`（编译时报错）
- **不支持**：字符串比较（编译时报错）
- **不支持**：类、列表、字典、元组等高级类型
- **不支持**：异常处理、模块导入、装饰器等

## 示例代码

```python
# 超大数运算
a = 100000000000000000000
b = 99999999999999999999
print(a + b)  # 199999999999999999999

# 字符串拼接
s = "hello"
t = "world"
print(s + " " + t)  # hello world

# 控制流
x = 10
if x > 5:
    print("big")
else:
    print("small")

# 循环
for i in range(5):
    print(i)

# 函数定义与调用
def add(a, b):
    return a + b

result = add(123456789, 987654321)
print(result)  # 1111111110
```

## 依赖安装（PowerShell）

### 1) Python

建议 Python 3.10+（任意方式安装均可）。用 winget：

```powershell
winget install -e --id Python.Python.3.12
```

### 2A) MSVC (推荐)

安装 Visual Studio Build Tools（包含 cl.exe + linker）：

```powershell
winget install -e --id Microsoft.VisualStudio.2022.BuildTools
```

安装完成后，用"x64 Native Tools Command Prompt for VS 2022"或"Developer PowerShell for VS 2022"打开终端，
确保 `cl.exe` 在 PATH 中：

```powershell
cl
```

### 2B) clang-cl（没有 VS 也尽量可用）

安装 LLVM：

```powershell
winget install -e --id LLVM.LLVM
```

注意：在 Windows 上链接通常仍需要 Windows SDK 的库（UCRT/Kernel32 等）。建议安装 Windows 11 SDK：

```powershell
winget install -e --id Microsoft.WindowsSDK.11
```

验证：

```powershell
clang-cl --version
```

## 构建与运行

### 方式 1：用 pcc CLI 一键 build

在仓库根目录：

```powershell
python -m pcc build .\tests\t02_print_multi.py -o .\out.exe
.\out.exe
```

可强制指定工具链：

```powershell
python -m pcc build .\tests\t02_print_multi.py -o .\out.exe --toolchain msvc
python -m pcc build .\tests\t02_print_multi.py -o .\out.exe --toolchain clang-cl
```

### 方式 2：只生成 C，再用 scripts/build.ps1 编译

```powershell
python -m pcc build .\tests\t01_print_1.py -o .\out.exe --emit-c-only
# 生成的 main.c 会在 build\... 目录下；CLI 会打印路径
# 然后你可以手工调用：
.\scripts\build.ps1 -MainC .\build\pcc_t01_print_1\main.c -OutExe .\out.exe
```

## 运行测试

一键测试（编译 + 执行 + 比对输出）：

```powershell
.\scripts\run_tests.ps1
```

## 测试覆盖

当前共有 33 个测试用例，覆盖：
- 基础打印（t01-t06）
- 条件语句（t07-t09）
- 循环（t10-t12）
- 函数与递归（t13-t18）
- break/continue（t19-t21）
- for range（t22-t25）
- 字符串（t26-t29）
- BigInt 运算（t30-t33）

## 技术细节

### BigInt 实现
- 使用 base=10^9 的小端存储
- 支持任意精度整数运算
- 自动内存管理

### 代码生成
- 直接生成结构化 C 代码
- 不引入 VM、CFG、SSA
- 类型安全的编译时检查

### 运行时
- `runtime.h` / `runtime.c` 提供基础运行时支持
- 包含 BigInt 和字符串操作函数
- MSVC 和 clang-cl 兼容

@auther:@hi_tyc,@hi_zcy
