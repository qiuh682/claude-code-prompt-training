# Claude Code Prompt Writing Training / Claude Code 提示词写作训练

## 7-Day Training Program / 7天培训计划
**Duration / 时长**: 1-2 hours per day / 每天1-2小时

---

# Day 1: Fundamentals of Effective Prompting / 第一天：有效提示词的基础

## Learning Objectives / 学习目标
- Understand how Claude Code interprets prompts / 理解 Claude Code 如何解读提示词
- Learn the anatomy of a good prompt / 学习优秀提示词的结构
- Practice writing clear, specific requests / 练习编写清晰、具体的请求

## Core Concepts / 核心概念

### 1. Clarity Over Brevity / 清晰优先于简洁

**Bad / 差的例子:**
```
fix the bug
```

**Good / 好的例子:**
```
Fix the TypeError in src/utils/parser.js where the function parseConfig()
throws "Cannot read property 'name' of undefined" when the config file
is empty.

修复 src/utils/parser.js 中的 TypeError，当配置文件为空时，parseConfig()
函数抛出 "Cannot read property 'name' of undefined" 错误。
```

### 2. The CRISPE Framework / CRISPE 框架

| Element | 元素 | Description | 描述 |
|---------|------|-------------|------|
| **C**ontext | 上下文 | Background information | 背景信息 |
| **R**ole | 角色 | What perspective to take | 采用什么视角 |
| **I**nstruction | 指令 | What to do | 要做什么 |
| **S**pecifics | 具体要求 | Details and constraints | 细节和约束 |
| **P**urpose | 目的 | Why this matters | 为什么重要 |
| **E**xamples | 示例 | Show expected output | 展示预期输出 |

### 3. Prompt Structure Template / 提示词结构模板

```markdown
## Context / 上下文
[What is the project about? What has been done?]
[项目是关于什么的？已经完成了什么？]

## Task / 任务
[Clear description of what needs to be done]
[清晰描述需要完成的工作]

## Requirements / 要求
- [Specific requirement 1 / 具体要求1]
- [Specific requirement 2 / 具体要求2]

## Constraints / 约束
- [Any limitations or restrictions / 任何限制或约束]

## Expected Output / 预期输出
[What should the result look like?]
[结果应该是什么样的？]
```

## Exercises / 练习 (45 min)

### Exercise 1.1: Rewrite Bad Prompts / 重写糟糕的提示词
Transform these vague prompts into clear, actionable ones:
将这些模糊的提示词改写成清晰、可操作的：

1. "make it faster" → ?
2. "add tests" → ?
3. "clean up the code" → ?

### Exercise 1.2: Write a Complete Prompt / 编写完整提示词
Write a prompt asking Claude Code to create a function that validates email addresses.
编写一个提示词，要求 Claude Code 创建一个验证电子邮件地址的函数。

### Exercise 1.3: Identify Missing Information / 识别缺失信息
Review this prompt and list what information is missing:
审查这个提示词并列出缺失的信息：
```
Add a login feature to my app
```

## Day 1 Summary / 第一天总结
- Be specific, not vague / 要具体，不要模糊
- Provide context / 提供上下文
- State your constraints / 说明你的约束条件
- Describe expected outcomes / 描述预期结果

---

# Day 2: Task Decomposition / 第二天：任务分解

## Learning Objectives / 学习目标
- Break complex tasks into manageable steps / 将复杂任务分解为可管理的步骤
- Understand task dependencies / 理解任务依赖关系
- Create effective task sequences / 创建有效的任务序列

## Core Concepts / 核心概念

### 1. The Decomposition Principle / 分解原则

**Complex Task / 复杂任务:**
```
Build a user authentication system
构建用户认证系统
```

**Decomposed / 分解后:**
```
1. Create user database schema with fields: id, email, password_hash,
   created_at, updated_at
   创建用户数据库模式，字段：id, email, password_hash, created_at, updated_at

2. Implement password hashing using bcrypt with cost factor 12
   使用 bcrypt 实现密码哈希，成本因子为12

3. Create registration endpoint POST /api/auth/register
   创建注册端点 POST /api/auth/register

4. Create login endpoint POST /api/auth/login that returns JWT token
   创建登录端点 POST /api/auth/login，返回 JWT token

5. Add authentication middleware to protect routes
   添加认证中间件来保护路由

6. Write unit tests for each component
   为每个组件编写单元测试
```

### 2. Identifying Task Dependencies / 识别任务依赖

```
┌─────────────────┐
│ Database Schema │ ← Must be first / 必须首先完成
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Password Hashing│
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────┐
│Register│ │ Login │ ← Can be parallel / 可以并行
└───────┘ └───────┘
    │         │
    └────┬────┘
         ▼
┌─────────────────┐
│   Middleware    │
└─────────────────┘
```

### 3. Prompt Chaining / 提示词链式调用

**Step 1 / 第一步:**
```
First, analyze the existing codebase structure in src/ and identify
where authentication logic should be placed. List the files that will
need to be created or modified.

首先，分析 src/ 中现有的代码库结构，确定认证逻辑应该放在哪里。
列出需要创建或修改的文件。
```

**Step 2 / 第二步:**
```
Based on the analysis, create the User model in src/models/User.js
with the schema we discussed.

根据分析，在 src/models/User.js 中创建我们讨论过的 User 模型。
```

### 4. When to Decompose vs. Single Prompt / 何时分解 vs 单个提示词

| Single Prompt / 单个提示词 | Decomposed / 分解 |
|---------------------------|-------------------|
| Simple function / 简单函数 | Multi-file changes / 多文件更改 |
| Bug fix / Bug修复 | New features / 新功能 |
| Code review / 代码审查 | System architecture / 系统架构 |
| Explanation / 解释说明 | Refactoring / 重构 |

## Exercises / 练习 (45 min)

### Exercise 2.1: Decompose a Feature / 分解一个功能
Break down this task into 5-7 sequential steps:
将此任务分解为5-7个顺序步骤：
```
Add a shopping cart feature to an e-commerce site
为电商网站添加购物车功能
```

### Exercise 2.2: Identify Dependencies / 识别依赖关系
Given these tasks, draw a dependency diagram:
给定这些任务，绘制依赖关系图：
- Create product API
- Design database schema
- Build frontend cart UI
- Implement cart state management
- Add checkout flow

### Exercise 2.3: Write Chained Prompts / 编写链式提示词
Write 3 sequential prompts for implementing a file upload feature.
为实现文件上传功能编写3个顺序提示词。

## Day 2 Summary / 第二天总结
- Break big tasks into small, testable steps / 将大任务分解为小的、可测试的步骤
- Identify dependencies before starting / 开始前识别依赖关系
- Each prompt should have one clear goal / 每个提示词应该有一个明确目标
- Use results from previous steps / 使用前序步骤的结果

---

# Day 3: Context and Constraints / 第三天：上下文与约束

## Learning Objectives / 学习目标
- Provide effective context without overwhelming / 提供有效的上下文而不过载
- Set clear constraints and boundaries / 设定清晰的约束和边界
- Reference existing code and patterns / 引用现有代码和模式

## Core Concepts / 核心概念

### 1. Context Layering / 上下文分层

```
Level 1: Project Context / 项目上下文
├── What the project does / 项目功能
├── Tech stack / 技术栈
└── Coding conventions / 编码规范

Level 2: Task Context / 任务上下文
├── What you're building / 你要构建什么
├── Why it's needed / 为什么需要
└── Related existing code / 相关现有代码

Level 3: Immediate Context / 直接上下文
├── Specific file/function / 具体文件/函数
├── Current state / 当前状态
└── Expected behavior / 预期行为
```

### 2. Effective Context Examples / 有效上下文示例

**Too Little / 太少:**
```
Add validation to the form
给表单添加验证
```

**Too Much / 太多:**
```
[500 lines of unrelated code history...]
Add validation to the form
```

**Just Right / 刚好:**
```
We're building a React registration form in src/components/RegisterForm.tsx.
The form currently has email and password fields but no validation.
我们正在 src/components/RegisterForm.tsx 中构建一个 React 注册表单。
表单目前有 email 和 password 字段，但没有验证。

We use Zod for validation across the project (see src/utils/validators.ts
for examples). Please add validation with these rules:
我们在整个项目中使用 Zod 进行验证（参见 src/utils/validators.ts 的示例）。
请添加以下规则的验证：

- Email: valid format, required / 邮箱：有效格式，必填
- Password: min 8 chars, 1 uppercase, 1 number / 密码：至少8字符，1大写，1数字
```

### 3. Types of Constraints / 约束类型

| Type | 类型 | Example | 示例 |
|------|------|---------|------|
| Technical | 技术 | "Must work with Node 18+" | "必须支持 Node 18+" |
| Style | 风格 | "Follow existing naming conventions" | "遵循现有命名规范" |
| Performance | 性能 | "Response time under 100ms" | "响应时间低于100ms" |
| Security | 安全 | "No eval(), sanitize all inputs" | "禁止 eval()，清理所有输入" |
| Scope | 范围 | "Only modify files in src/auth/" | "只修改 src/auth/ 中的文件" |

### 4. Referencing Patterns / 引用模式

```
Follow the same pattern as the UserService class in src/services/UserService.ts
for error handling and logging.
遵循 src/services/UserService.ts 中 UserService 类的相同模式来处理错误和日志。

Specifically:
具体来说：
- Wrap operations in try-catch / 用 try-catch 包装操作
- Use the logger from src/utils/logger.ts / 使用 src/utils/logger.ts 中的 logger
- Throw custom errors from src/errors/ / 抛出 src/errors/ 中的自定义错误
```

### 5. The "Don't" Constraints / "不要"约束

```
Please implement the feature with these constraints:
请在以下约束条件下实现该功能：

DO / 要做:
- Use TypeScript strict mode / 使用 TypeScript 严格模式
- Add JSDoc comments for public methods / 为公共方法添加 JSDoc 注释

DON'T / 不要:
- Don't add new dependencies / 不要添加新依赖
- Don't modify the existing API contract / 不要修改现有 API 契约
- Don't use any type / 不要使用 any 类型
```

## Exercises / 练习 (45 min)

### Exercise 3.1: Context Extraction / 上下文提取
You need to add caching to an API. What context would you provide? List:
你需要为一个 API 添加缓存。你会提供什么上下文？列出：
- 3 essential pieces of context / 3个必要的上下文信息
- 3 nice-to-have pieces / 3个有则更好的信息
- 3 things to avoid including / 3个应该避免包含的信息

### Exercise 3.2: Write Constraints / 编写约束
Write constraints for these scenarios:
为这些场景编写约束：
1. Adding a feature to a legacy codebase / 向遗留代码库添加功能
2. Building a security-sensitive feature / 构建安全敏感的功能
3. Optimizing a slow function / 优化一个慢函数

### Exercise 3.3: Pattern Reference / 模式引用
Write a prompt that references an existing pattern in code and asks Claude
to apply it to a new situation.
编写一个提示词，引用代码中的现有模式，并要求 Claude 将其应用于新场景。

## Day 3 Summary / 第三天总结
- Provide layered, relevant context / 提供分层的相关上下文
- Be explicit about constraints / 明确约束条件
- Reference existing patterns / 引用现有模式
- Include both "do" and "don't" / 包含"要做"和"不要做"

---

# Day 4: Code-Specific Prompt Patterns / 第四天：代码特定的提示词模式

## Learning Objectives / 学习目标
- Master common code task prompts / 掌握常见代码任务提示词
- Learn debugging prompt techniques / 学习调试提示词技巧
- Write effective refactoring requests / 编写有效的重构请求

## Core Concepts / 核心概念

### 1. Bug Fixing Prompts / Bug 修复提示词

**Template / 模板:**
```
## Bug Description / Bug 描述
[What is happening vs what should happen]
[正在发生什么 vs 应该发生什么]

## Steps to Reproduce / 复现步骤
1. [Step 1]
2. [Step 2]

## Error Message / 错误信息
```
[Exact error message or stack trace]
[精确的错误信息或堆栈跟踪]
```

## Relevant Files / 相关文件
- [file1.js] - [why relevant]
- [file2.js] - [why relevant]

## What I've Tried / 我尝试过的
- [Attempt 1 and result]
- [Attempt 2 and result]
```

**Example / 示例:**
```
## Bug Description / Bug 描述
The user list pagination shows page 2 data when clicking page 3.
用户列表分页在点击第3页时显示第2页的数据。

## Steps to Reproduce / 复现步骤
1. Go to /admin/users
2. Click page 3 in pagination
3. Observe that page 2 data is shown

## Error Message / 错误信息
No error, but Network tab shows request for page=2 instead of page=3

## Relevant Files / 相关文件
- src/components/UserList.tsx - pagination component
- src/hooks/useUsers.ts - data fetching hook

## What I've Tried / 我尝试过的
- Console logged the page number - it's correct in state
- The API call seems to use stale value
```

### 2. Feature Implementation Prompts / 功能实现提示词

**Template / 模板:**
```
## Feature Overview / 功能概述
[Brief description of the feature]
[功能的简要描述]

## User Story / 用户故事
As a [role], I want to [action] so that [benefit].
作为一个[角色]，我想要[动作]，以便[好处]。

## Acceptance Criteria / 验收标准
- [ ] [Criterion 1]
- [ ] [Criterion 2]

## Technical Requirements / 技术要求
- [Requirement 1]
- [Requirement 2]

## Existing Code to Reference / 参考的现有代码
- [Similar feature/pattern]
```

### 3. Refactoring Prompts / 重构提示词

**Template / 模板:**
```
## Current State / 当前状态
[Describe current implementation and its problems]
[描述当前实现及其问题]

## Desired State / 期望状态
[Describe what the code should look like after]
[描述重构后代码应该是什么样]

## Refactoring Goals / 重构目标
- [ ] [Goal 1: e.g., Improve readability]
- [ ] [Goal 2: e.g., Reduce duplication]

## Constraints / 约束
- Must maintain backward compatibility / 必须保持向后兼容
- No changes to public API / 不改变公共 API
- All existing tests must pass / 所有现有测试必须通过
```

### 4. Code Review Prompts / 代码审查提示词

```
Review the following code for:
审查以下代码的：

1. Security vulnerabilities / 安全漏洞
2. Performance issues / 性能问题
3. Code style consistency / 代码风格一致性
4. Error handling completeness / 错误处理完整性
5. Test coverage gaps / 测试覆盖空白

Please provide:
请提供：
- Severity level for each issue (critical/major/minor)
  每个问题的严重程度（严重/重要/次要）
- Specific line numbers / 具体行号
- Suggested fixes / 建议的修复方案
```

### 5. Test Writing Prompts / 测试编写提示词

```
Write unit tests for the UserService class in src/services/UserService.ts.
为 src/services/UserService.ts 中的 UserService 类编写单元测试。

Testing framework: Jest with ts-jest
测试框架：Jest 配合 ts-jest

Please test:
请测试：
- All public methods / 所有公共方法
- Edge cases: empty input, null values, invalid data
  边界情况：空输入、null值、无效数据
- Error scenarios / 错误场景
- Mock external dependencies (database, API calls)
  Mock 外部依赖（数据库、API调用）

Follow the AAA pattern (Arrange, Act, Assert).
遵循 AAA 模式（准备、执行、断言）。
```

## Exercises / 练习 (45 min)

### Exercise 4.1: Write a Bug Report Prompt / 编写 Bug 报告提示词
Create a complete bug-fixing prompt for: "Login doesn't work on mobile"
为以下问题创建完整的 bug 修复提示词："登录在移动端不工作"

### Exercise 4.2: Feature Implementation / 功能实现
Write a prompt for implementing a "forgot password" feature.
编写一个实现"忘记密码"功能的提示词。

### Exercise 4.3: Refactoring Request / 重构请求
Write a prompt to refactor a 500-line function into smaller, testable units.
编写一个提示词，将500行的函数重构为更小的、可测试的单元。

## Day 4 Summary / 第四天总结
- Use templates for common tasks / 为常见任务使用模板
- Include reproduction steps for bugs / Bug 包含复现步骤
- Specify acceptance criteria for features / 功能指定验收标准
- Define clear boundaries for refactoring / 重构定义清晰边界

---

# Day 5: Advanced Prompting Techniques / 第五天：高级提示词技巧

## Learning Objectives / 学习目标
- Use meta-prompts and self-correction / 使用元提示词和自我纠正
- Implement iterative refinement / 实现迭代改进
- Handle complex multi-step workflows / 处理复杂的多步骤工作流

## Core Concepts / 核心概念

### 1. Meta-Prompts / 元提示词

Ask Claude to think about the approach before coding:
让 Claude 在编码前思考方法：

```
Before implementing, please:
在实现之前，请：

1. Analyze the current codebase structure
   分析当前代码库结构
2. List 2-3 possible approaches with pros/cons
   列出2-3种可能的方法及其优缺点
3. Recommend the best approach and explain why
   推荐最佳方法并解释原因
4. Wait for my approval before writing code
   在编写代码前等待我的批准
```

### 2. Self-Verification Prompts / 自我验证提示词

```
After implementing, please verify:
实现后，请验证：

1. Run the existing tests and confirm they pass
   运行现有测试并确认通过
2. Check for TypeScript errors
   检查 TypeScript 错误
3. Review your code for the security issues we discussed
   审查你的代码是否有我们讨论过的安全问题
4. List any edge cases that might not be handled
   列出可能未处理的边界情况
```

### 3. Iterative Refinement / 迭代改进

**Round 1:**
```
Create a basic REST API endpoint for user search.
创建一个基本的用户搜索 REST API 端点。
```

**Round 2:**
```
Good start. Now enhance it with:
好的开始。现在增强它：
- Pagination (limit/offset) / 分页（limit/offset）
- Sorting options / 排序选项
- Maintain the existing structure / 保持现有结构
```

**Round 3:**
```
Now add input validation and error handling for:
现在添加输入验证和错误处理：
- Invalid pagination values / 无效的分页值
- SQL injection prevention / SQL 注入预防
- Rate limiting headers / 限流头部
```

### 4. Conditional Logic in Prompts / 提示词中的条件逻辑

```
Implement user data export with these conditions:
根据以下条件实现用户数据导出：

IF the user is admin:
如果用户是管理员：
  - Allow export of all user fields
    允许导出所有用户字段
  - Include audit logs
    包含审计日志

ELSE IF the user is manager:
否则如果用户是经理：
  - Allow export of their team only
    只允许导出他们的团队
  - Exclude sensitive fields (SSN, salary)
    排除敏感字段（SSN、薪资）

ELSE:
否则：
  - Only allow export of own data
    只允许导出自己的数据
```

### 5. Output Format Control / 输出格式控制

```
Please provide your response in this exact format:
请按照这个确切格式提供你的回复：

### Analysis / 分析
[Your analysis here]

### Files to Modify / 要修改的文件
| File | Change Type | Description |
|------|-------------|-------------|
| ... | Add/Modify/Delete | ... |

### Implementation / 实现
[Code blocks with file paths as comments]

### Testing Instructions / 测试说明
[How to verify the changes work]
```

### 6. Role-Based Prompts / 基于角色的提示词

```
Act as a senior security engineer reviewing this authentication code.
作为一名高级安全工程师审查这段认证代码。

Focus on:
关注：
- OWASP Top 10 vulnerabilities / OWASP 前10大漏洞
- Token handling best practices / Token 处理最佳实践
- Session management / 会话管理

Provide findings in order of severity.
按严重程度顺序提供发现。
```

## Exercises / 练习 (45 min)

### Exercise 5.1: Write a Meta-Prompt / 编写元提示词
Create a meta-prompt for designing a caching strategy.
为设计缓存策略创建一个元提示词。

### Exercise 5.2: Iterative Enhancement / 迭代增强
Plan 3 rounds of prompts to build a notification system from basic to advanced.
规划3轮提示词，将通知系统从基础构建到高级。

### Exercise 5.3: Format Control / 格式控制
Write a prompt that requires a specific structured output format.
编写一个需要特定结构化输出格式的提示词。

## Day 5 Summary / 第五天总结
- Use meta-prompts for complex decisions / 对复杂决策使用元提示词
- Build features iteratively / 迭代构建功能
- Control output format explicitly / 明确控制输出格式
- Leverage role-based perspectives / 利用基于角色的视角

---

# Day 6: Debugging Prompts & Handling Failures / 第六天：调试提示词与处理失败

## Learning Objectives / 学习目标
- Diagnose why prompts don't work as expected / 诊断提示词为什么没有按预期工作
- Refine prompts based on results / 根据结果改进提示词
- Handle common failure modes / 处理常见的失败模式

## Core Concepts / 核心概念

### 1. Common Prompt Failures / 常见提示词失败

| Problem | 问题 | Cause | 原因 | Solution | 解决方案 |
|---------|------|-------|------|----------|----------|
| Wrong approach | 方法错误 | Unclear requirements | 需求不清 | Add specifics | 添加具体细节 |
| Incomplete code | 代码不完整 | Scope too large | 范围太大 | Break into steps | 分解步骤 |
| Ignores constraints | 忽略约束 | Constraints unclear | 约束不明 | Repeat constraints | 重复约束 |
| Wrong file modified | 修改了错误文件 | Ambiguous reference | 引用模糊 | Use full paths | 使用完整路径 |
| Style mismatch | 风格不匹配 | No style reference | 无风格参考 | Point to examples | 指向示例 |

### 2. The Feedback Loop / 反馈循环

```
Initial Prompt → Result → Analysis → Refined Prompt → Better Result
初始提示词 → 结果 → 分析 → 改进的提示词 → 更好的结果
```

**Example feedback / 反馈示例:**
```
The implementation you provided has these issues:
你提供的实现有以下问题：

1. ❌ Used `var` instead of `const/let` (we use ES6+)
   使用了 `var` 而不是 `const/let`（我们使用 ES6+）

2. ❌ Missing error handling for the API call
   API 调用缺少错误处理

3. ✅ Logic is correct / 逻辑正确

Please fix issues 1 and 2 while keeping the logic the same.
请修复问题1和2，同时保持逻辑不变。
```

### 3. Debugging Checklist / 调试检查清单

When a prompt doesn't work, check:
当提示词不工作时，检查：

```
□ Was the context sufficient?
  上下文是否充足？

□ Were requirements specific enough?
  需求是否足够具体？

□ Did I reference the right files/patterns?
  我是否引用了正确的文件/模式？

□ Were constraints clearly stated?
  约束是否明确说明？

□ Was the scope appropriate?
  范围是否合适？

□ Did I provide examples of expected output?
  我是否提供了预期输出的示例？
```

### 4. Recovery Prompts / 恢复提示词

**When code has bugs / 代码有 bug 时:**
```
The code you wrote has a bug. When I run it:
你写的代码有 bug。当我运行它时：

Input: [exact input]
Output: [actual output]
Expected: [expected output]

Please debug this specific issue without changing other functionality.
请调试这个具体问题，不要更改其他功能。
```

**When approach is wrong / 方法错误时:**
```
Let's step back. The approach we took won't work because [reason].
让我们退一步。我们采取的方法行不通，因为[原因]。

Instead, let's try:
相反，让我们尝试：
- [New approach]
- [Key constraint to respect]

Please start fresh with this new approach.
请用这个新方法重新开始。
```

### 5. Incremental Verification / 增量验证

```
Let's implement this step by step with verification:
让我们逐步实现并验证：

Step 1: Create the database migration
第一步：创建数据库迁移
→ After this, I'll run the migration and confirm it works
→ 之后，我会运行迁移并确认它工作

Step 2: Create the model
第二步：创建模型
→ After this, I'll test basic CRUD operations
→ 之后，我会测试基本的 CRUD 操作

[Continue step by step]
[继续逐步进行]
```

## Exercises / 练习 (45 min)

### Exercise 6.1: Diagnose a Failure / 诊断失败
Given this prompt and result, identify what went wrong:
给定这个提示词和结果，识别出哪里出了问题：

Prompt: "Add caching to the API"
Result: Added caching but broke existing functionality

### Exercise 6.2: Write Recovery Prompts / 编写恢复提示词
Write 3 different recovery prompts for when:
为以下情况编写3个不同的恢复提示词：
1. Code works but is inefficient / 代码工作但效率低
2. Code has security vulnerability / 代码有安全漏洞
3. Code doesn't follow project patterns / 代码不遵循项目模式

### Exercise 6.3: Iterative Debug Session / 迭代调试会话
Simulate a 3-round debugging session for a complex bug.
模拟一个复杂 bug 的3轮调试会话。

## Day 6 Summary / 第六天总结
- Analyze failures systematically / 系统地分析失败
- Give specific feedback / 提供具体反馈
- Use incremental verification / 使用增量验证
- Know when to restart vs. refine / 知道何时重新开始 vs 改进

---

# Day 7: Real Project Practice & Review / 第七天：真实项目实践与回顾

## Learning Objectives / 学习目标
- Apply all concepts to real projects / 将所有概念应用到真实项目
- Build a personal prompt library / 建立个人提示词库
- Establish your workflow / 建立你的工作流程

## Core Concepts / 核心概念

### 1. Building Your Prompt Library / 建立你的提示词库

Create templates for your common tasks:
为你的常见任务创建模板：

```
📁 My Prompt Templates / 我的提示词模板
├── 📄 bug-fix.md
├── 📄 new-feature.md
├── 📄 refactor.md
├── 📄 code-review.md
├── 📄 test-writing.md
├── 📄 documentation.md
└── 📄 performance-optimization.md
```

### 2. Project-Specific Context Files / 项目特定的上下文文件

Create a CLAUDE.md file for your project:
为你的项目创建一个 CLAUDE.md 文件：

```markdown
# Project Context for Claude / Claude 项目上下文

## Tech Stack / 技术栈
- Frontend: React 18 + TypeScript
- Backend: Node.js + Express
- Database: PostgreSQL
- Testing: Jest + React Testing Library

## Code Conventions / 代码规范
- Use functional components with hooks
- Prefer named exports
- Use async/await over promises
- Error handling: use custom error classes in src/errors/

## File Structure / 文件结构
src/
├── components/  # React components
├── hooks/       # Custom hooks
├── services/    # API calls
├── utils/       # Utility functions
└── types/       # TypeScript types

## Important Patterns / 重要模式
- See src/services/UserService.ts for API service pattern
- See src/hooks/useQuery.ts for data fetching pattern
```

### 3. Workflow Integration / 工作流集成

```
Daily Workflow / 日常工作流:

1. Start of task / 任务开始
   └── Write detailed prompt with context
       编写带有上下文的详细提示词

2. During implementation / 实现过程中
   └── Give feedback, iterate
       提供反馈，迭代

3. Completion / 完成
   └── Request verification and tests
       请求验证和测试

4. After / 之后
   └── Save useful prompts to library
       将有用的提示词保存到库中
```

### 4. Quality Checklist / 质量检查清单

Before sending any significant prompt:
在发送任何重要提示词之前：

```
□ Context: Does it include necessary background?
  上下文：是否包含必要的背景？

□ Specificity: Are requirements unambiguous?
  具体性：需求是否明确？

□ Constraints: Are limitations clearly stated?
  约束：限制是否明确说明？

□ Examples: Are there examples if needed?
  示例：如果需要是否有示例？

□ Scope: Is it appropriately sized?
  范围：大小是否合适？

□ Verification: How will success be measured?
  验证：如何衡量成功？
```

## Final Project / 最终项目 (60-90 min)

### Capstone Exercise / 毕业练习

Choose one of these projects and write a complete set of prompts:
选择以下项目之一，编写一套完整的提示词：

**Option A: Build a Todo API / 选项A：构建待办事项 API**
- REST API with CRUD operations
- User authentication
- Data validation
- Tests

**Option B: Add Search to Existing App / 选项B：为现有应用添加搜索**
- Full-text search
- Filters and sorting
- Results pagination
- Performance optimization

**Option C: Refactor Legacy Code / 选项C：重构遗留代码**
- Analyze existing code
- Plan refactoring strategy
- Implement incrementally
- Maintain functionality

For your chosen project, create:
为你选择的项目创建：

1. **Initial planning prompt / 初始规划提示词**
2. **3-5 implementation prompts / 3-5个实现提示词**
3. **Testing/verification prompt / 测试/验证提示词**
4. **Review/refinement prompt / 审查/改进提示词**

## Course Summary / 课程总结

### Key Principles / 关键原则

1. **Be Specific / 要具体**
   - Vague prompts → Vague results / 模糊的提示词 → 模糊的结果

2. **Provide Context / 提供上下文**
   - Claude can't read your mind / Claude 不能读心

3. **Set Constraints / 设定约束**
   - Boundaries improve output / 边界改善输出

4. **Decompose Tasks / 分解任务**
   - Small steps → Better results / 小步骤 → 更好的结果

5. **Iterate / 迭代**
   - First attempt rarely perfect / 第一次尝试很少完美

6. **Verify / 验证**
   - Always confirm results / 总是确认结果

### Quick Reference Card / 快速参考卡

```
┌─────────────────────────────────────────────────────────┐
│              PROMPT WRITING CHEAT SHEET                 │
│                  提示词编写速查表                         │
├─────────────────────────────────────────────────────────┤
│ STRUCTURE / 结构:                                       │
│   Context → Task → Requirements → Constraints → Output  │
│   上下文 → 任务 → 要求 → 约束 → 输出                      │
├─────────────────────────────────────────────────────────┤
│ FOR BUGS / Bug修复:                                     │
│   What happens + Expected + Steps to reproduce          │
│   发生了什么 + 预期 + 复现步骤                            │
├─────────────────────────────────────────────────────────┤
│ FOR FEATURES / 功能:                                    │
│   User story + Acceptance criteria + Tech requirements  │
│   用户故事 + 验收标准 + 技术要求                          │
├─────────────────────────────────────────────────────────┤
│ FOR REFACTORING / 重构:                                 │
│   Current state + Desired state + Constraints           │
│   当前状态 + 期望状态 + 约束                              │
├─────────────────────────────────────────────────────────┤
│ WHEN IT FAILS / 失败时:                                 │
│   Specific feedback + What to fix + What to keep        │
│   具体反馈 + 要修复什么 + 要保留什么                       │
└─────────────────────────────────────────────────────────┘
```

---

## Congratulations! / 恭喜！

You've completed the Claude Code Prompt Writing Training.
你已经完成了 Claude Code 提示词编写培训。

Next steps / 下一步:
1. Practice daily with real tasks / 每天用真实任务练习
2. Build your prompt library / 建立你的提示词库
3. Review and refine your templates / 审查和改进你的模板
4. Share learnings with your team / 与团队分享学习成果

Happy prompting! / 祝提示词编写愉快！
