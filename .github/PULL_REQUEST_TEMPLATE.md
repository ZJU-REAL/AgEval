## 摘要

<!-- 改了什么、为什么。机制/产品语义变更须先改 docs/design（或说明已改）。 -->

## 关联

- Issue：
- 证据等级（若声称）：

## 验证

```bash
# 实际跑过的命令（pytest / bora lock|run / validate…）
```

## Checklist

- [ ] 未把 credential / token 写入 yaml、lock、evidence、示例
- [ ] 未把 trajectory / `HarnessTerminal.completed` 当作 PASS
- [ ] 产品/机制变更已同步最高权威（design → Architecture / Issues 按需）
- [ ] 有回归或公开 smoke；fixture 未单独冒充 `runnable-mvp`
