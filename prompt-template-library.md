# Claude Code Prompt Template Library
# Claude Code 提示词模板库

Your personal collection of reusable prompt templates.
你的个人可复用提示词模板集合。

---

## Quick Reference Card / 快速参考卡

```
┌─────────────────────────────────────────────────────────────┐
│              PROMPT WRITING CHEAT SHEET                     │
│                  提示词编写速查表                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  STRUCTURE / 结构:                                          │
│  Context → Task → Requirements → Constraints → Output       │
│  上下文 → 任务 → 要求 → 约束 → 输出                          │
│                                                             │
│  FOR BUGS / Bug修复:                                        │
│  What happens + Expected + Steps + Error + Tried            │
│  发生了什么 + 预期 + 步骤 + 错误 + 尝试过的                   │
│                                                             │
│  FOR FEATURES / 功能:                                       │
│  User Story + Flow + Endpoints + Security + Criteria        │
│  用户故事 + 流程 + 端点 + 安全 + 标准                         │
│                                                             │
│  FOR REFACTORING / 重构:                                    │
│  Current State + Desired + Goals + Constraints              │
│  当前状态 + 期望 + 目标 + 约束                                │
│                                                             │
│  WHEN IT FAILS / 失败时:                                    │
│  Keep (good parts) + Fix (specific issues) + Verify         │
│  保留（好的部分）+ 修复（具体问题）+ 验证                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Table of Contents / 目录

1. [Meta-Prompts / 元提示词](#1-meta-prompts--元提示词)
2. [Bug Fix Templates / Bug修复模板](#2-bug-fix-templates--bug修复模板)
3. [Feature Templates / 功能模板](#3-feature-templates--功能模板)
4. [Refactoring Templates / 重构模板](#4-refactoring-templates--重构模板)
5. [Code Review Templates / 代码审查模板](#5-code-review-templates--代码审查模板)
6. [Test Writing Templates / 测试编写模板](#6-test-writing-templates--测试编写模板)
7. [Recovery Templates / 恢复模板](#7-recovery-templates--恢复模板)
8. [Verification Templates / 验证模板](#8-verification-templates--验证模板)
9. [Project Context Template / 项目上下文模板](#9-project-context-template--项目上下文模板)

---

## 1. Meta-Prompts / 元提示词

### 1.1 Architecture Analysis / 架构分析

```
Before implementing [FEATURE], please analyze our options.
在实现 [功能] 之前，请分析我们的选项。

## Context / 上下文
[Describe current system and requirements]

## Please Analyze / 请分析

### Option Comparison / 选项比较
For each approach, evaluate:
| Approach | Pros | Cons | Complexity | Recommended? |
|----------|------|------|------------|--------------|
| Option A | ? | ? | ? | ? |
| Option B | ? | ? | ? | ? |
| Option C | ? | ? | ? | ? |

### Consider These Factors / 考虑这些因素
- Scalability / 可扩展性
- Maintainability / 可维护性
- Performance / 性能
- Security / 安全性
- Implementation effort / 实现工作量

### Output / 输出
1. Your recommendation with reasoning
2. What we'd need (dependencies, changes)
3. Potential risks and mitigations
4. Questions you have for me

## Do NOT write code yet / 暂不要写代码
Wait for my approval before proceeding.
```

### 1.2 Implementation Planning / 实现规划

```
I need to implement [FEATURE]. Before coding, please create a plan.
我需要实现 [功能]。在编码之前，请创建一个计划。

## Context / 上下文
[Project info, tech stack, existing patterns]

## Create Implementation Plan / 创建实现计划

### 1. File Changes
List all files to create/modify:
| File | Action | Purpose |
|------|--------|---------|
| ? | Create/Modify | ? |

### 2. Dependencies
- New packages needed?
- Database changes?
- Configuration changes?

### 3. Implementation Order
Draw dependency graph and suggest order.

### 4. Testing Strategy
- Unit tests needed?
- Integration tests?
- Manual testing steps?

### 5. Estimated Steps
Break into [3-7] sequential steps.

## Questions for Me / 给我的问题
[List any clarifications needed]

Wait for my approval before starting implementation.
```

---

## 2. Bug Fix Templates / Bug修复模板

### 2.1 Standard Bug Report / 标准Bug报告

```
Fix the bug where [BRIEF DESCRIPTION].
修复 [简要描述] 的 bug。

## Bug Description / Bug 描述
**Expected:** [What should happen]
**Actual:** [What actually happens]

## Environment / 环境
- Browser/OS: [e.g., Chrome 120, macOS]
- Version: [e.g., v2.1.0]
- Works in: [Where it works]
- Fails in: [Where it fails]

## Steps to Reproduce / 复现步骤
1. [Step 1]
2. [Step 2]
3. [Step 3]
4. Observe: [What you see]

## Error Message / 错误信息
```
[Exact error message or console output]
```

## Relevant Files / 相关文件
- [file1.ts] - [why relevant]
- [file2.ts] - [why relevant]

## Current Code / 当前代码
```[language]
[Relevant code snippet]
```

## What I've Tried / 我尝试过的
1. ❌ [Attempt 1] - [Result]
2. ❌ [Attempt 2] - [Result]

## Suspected Cause / 疑似原因
[Your hypothesis if any]

## Constraints / 约束
- Don't change: [What to preserve]
- Must maintain: [Requirements]
```

### 2.2 Performance Bug / 性能Bug

```
Fix the performance issue in [LOCATION].
修复 [位置] 的性能问题。

## Problem / 问题
**Current:** [Current performance, e.g., "3 seconds to load"]
**Target:** [Target performance, e.g., "under 500ms"]

## Location / 位置
File: [file path]
Function/Component: [name]
Lines: [approximate lines]

## Profiling Data / 分析数据
[Any performance measurements, flame graphs, etc.]

## Suspected Bottlenecks / 疑似瓶颈
1. [Bottleneck 1]
2. [Bottleneck 2]

## Constraints / 约束
- Don't change the output/behavior
- Don't add new dependencies unless necessary
- Must still pass all tests

## Verification / 验证
After fixing, measure:
- [ ] Response time < [target]
- [ ] Memory usage acceptable
- [ ] No functionality regression
```

---

## 3. Feature Templates / 功能模板

### 3.1 Full Feature Implementation / 完整功能实现

```
Implement [FEATURE NAME] feature.
实现 [功能名称] 功能。

## Feature Overview / 功能概述
[2-3 sentence description of what this feature does]

## User Story / 用户故事
As a [ROLE],
I want to [ACTION],
so that [BENEFIT].

## User Flow / 用户流程
1. User [action 1]
2. System [response 1]
3. User [action 2]
4. ...
5. End state: [final outcome]

## Technical Requirements / 技术要求

### Backend / 后端
Endpoints needed:
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/... | ... |
| GET | /api/... | ... |

Database changes:
[Schema changes if any]

### Frontend / 前端
Components needed:
- [ ] [Component 1] - [purpose]
- [ ] [Component 2] - [purpose]

Pages/Routes:
- [ ] /path - [description]

### Security / 安全
- [ ] Authentication required?
- [ ] Authorization rules?
- [ ] Input validation?
- [ ] Rate limiting?

## Acceptance Criteria / 验收标准
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Criterion 3]

## Out of Scope / 不在范围内
- [What this feature does NOT include]

## Existing Code to Reference / 参考的现有代码
- [Similar feature/pattern location]
```

### 3.2 API Endpoint / API端点

```
Create [METHOD] [PATH] endpoint.
创建 [方法] [路径] 端点。

## Purpose / 目的
[What this endpoint does]

## Request / 请求
```json
{
  "field1": "type - description",
  "field2": "type - description (optional)"
}
```

## Response / 响应
Success (200/201):
```json
{
  "data": { ... }
}
```

Error responses:
- 400: [When/why]
- 401: [When/why]
- 404: [When/why]

## Validation Rules / 验证规则
- field1: [rules]
- field2: [rules]

## Business Logic / 业务逻辑
1. [Step 1]
2. [Step 2]
3. [Step 3]

## Security / 安全
- Authentication: [Required/Optional]
- Authorization: [Rules]
- Rate limiting: [Limits]

## Location / 位置
- Route: src/routes/[file].ts
- Controller: src/controllers/[file].ts
- Service: src/services/[file].ts

## Follow Patterns In / 遵循的模式
[Reference file for patterns]
```

### 3.3 React Component / React组件

```
Create [COMPONENT NAME] component.
创建 [组件名称] 组件。

## Purpose / 目的
[What this component does]

## Location / 位置
src/components/[path]/[ComponentName].tsx

## Props Interface / 属性接口
```typescript
interface [ComponentName]Props {
  prop1: type;       // Description
  prop2?: type;      // Description (optional)
  onEvent?: () => void;
}
```

## States / 状态
- [state1]: [type] - [purpose]
- [state2]: [type] - [purpose]

## Behavior / 行为
- On mount: [what happens]
- On [event]: [what happens]
- On unmount: [cleanup needed?]

## UI States / UI状态
- Loading: [how it looks]
- Empty: [how it looks]
- Error: [how it looks]
- Success: [how it looks]

## Styling / 样式
- Use: [CSS modules / Tailwind / styled-components]
- Follow: [design system / existing patterns]

## Accessibility / 可访问性
- Keyboard navigation: [requirements]
- Screen reader: [requirements]
- ARIA labels: [requirements]

## Example Usage / 使用示例
```tsx
<[ComponentName]
  prop1={value}
  prop2={value}
  onEvent={() => handleEvent()}
/>
```
```

---

## 4. Refactoring Templates / 重构模板

### 4.1 Code Refactoring / 代码重构

```
Refactor [WHAT] to improve [GOAL].
重构 [什么] 以改进 [目标]。

## Current State / 当前状态
Location: [file path, lines]

### Problems / 问题
1. [Problem 1]
2. [Problem 2]
3. [Problem 3]

### Current Code / 当前代码
```[language]
[Current implementation]
```

## Desired State / 期望状态

### Goals / 目标
- [ ] [Goal 1, e.g., "Reduce function to <50 lines"]
- [ ] [Goal 2, e.g., "Remove code duplication"]
- [ ] [Goal 3, e.g., "Add proper types"]

### Target Architecture / 目标架构
[Describe or diagram the target state]

## Constraints / 约束

### MUST Keep / 必须保持
- [ ] Same public API/function signatures
- [ ] All existing tests pass
- [ ] Same behavior/output

### MUST NOT / 必须不
- [ ] Don't add new dependencies
- [ ] Don't change [specific thing]
- [ ] Don't modify files outside [scope]

## Refactoring Steps / 重构步骤
Suggest step-by-step approach:
1. [Step 1]
2. [Step 2]
...

## Verification / 验证
After refactoring:
- [ ] All tests pass
- [ ] No TypeScript errors
- [ ] [Specific verification]
```

### 4.2 File/Module Split / 文件/模块拆分

```
Split [FILE] into smaller, focused modules.
将 [文件] 拆分为更小的、聚焦的模块。

## Current State / 当前状态
File: [path]
Lines: [count]
Problems:
- [Too many responsibilities]
- [Hard to test]
- [etc.]

## Proposed Structure / 建议结构
```
[directory]/
├── index.ts           # Re-exports
├── [module1].ts       # [responsibility]
├── [module2].ts       # [responsibility]
├── [module3].ts       # [responsibility]
├── types.ts           # Shared types
└── utils.ts           # Shared utilities
```

## Module Responsibilities / 模块职责
| Module | Responsibility | ~Lines |
|--------|---------------|--------|
| module1 | [what it handles] | ~XX |
| module2 | [what it handles] | ~XX |

## Migration Plan / 迁移计划
1. Create new file structure
2. Move [X] to [module1]
3. Move [Y] to [module2]
4. Update imports
5. Verify tests pass

## Constraints / 约束
- Maintain backward compatibility via re-exports
- Don't break existing imports
- Keep all tests passing
```

---

## 5. Code Review Templates / 代码审查模板

### 5.1 Security Review / 安全审查

```
Review [FILE/FEATURE] for security vulnerabilities.
审查 [文件/功能] 的安全漏洞。

## Scope / 范围
Files: [list files]
Focus: [specific areas]

## Check For / 检查项

### Input Validation / 输入验证
- [ ] All user inputs validated?
- [ ] SQL injection prevented?
- [ ] XSS prevented?
- [ ] Command injection prevented?

### Authentication & Authorization / 认证与授权
- [ ] Auth required where needed?
- [ ] Proper authorization checks?
- [ ] Token handling secure?

### Data Protection / 数据保护
- [ ] Sensitive data encrypted?
- [ ] No secrets in code?
- [ ] PII handled correctly?

### Error Handling / 错误处理
- [ ] No stack traces to users?
- [ ] No sensitive info in errors?

## Output Format / 输出格式
| Severity | Location | Issue | Recommendation |
|----------|----------|-------|----------------|
| 🔴 Critical | file:line | ... | ... |
| 🟡 High | file:line | ... | ... |
| 🟢 Low | file:line | ... | ... |
```

### 5.2 General Code Review / 通用代码审查

```
Review the following code for quality and issues.
审查以下代码的质量和问题。

## Code to Review / 要审查的代码
[Paste code or specify files]

## Review Checklist / 审查清单

### Correctness / 正确性
- [ ] Logic is correct?
- [ ] Edge cases handled?
- [ ] Error handling complete?

### Performance / 性能
- [ ] No unnecessary loops?
- [ ] Efficient algorithms?
- [ ] No memory leaks?

### Maintainability / 可维护性
- [ ] Clear naming?
- [ ] Appropriate comments?
- [ ] Single responsibility?

### Style / 风格
- [ ] Matches project conventions?
- [ ] Consistent formatting?

## Output / 输出
For each issue found:
- Severity: Critical / Major / Minor / Suggestion
- Location: file:line
- Issue: [description]
- Suggestion: [how to fix]
```

---

## 6. Test Writing Templates / 测试编写模板

### 6.1 Unit Tests / 单元测试

```
Write unit tests for [FILE/FUNCTION].
为 [文件/函数] 编写单元测试。

## Target / 目标
File: [path]
Functions/Methods: [list]

## Test Framework / 测试框架
[Jest / Mocha / pytest / etc.]

## Test Cases / 测试用例

### Happy Path / 正常路径
- [ ] [Test case 1]
- [ ] [Test case 2]

### Edge Cases / 边界情况
- [ ] Empty input
- [ ] Null/undefined
- [ ] Maximum values
- [ ] Minimum values

### Error Cases / 错误情况
- [ ] Invalid input type
- [ ] Missing required fields
- [ ] [Specific error scenarios]

## Mocking / 模拟
Mock these dependencies:
- [Dependency 1]: [how to mock]
- [Dependency 2]: [how to mock]

## Output Location / 输出位置
[path]/__tests__/[filename].test.ts

## Patterns / 模式
- Use AAA pattern (Arrange, Act, Assert)
- Descriptive test names
- One assertion per test (when practical)
```

### 6.2 API Integration Tests / API集成测试

```
Write integration tests for [ENDPOINT/FEATURE].
为 [端点/功能] 编写集成测试。

## Endpoints to Test / 要测试的端点
| Method | Path | Description |
|--------|------|-------------|
| ... | ... | ... |

## Test Scenarios / 测试场景

### Authentication / 认证
- [ ] Without token → 401
- [ ] With invalid token → 401
- [ ] With valid token → proceeds

### Success Cases / 成功情况
- [ ] Valid request → expected response
- [ ] [Specific success case]

### Validation Errors / 验证错误
- [ ] Missing required field → 400
- [ ] Invalid field value → 400

### Business Logic / 业务逻辑
- [ ] [Specific business rule test]

## Test Setup / 测试设置
- Database: [test db / mock]
- Auth: [how to handle]
- Cleanup: [after each / after all]

## Use / 使用
Testing library: [supertest / etc.]
```

---

## 7. Recovery Templates / 恢复模板

### 7.1 General Recovery / 通用恢复

```
The implementation has issues that need fixing.
实现有需要修复的问题。

## What's Working (Keep) / 工作正常（保留）
✅ [Good part 1]
✅ [Good part 2]

## Issues to Fix / 需要修复的问题

### Issue 1: [Title]
**Location:** [file:line]
**Current:**
```[language]
[Current code]
```
**Should be:**
```[language]
[Target code]
```

### Issue 2: [Title]
...

## Constraints / 约束
- Keep: [what to preserve]
- Don't change: [what not to modify]

## Verification / 验证
After fixing:
- [ ] [Verification step 1]
- [ ] [Verification step 2]
```

### 7.2 Performance Fix / 性能修复

```
The code works but has performance issues.
代码工作正常但有性能问题。

## Keep / 保留
✅ Logic is correct
✅ Output is correct
✅ [Other good parts]

## Performance Issues / 性能问题

### Issue 1: [Description]
Location: [file:line]
Current: [O(n²) / N+1 queries / etc.]
Target: [O(n) / 1 query / etc.]

Current code:
```[language]
[inefficient code]
```

Optimize to:
```[language]
[efficient code pattern]
```

## Constraints / 约束
- Same function signature
- Same output format
- All tests must pass

## Verification / 验证
After optimization:
- [ ] Process [X items] in < [Y time]
- [ ] Memory usage < [Z]
- [ ] All tests pass
```

### 7.3 Security Fix / 安全修复

```
🚨 SECURITY: Critical fixes needed.
🚨 安全：需要关键修复。

## Keep / 保留
✅ [Working parts to preserve]

## Security Fixes Required / 需要的安全修复

### 🔴 CRITICAL: [Issue]
Location: [file:line]
**Vulnerable:**
```[language]
[vulnerable code]
```
**Secure:**
```[language]
[secure code]
```

### 🟡 HIGH: [Issue]
...

## DO NOT / 不要
❌ [What not to change]

## Verification / 验证
- [ ] [Security test 1]
- [ ] [Security test 2]
```

---

## 8. Verification Templates / 验证模板

### 8.1 Implementation Verification / 实现验证

```
Verify the implementation is complete and correct.
验证实现是完整和正确的。

## Functionality / 功能
- [ ] [Feature 1] works
- [ ] [Feature 2] works
- [ ] Edge cases handled

## Security / 安全
- [ ] Input validation
- [ ] Authentication/Authorization
- [ ] No sensitive data exposure

## Code Quality / 代码质量
- [ ] No TypeScript/lint errors
- [ ] Follows project patterns
- [ ] Appropriate error handling

## Tests / 测试
- [ ] All tests pass
- [ ] Coverage meets threshold

## Report Format / 报告格式
### ✅ Passed
[List]

### ⚠️ Warnings
[List]

### ❌ Failed (Must Fix)
[List]
```

### 8.2 Pre-Deployment Checklist / 部署前检查清单

```
Pre-deployment verification for [FEATURE].
[功能] 的部署前验证。

## Code / 代码
- [ ] All tests pass
- [ ] No console.log / debug code
- [ ] Environment variables documented
- [ ] Database migrations ready

## Security / 安全
- [ ] No secrets in code
- [ ] Input validation complete
- [ ] Auth/authz working

## Performance / 性能
- [ ] No N+1 queries
- [ ] Appropriate caching
- [ ] Load tested (if applicable)

## Documentation / 文档
- [ ] API docs updated
- [ ] README updated (if needed)
- [ ] Changelog updated

## Rollback Plan / 回滚计划
- [ ] Rollback steps documented
- [ ] Feature flag (if applicable)
```

---

## 9. Project Context Template / 项目上下文模板

### 9.1 CLAUDE.md for Your Project / 项目的CLAUDE.md

Create this file in your project root to give Claude consistent context.
在项目根目录创建此文件以给 Claude 提供一致的上下文。

```markdown
# Project Context for Claude / Claude 项目上下文

## Project Overview / 项目概述
[Brief description of what this project does]

## Tech Stack / 技术栈
- Frontend: [React/Vue/Angular] + [TypeScript/JavaScript]
- Backend: [Node/Python/Go] + [Framework]
- Database: [PostgreSQL/MongoDB/etc.]
- Testing: [Jest/Mocha/pytest]
- Other: [Redis, Docker, etc.]

## Code Conventions / 代码规范

### Naming / 命名
- Files: [camelCase / kebab-case / PascalCase]
- Functions: [camelCase]
- Classes: [PascalCase]
- Constants: [UPPER_SNAKE_CASE]

### Style / 风格
- Use [const/let], never var
- Use [async/await], not callbacks
- Use [named exports / default exports]
- [Other conventions]

## File Structure / 文件结构
```
src/
├── components/    # [Description]
├── pages/         # [Description]
├── services/      # [Description]
├── utils/         # [Description]
├── types/         # [Description]
└── ...
```

## Important Patterns / 重要模式

### Error Handling / 错误处理
See: [example file]
Pattern: [description]

### API Calls / API调用
See: [example file]
Pattern: [description]

### State Management / 状态管理
See: [example file]
Pattern: [description]

## Common Commands / 常用命令
- `npm run dev` - Start development server
- `npm test` - Run tests
- `npm run build` - Build for production
- [Other commands]

## DO / 要做
- Follow existing patterns
- Add types for all functions
- Write tests for new features
- [Other requirements]

## DON'T / 不要
- Don't use `any` type
- Don't skip error handling
- Don't commit console.log
- [Other restrictions]
```

---

## How to Use This Library / 如何使用此库

1. **Find the right template** for your task
   找到适合你任务的模板

2. **Copy and customize** - fill in the [PLACEHOLDERS]
   复制并定制 - 填写 [占位符]

3. **Add context** specific to your project
   添加你项目特定的上下文

4. **Review** against the checklist before sending
   发送前对照清单审查

5. **Iterate** - save improved versions back to your library
   迭代 - 将改进版本保存回你的库

---

## Template Selection Guide / 模板选择指南

```
What are you doing? / 你在做什么？
│
├─ Planning something new?
│  └─ Use: Meta-Prompt (1.1 or 1.2)
│
├─ Fixing a bug?
│  └─ Use: Bug Fix Template (2.1 or 2.2)
│
├─ Building a feature?
│  ├─ Full feature → 3.1
│  ├─ API endpoint → 3.2
│  └─ UI component → 3.3
│
├─ Improving existing code?
│  ├─ Restructuring → 4.1
│  └─ Splitting files → 4.2
│
├─ Reviewing code?
│  ├─ Security focus → 5.1
│  └─ General review → 5.2
│
├─ Writing tests?
│  ├─ Unit tests → 6.1
│  └─ API tests → 6.2
│
├─ Fixing Claude's output?
│  ├─ General issues → 7.1
│  ├─ Performance → 7.2
│  └─ Security → 7.3
│
└─ Verifying work?
   ├─ Implementation → 8.1
   └─ Pre-deployment → 8.2
```

---

*Last updated: [DATE]*
*Templates version: 1.0*
