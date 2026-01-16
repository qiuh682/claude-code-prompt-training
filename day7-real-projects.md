# Day 7: Real Project Practice & Review
# 第七天：真实项目实践与回顾

**Duration / 时长**: 1.5-2 hours / 1.5-2小时

---

## Learning Objectives / 学习目标
- Apply all concepts to real projects / 将所有概念应用到真实项目
- Build a personal prompt library / 建立个人提示词库
- Establish your workflow / 建立你的工作流程

---

## The 7-Day Journey Review / 7天旅程回顾

```
┌─────────────────────────────────────────────────────────────┐
│                    7-DAY SUMMARY                            │
│                     7天总结                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Day 1: FUNDAMENTALS / 基础                                 │
│  • Clarity over brevity / 清晰优先于简洁                     │
│  • CRISPE framework / CRISPE 框架                           │
│  • Specific > Vague / 具体 > 模糊                           │
│                                                             │
│  Day 2: TASK DECOMPOSITION / 任务分解                       │
│  • Break complex tasks into steps / 分解复杂任务             │
│  • Identify dependencies / 识别依赖关系                      │
│  • Chain prompts effectively / 有效链接提示词                │
│                                                             │
│  Day 3: CONTEXT & CONSTRAINTS / 上下文与约束                 │
│  • Layer your context / 分层上下文                          │
│  • DO and DON'T constraints / 要做和不要做的约束             │
│  • Reference existing patterns / 引用现有模式                │
│                                                             │
│  Day 4: CODE-SPECIFIC PATTERNS / 代码特定模式                │
│  • Bug fix template / Bug 修复模板                          │
│  • Feature implementation / 功能实现模板                     │
│  • Refactoring template / 重构模板                          │
│                                                             │
│  Day 5: ADVANCED TECHNIQUES / 高级技巧                      │
│  • Meta-prompts (think before coding) / 元提示词             │
│  • Iterative refinement (rounds) / 迭代改进                  │
│  • Self-verification / 自我验证                              │
│                                                             │
│  Day 6: DEBUGGING & RECOVERY / 调试与恢复                    │
│  • Diagnose failures / 诊断失败                              │
│  • Recovery prompts / 恢复提示词                             │
│  • Incremental debugging / 增量调试                          │
│                                                             │
│  Day 7: PUTTING IT ALL TOGETHER / 整合                      │
│  • Capstone project / 毕业项目                               │
│  • Template library / 模板库                                 │
│  • Graduation / 毕业                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Exercise 7.1: Capstone Project / 毕业项目

### Project Options / 项目选项

```
┌─────────────────────────────────────────────────────────────┐
│  OPTION A: Todo API                                        │
│  选项A：待办事项 API                                         │
├─────────────────────────────────────────────────────────────┤
│  Build a REST API with:                                    │
│  • CRUD operations for todos                               │
│  • User authentication                                     │
│  • Data validation                                         │
│  • Unit tests                                              │
│  Tech: Node.js + Express + PostgreSQL                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  OPTION B: Search Feature                                  │
│  选项B：搜索功能                                             │
├─────────────────────────────────────────────────────────────┤
│  Add search to existing app:                               │
│  • Full-text search                                        │
│  • Filters and sorting                                     │
│  • Results pagination                                      │
│  • Performance optimization                                │
│  Tech: React + existing backend API                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  OPTION C: Legacy Refactor                                 │
│  选项C：遗留代码重构                                         │
├─────────────────────────────────────────────────────────────┤
│  Refactor a messy codebase:                                │
│  • Analyze existing code                                   │
│  • Plan refactoring strategy                               │
│  • Implement incrementally                                 │
│  • Maintain functionality                                  │
│  Tech: Any (JavaScript/TypeScript preferred)               │
└─────────────────────────────────────────────────────────────┘
```

### Capstone Requirements / 毕业项目要求

For your chosen project, create:
为你选择的项目创建：

1. **META-PROMPT**: Planning & Analysis / 规划与分析
2. **IMPLEMENTATION PROMPTS (3-5)**: Decomposed steps / 分解的步骤
3. **VERIFICATION PROMPT**: Self-check after implementation / 实现后自检
4. **RECOVERY PROMPT**: In case something goes wrong / 以防出错

---

## Sample Capstone: Todo API / 示例毕业项目：Todo API

### 1. Meta-Prompt: Planning & Analysis / 元提示词：规划与分析

```
I need to build a Todo API with user authentication. Before implementing,
please analyze our options and create a plan.

## Project Context
- Building from scratch (new project)
- Tech stack: Node.js + Express + TypeScript + PostgreSQL
- Will be deployed to production eventually
- Need good test coverage

## Please Analyze

### 1. Project Structure Options
Compare: Simple vs Layered vs Clean Architecture
Recommend the best fit and explain why.

### 2. Authentication Strategy
Compare: JWT vs Sessions vs API Keys
Consider: Security, scalability, implementation effort.

### 3. Database Schema Design
Propose schema for Users and Todos tables.
Include: fields, types, constraints, indexes.

### 4. API Endpoint Design
List all endpoints needed with METHOD /path - description

### 5. Implementation Order
What order should we build things? Draw dependency graph.

## Output Format
- Recommended approach with reasoning
- Proposed file structure
- Implementation phases
- Questions for me

Do NOT write code yet. Wait for my approval.
```

### 2. Implementation Prompts / 实现提示词

#### Prompt 2.1: Project Setup & Database

```
Set up the Todo API project foundation and database schema.

## Project Structure
todo-api/
├── src/
│   ├── config/
│   ├── controllers/
│   ├── middleware/
│   ├── models/
│   ├── routes/
│   ├── services/
│   ├── utils/
│   ├── validators/
│   ├── types/
│   └── app.ts
├── tests/
├── package.json
├── tsconfig.json
└── .env.example

## Dependencies
Production: express, cors, helmet, pg, prisma, zod, bcrypt, jsonwebtoken, dotenv
Development: typescript, ts-node, @types/*, jest, supertest, nodemon

## Database Schema (Prisma)
- Users: id, email, passwordHash, name, timestamps
- Todos: id, title, description, completed, dueDate, priority, userId, timestamps

## Verification
□ npm install completes
□ TypeScript compiles
□ Prisma generates client
□ Migrations run
□ Basic app starts
```

#### Prompt 2.2: Authentication System

```
Implement JWT authentication with register, login, and protected routes.

## Auth Service Methods
- register(email, password, name?) → { user, tokens }
- login(email, password) → { user, tokens }
- refreshToken(token) → { tokens }
- logout(userId) → void

## Token Config
- Access: 15 min, Refresh: 7 days
- Store refresh token hash in database

## Password: bcrypt, cost 12, min 8 chars

## Routes
POST /api/auth/register
POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/logout (protected)
GET  /api/auth/me (protected)

## Security
✅ Hash passwords, httpOnly cookies, validate inputs, generic errors
❌ No plain passwords, no password in responses
```

#### Prompt 2.3: Todo CRUD Operations

```
Implement complete CRUD for Todos with filtering and pagination.

## Service Methods
- create(userId, data) → Todo
- getAll(userId, filters) → { todos, pagination }
- getById(userId, todoId) → Todo | null
- update(userId, todoId, data) → Todo
- delete(userId, todoId) → void
- toggleComplete(userId, todoId) → Todo

## Routes (all protected)
GET    /api/todos         - List with filters/pagination
POST   /api/todos         - Create
GET    /api/todos/:id     - Get single
PATCH  /api/todos/:id     - Update
DELETE /api/todos/:id     - Delete
PATCH  /api/todos/:id/toggle - Toggle completed

## Validation (Zod)
- title: 1-200 chars, required
- description: max 2000, optional
- dueDate: ISO date, future, optional
- priority: LOW/MEDIUM/HIGH, optional

## Error Handling
- 400: Validation error
- 401: Not authenticated
- 404: Not found (also for other user's todos)
```

#### Prompt 2.4: Error Handling & Middleware

```
Add global error handling, logging, and utility middleware.

## Custom Errors
AppError, ValidationError, AuthenticationError, ForbiddenError, NotFoundError

## Error Handler Middleware
- Catch all errors
- Consistent response format
- No stack traces in production
- Handle Prisma/Zod errors

## Logger Utility
- Levels: debug, info, warn, error
- JSON in production, pretty in dev
- Never log sensitive data

## Additional Middleware
- Request logger (method, path, duration, requestId)
- Rate limiter (100/min general, 10/min auth)
- Security (CORS, size limits)

## Update existing code
- Use asyncHandler wrapper
- Replace generic errors with custom classes
```

#### Prompt 2.5: Unit Tests

```
Write comprehensive unit tests for the Todo API.

## Setup
- Jest with ts-jest
- Separate test database
- Coverage threshold: 80%

## Test Helpers
- createTestUser() → user with token
- createTestTodo(userId) → todo
- getAuthHeader(token)
- resetDatabase()

## Test Files

### tests/auth.test.ts
- Register: valid, invalid email, weak password, existing email
- Login: correct, wrong password, non-existent email
- Protected routes: valid token, missing, invalid, expired

### tests/todos.test.ts
- Create: valid, missing title, no auth
- List: user's only, pagination, filters
- Get: owned, not found, other user's
- Update: partial, not found
- Delete: success, other user's

## Patterns
- AAA (Arrange, Act, Assert)
- Descriptive names
- One assertion per test
```

### 3. Verification Prompt / 验证提示词

```
Verify the Todo API implementation is complete and correct.

## Functionality Check
□ Auth: register, login, protected routes, refresh, logout
□ Todos: create, list, get, update, delete, toggle
□ Pagination and filters work
□ Only user's own todos accessible

## Security Check
□ Passwords hashed
□ Can't access other user's todos
□ Rate limiting works
□ No sensitive data in responses

## Error Handling Check
□ 400 for invalid input
□ 401 for missing/invalid auth
□ 404 for not found

## Code Quality Check
□ TypeScript compiles
□ All tests pass
□ Coverage meets threshold

## Report
### ✅ Passed
### ⚠️ Warnings
### ❌ Failed (Must Fix)
```

### 4. Recovery Prompts / 恢复提示词

#### If Auth Has Issues

```
The authentication has issues:

## Working
✅ [List working parts]

## Issues
❌ [Specific issues with location]

## Fix Requirements
- Keep: [what to preserve]
- Fix: [what to change]
- Don't: [what not to modify]

Fix only the identified issues.
```

#### If Tests Fail

```
Some tests are failing:

## Failing Tests
1. [Test name] - [Error]
2. [Test name] - [Error]

## Debug Steps
For each: Check test logic, check implementation, determine which needs fixing.

## Report
For each: Root cause, fix needed, fix applied.
```

---

## Exercise 7.2: Personal Template Library / 个人模板库

Your template library has been created at:
**prompt-template-library.md**

### Library Contents / 库内容

```
9 TEMPLATE CATEGORIES / 9个模板类别:

1. Meta-Prompts (2)        - Planning & analysis
2. Bug Fix (2)             - Standard & performance
3. Feature (3)             - Full, API, Component
4. Refactoring (2)         - Code & file splitting
5. Code Review (2)         - Security & general
6. Test Writing (2)        - Unit & integration
7. Recovery (3)            - General, perf, security
8. Verification (2)        - Implementation & deploy
9. Project Context (1)     - CLAUDE.md template

TOTAL: 19 TEMPLATES
```

### How to Use / 如何使用

```
1. IDENTIFY task type
2. SELECT template
3. FILL IN [placeholders]
4. ADD project context
5. REVIEW & SEND
6. SAVE improvements
```

---

## Exercise 7.3: Graduation Checklist / 毕业清单

```
DAY 1: FUNDAMENTALS
□ I understand: Specific > Vague
□ I can use: CRISPE framework
□ I know: Good prompt structure

DAY 2: TASK DECOMPOSITION
□ I can: Break complex tasks into steps
□ I can: Identify dependencies
□ I can: Chain prompts effectively

DAY 3: CONTEXT & CONSTRAINTS
□ I know: What context to include/exclude
□ I can: Write DO and DON'T constraints
□ I can: Reference existing patterns

DAY 4: CODE-SPECIFIC PATTERNS
□ I have: Bug fix template
□ I have: Feature implementation template
□ I have: Refactoring template

DAY 5: ADVANCED TECHNIQUES
□ I can: Use meta-prompts for planning
□ I can: Build features iteratively
□ I can: Add self-verification

DAY 6: DEBUGGING & RECOVERY
□ I can: Diagnose why prompts fail
□ I can: Write recovery prompts
□ I can: Debug incrementally

DAY 7: PUTTING IT TOGETHER
□ I have: Personal template library
□ I completed: Capstone project prompts
□ I'm ready: To apply in real projects
```

---

## Key Principles Summary / 关键原则总结

```
┌─────────────────────────────────────────────────────────────┐
│              THE 6 PILLARS OF GREAT PROMPTS                 │
│                  优秀提示词的6大支柱                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. BE SPECIFIC / 要具体                                    │
│     Vague prompts → Vague results                          │
│     模糊的提示词 → 模糊的结果                                │
│                                                             │
│  2. PROVIDE CONTEXT / 提供上下文                            │
│     Claude can't read your mind                            │
│     Claude 不能读心                                         │
│                                                             │
│  3. SET CONSTRAINTS / 设定约束                              │
│     Boundaries improve output                              │
│     边界改善输出                                             │
│                                                             │
│  4. DECOMPOSE TASKS / 分解任务                              │
│     Small steps → Better results                           │
│     小步骤 → 更好的结果                                      │
│                                                             │
│  5. ITERATE / 迭代                                          │
│     First attempt rarely perfect                           │
│     第一次尝试很少完美                                       │
│                                                             │
│  6. VERIFY / 验证                                           │
│     Always confirm results                                 │
│     总是确认结果                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## The Master Formula / 大师公式

```
EXCELLENT PROMPT =
    Context (What exists)
  + Task (What to do)
  + Requirements (How to do it)
  + Constraints (Boundaries)
  + Verification (How to confirm)

优秀提示词 =
    上下文（存在什么）
  + 任务（做什么）
  + 要求（如何做）
  + 约束（边界）
  + 验证（如何确认）
```

---

## Next Steps / 下一步

### Immediate / 立即

1. **Practice daily** with real tasks
   每天用真实任务练习

2. **Use your template library** - don't start from scratch
   使用你的模板库 - 不要从头开始

3. **Create CLAUDE.md** for your projects
   为你的项目创建 CLAUDE.md

### Ongoing / 持续

4. **Refine templates** based on what works
   根据有效的内容改进模板

5. **Share learnings** with your team
   与团队分享学习成果

6. **Review this training** when you hit roadblocks
   遇到障碍时回顾此培训

---

## Your Training Materials / 你的培训材料

```
claude-code-prompt-training/
├── claude-code-prompt-training.md    # 7-day overview / 7天概览
├── day1-fundamentals.md              # Fundamentals / 基础
├── day2-task-decomposition.md        # Decomposition / 任务分解
├── day3-context-constraints.md       # Context / 上下文与约束
├── day4-code-specific-patterns.md    # Code patterns / 代码模式
├── day5-advanced-techniques.md       # Advanced / 高级技巧
├── day6-debugging-failures.md        # Debugging / 调试与恢复
├── day7-real-projects.md             # Real projects / 真实项目
└── prompt-template-library.md        # Template library / 模板库
```

---

## Congratulations! / 恭喜！

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│           🎓 TRAINING COMPLETE! / 培训完成！                 │
│                                                             │
│     You've learned how to write high-quality prompts       │
│     for Claude Code. Now go build amazing things!          │
│                                                             │
│     你已经学会了如何为 Claude Code 编写高质量提示词。         │
│     现在去创造令人惊叹的东西吧！                              │
│                                                             │
│           Happy prompting! / 祝提示词编写愉快！              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

*Training created: January 2025*
*Version: 1.0*
