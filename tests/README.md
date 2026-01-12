# 测试指南 (Testing Guide)

## 概述

本项目使用 `pytest` 作为测试框架，提供完整的单元测试和集成测试。

## 安装测试依赖

```bash
pip install pytest pytest-cov pytest-mock
```

## 运行测试

### 运行所有测试
```bash
pytest
```

### 运行特定目录的测试
```bash
# 只运行单元测试
pytest tests/unit/

# 只运行集成测试
pytest tests/integration/
```

### 运行特定测试文件
```bash
pytest tests/unit/test_exceptions.py
pytest tests/unit/test_data_provider.py
```

### 运行特定测试类或方法
```bash
# 运行特定测试类
pytest tests/unit/test_exceptions.py::TestExceptionHierarchy

# 运行特定测试方法
pytest tests/unit/test_exceptions.py::TestExceptionHierarchy::test_base_exception
```

### 使用标记运行测试
```bash
# 只运行单元测试（快速）
pytest -m unit

# 只运行集成测试
pytest -m integration

# 跳过慢速测试
pytest -m "not slow"

# 跳过需要网络的测试
pytest -m "not network"
```

## 测试覆盖率

### 生成覆盖率报告
```bash
# 运行测试并生成覆盖率报告
pytest --cov=quant --cov-report=html

# 查看覆盖率报告
open htmlcov/index.html
```

### 显示缺少覆盖的行
```bash
pytest --cov=quant --cov-report=term-missing
```

## 测试组织结构

```
tests/
├── conftest.py                 # 共享fixtures和配置
├── unit/                       # 单元测试（快速，隔离）
│   ├── test_exceptions.py      # 异常体系测试
│   ├── test_data_provider.py   # 数据提供者测试
│   └── test_backtest_components.py  # 回测组件测试
├── integration/                # 集成测试（较慢，可能需要外部资源）
│   └── ...
└── fixtures/                   # 测试数据和辅助文件
    └── ...
```

## 编写测试

### 测试命名规范
- 测试文件：`test_*.py`
- 测试类：`Test*`
- 测试方法：`test_*`

### 示例测试
```python
import pytest
from quant.core.exceptions import DataNotFoundError

class TestDataProvider:
    """测试数据提供者"""

    def test_valid_symbol(self):
        """测试有效的股票代码"""
        # 测试逻辑
        pass

    def test_invalid_symbol(self):
        """测试无效的股票代码"""
        with pytest.raises(DataNotFoundError):
            # 应该抛出异常的代码
            pass
```

### 使用Fixtures
```python
def test_with_fixture(sample_stock_data):
    """使用共享的fixture"""
    assert not sample_stock_data.empty
    assert 'close' in sample_stock_data.columns
```

## 测试最佳实践

### 1. 测试应该快速
- 单元测试应在毫秒级完成
- 使用mock避免真实的API调用
- 集成测试可以较慢，但也应在秒级完成

### 2. 测试应该隔离
- 每个测试独立运行
- 不依赖测试运行顺序
- 使用fixtures提供清洁的测试环境

### 3. 测试应该清晰
- 使用描述性的测试名称
- 遵循 Arrange-Act-Assert 模式
- 每个测试只测试一个概念

### 4. 使用适当的断言
```python
# 好的断言
assert result == expected_value
assert len(trades) == 5
assert 'error' in response

# 使用pytest的断言
with pytest.raises(ValueError):
    invalid_operation()

with pytest.warns(UserWarning):
    deprecated_function()
```

## 持续集成

测试应该在每次提交前运行：

```bash
# 提交前检查清单
pytest                          # 运行所有测试
pytest --cov=quant             # 检查覆盖率
pytest -m "not slow"           # 快速测试
```

## 调试失败的测试

### 详细输出
```bash
# 显示print输出
pytest -s

# 显示详细的错误信息
pytest -vv

# 在第一个失败时停止
pytest -x

# 显示最慢的10个测试
pytest --durations=10
```

### 使用调试器
```python
def test_something():
    result = complex_function()
    import pdb; pdb.set_trace()  # 设置断点
    assert result == expected
```

## 测试覆盖率目标

- **核心模块** (`quant/core/`): 目标 80%+
- **数据层** (`quant/data/`): 目标 70%+
- **策略层** (`quant/strategies/`): 目标 60%+
- **分析层** (`quant/analysis/`): 目标 50%+

## 参考资源

- [Pytest官方文档](https://docs.pytest.org/)
- [Pytest覆盖率插件](https://pytest-cov.readthedocs.io/)
- [Python测试最佳实践](https://docs.python-guide.org/writing/tests/)
