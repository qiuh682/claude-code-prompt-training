# Day 1: Fundamentals of Effective Prompting
# 第一天：有效提示词的基础

**Duration / 时长**: 1-1.5 hours / 1-1.5小时

---

## Learning Objectives / 学习目标
- Understand how Claude Code interprets prompts / 理解 Claude Code 如何解读提示词
- Learn the anatomy of a good prompt / 学习优秀提示词的结构
- Practice writing clear, specific requests / 练习编写清晰、具体的请求

---

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

---

### 2. The CRISPE Framework / CRISPE 框架

| Element | 元素 | Description | 描述 |
|---------|------|-------------|------|
| **C**ontext | 上下文 | Background information | 背景信息 |
| **R**ole | 角色 | What perspective to take | 采用什么视角 |
| **I**nstruction | 指令 | What to do | 要做什么 |
| **S**pecifics | 具体要求 | Details and constraints | 细节和约束 |
| **P**urpose | 目的 | Why this matters | 为什么重要 |
| **E**xamples | 示例 | Show expected output | 展示预期输出 |

---

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

---

## Exercises with Solutions / 练习与答案

### Exercise 1.1: Rewrite Bad Prompts / 重写糟糕的提示词

#### Prompt 1: "make it faster"

**Bad / 差:**
```
make it faster
```

**Good / 好:**
```
The GET /api/users endpoint in src/controllers/userController.ts is slow.
GET /api/users 端点（位于 src/controllers/userController.ts）响应很慢。

Current state / 当前状态:
- Response time: 3-5 seconds for 1000 users
  响应时间：1000个用户需要3-5秒
- The endpoint fetches all users with their orders and profiles
  该端点获取所有用户及其订单和个人资料

Goal / 目标:
- Reduce response time to under 500ms
  将响应时间减少到500ms以下

Constraints / 约束:
- Cannot change the API response structure (frontend depends on it)
  不能更改 API 响应结构（前端依赖它）
- PostgreSQL database, can add indexes if needed
  PostgreSQL 数据库，如需可以添加索引

Please analyze the current implementation and suggest optimizations
(pagination, query optimization, caching, etc.)
请分析当前实现并建议优化方案（分页、查询优化、缓存等）
```

**Key improvements / 关键改进:**
| Added | 添加了 |
|-------|--------|
| Specific file location | 具体文件位置 |
| Measurable current state | 可测量的当前状态 |
| Clear target metric | 明确的目标指标 |
| Technical constraints | 技术约束 |
| Suggested approaches | 建议的方法 |

---

#### Prompt 2: "add tests"

**Bad / 差:**
```
add tests
```

**Good / 好:**
```
Write unit tests for the PaymentService class in src/services/PaymentService.ts
为 src/services/PaymentService.ts 中的 PaymentService 类编写单元测试

Testing setup / 测试配置:
- Framework: Jest with ts-jest
- Test file location: src/services/__tests__/PaymentService.test.ts
  测试文件位置：src/services/__tests__/PaymentService.test.ts

Methods to test / 要测试的方法:
- processPayment()
- refundPayment()
- validateCard()

Test scenarios / 测试场景:
1. Success cases / 成功情况
   - Valid card, sufficient balance / 有效卡片，余额充足

2. Error cases / 错误情况
   - Invalid card number / 无效卡号
   - Expired card / 过期卡片
   - Insufficient funds / 余额不足
   - Network timeout / 网络超时

3. Edge cases / 边界情况
   - Zero amount / 金额为零
   - Maximum transaction limit / 最大交易限额

Mocking requirements / Mock 需求:
- Mock the StripeAPI client (src/lib/stripe.ts)
  Mock Stripe API 客户端
- Mock the database calls
  Mock 数据库调用

Follow AAA pattern (Arrange, Act, Assert) and aim for >80% coverage.
遵循 AAA 模式（准备、执行、断言），目标覆盖率 >80%。
```

**Key improvements / 关键改进:**
| Element | 元素 | Why it matters | 为什么重要 |
|---------|------|----------------|------------|
| Test framework specified | 指定测试框架 | Ensures correct syntax | 确保正确语法 |
| File location | 文件位置 | Follows project structure | 遵循项目结构 |
| Specific methods | 具体方法 | Clear scope | 明确范围 |
| Scenario categories | 场景分类 | Comprehensive coverage | 全面覆盖 |
| Mock instructions | Mock 指令 | Handles dependencies | 处理依赖 |

---

#### Prompt 3: "clean up the code"

**Bad / 差:**
```
clean up the code
```

**Good / 好:**
```
Refactor src/utils/helpers.ts which has become difficult to maintain.
重构 src/utils/helpers.ts，该文件已变得难以维护。

Current problems / 当前问题:
- 800+ lines in a single file / 单个文件超过800行
- Mixed responsibilities (date, string, validation, API helpers)
  职责混合（日期、字符串、验证、API辅助函数）
- Inconsistent naming (some camelCase, some snake_case)
  命名不一致（部分驼峰，部分下划线）
- No TypeScript types (all 'any') / 没有 TypeScript 类型（全是 'any'）
- Duplicate logic in formatDate() and formatDateTime()
  formatDate() 和 formatDateTime() 中有重复逻辑

Desired outcome / 期望结果:
1. Split into separate files by domain:
   按领域拆分为单独文件：
   - src/utils/date.ts
   - src/utils/string.ts
   - src/utils/validation.ts
   - src/utils/api.ts

2. Add proper TypeScript types / 添加正确的 TypeScript 类型

3. Use consistent camelCase naming / 使用一致的驼峰命名

4. Remove duplication / 移除重复代码

Constraints / 约束:
- All existing tests must pass / 所有现有测试必须通过
- Maintain the same public API (function names and signatures)
  保持相同的公共 API（函数名和签名）
- Re-export from src/utils/index.ts for backward compatibility
  从 src/utils/index.ts 重新导出以保持向后兼容
```

**Key improvements / 关键改进:**
| Vague term | 模糊术语 | Made specific | 具体化 |
|------------|----------|---------------|--------|
| "clean up" | "清理" | Split files, add types, fix naming | 拆分文件、添加类型、修复命名 |
| "the code" | "代码" | src/utils/helpers.ts | 具体文件路径 |
| "messy" | "混乱" | 800+ lines, mixed responsibilities | 800+行，职责混合 |
| "better" | "更好" | Specific file structure proposed | 提出具体文件结构 |

---

### Exercise 1.1 Summary / 练习1.1总结

| Bad Prompt | Good Prompt Includes |
|------------|---------------------|
| make it faster | Current metrics, target metrics, constraints |
| add tests | Framework, scenarios, mocking strategy |
| clean up code | Specific problems, desired structure, constraints |

**Pattern / 模式:** `Vague verb` → `Specific action + Context + Measurable goal + Constraints`

---

### Exercise 1.2: Write a Complete Prompt / 编写完整提示词

**Task / 任务:** Create a function that validates email addresses
创建一个验证电子邮件地址的函数

**Complete Prompt / 完整提示词:**

```
Create an email validation function in src/utils/validation.ts
在 src/utils/validation.ts 中创建一个邮箱验证函数

## Function Signature / 函数签名
function validateEmail(email: string): ValidationResult

## Return Type / 返回类型
interface ValidationResult {
  isValid: boolean;
  error?: string;  // Human-readable error message / 人类可读的错误信息
}

## Validation Rules / 验证规则
1. Required field - cannot be empty or whitespace only
   必填字段 - 不能为空或仅包含空格

2. Format - must match pattern: local@domain.tld
   格式 - 必须匹配模式：local@domain.tld

3. Local part (before @):
   本地部分（@之前）：
   - 1-64 characters / 1-64个字符
   - Allowed: letters, numbers, dots, hyphens, underscores
     允许：字母、数字、点、连字符、下划线
   - Cannot start or end with a dot / 不能以点开头或结尾

4. Domain part (after @):
   域名部分（@之后）：
   - Must have at least one dot / 必须至少有一个点
   - TLD must be 2-10 characters / 顶级域名必须是2-10个字符
   - No consecutive dots / 不能有连续的点

## Edge Cases to Handle / 要处理的边界情况
- null / undefined input → return { isValid: false, error: "Email is required" }
- "  " (whitespace) → return { isValid: false, error: "Email is required" }
- "test@" → return { isValid: false, error: "Invalid domain" }
- "@domain.com" → return { isValid: false, error: "Invalid local part" }
- "test@domain" → return { isValid: false, error: "Invalid TLD" }

## Examples / 示例
validateEmail("user@example.com")     → { isValid: true }
validateEmail("user.name@domain.co")  → { isValid: true }
validateEmail("invalid-email")        → { isValid: false, error: "Invalid email format" }
validateEmail("")                     → { isValid: false, error: "Email is required" }

## Constraints / 约束
- Do not use external libraries (no validator.js, etc.)
  不要使用外部库
- Use regex for pattern matching / 使用正则表达式进行模式匹配
- Add JSDoc comment explaining usage / 添加 JSDoc 注释说明用法
- Export the function and the ValidationResult interface
  导出函数和 ValidationResult 接口
```

**Why This Works / 为什么这个有效:**

| Element | 元素 | Purpose | 目的 |
|---------|------|---------|------|
| File location | 文件位置 | No ambiguity where to put it | 明确放置位置 |
| Type signature | 类型签名 | Clear contract | 明确契约 |
| Return type defined | 定义返回类型 | Consistent output | 一致的输出 |
| Numbered rules | 编号规则 | Easy to verify | 易于验证 |
| Edge cases with expected output | 边界情况及预期输出 | Testable requirements | 可测试的需求 |
| Examples | 示例 | Shows expected behavior | 展示预期行为 |
| Constraints | 约束 | Prevents unwanted solutions | 防止不想要的解决方案 |

---

### Exercise 1.3: Identify Missing Information / 识别缺失信息

**Original Prompt / 原始提示词:**
```
Add a login feature to my app
```

**Missing Information by Category / 按类别缺失的信息:**

#### 1. Technical Stack / 技术栈
| Missing | 缺失 | Why it matters | 为什么重要 |
|---------|------|----------------|------------|
| Frontend framework | 前端框架 | React? Vue? Angular? Vanilla JS? |
| Backend language | 后端语言 | Node? Python? Go? Java? |
| Database | 数据库 | PostgreSQL? MongoDB? MySQL? |
| Existing auth setup | 现有认证设置 | Starting from scratch or extending? |

#### 2. Authentication Method / 认证方式
| Missing | 缺失 | Options | 选项 |
|---------|------|---------|------|
| Auth type | 认证类型 | Session-based? JWT? OAuth? |
| Third-party auth | 第三方认证 | Google? GitHub? Facebook? |
| Token storage | Token 存储 | Cookie? localStorage? Memory? |
| Token expiration | Token 过期 | How long? Refresh tokens? |

#### 3. User Interface / 用户界面
| Missing | 缺失 | Questions | 问题 |
|---------|------|-----------|------|
| Form fields | 表单字段 | Email+password? Username? Phone? |
| Form location | 表单位置 | Separate page? Modal? Inline? |
| Design system | 设计系统 | Existing components to use? |
| Responsive needs | 响应式需求 | Mobile support required? |

#### 4. Security Requirements / 安全需求
| Missing | 缺失 | Considerations | 考虑事项 |
|---------|------|----------------|----------|
| Password rules | 密码规则 | Min length? Complexity? |
| Rate limiting | 限流 | Max login attempts? |
| 2FA/MFA | 双因素认证 | Required? Optional? |
| HTTPS | 安全传输 | Already configured? |
| CSRF protection | CSRF 防护 | Needed? How? |

#### 5. User Experience / 用户体验
| Missing | 缺失 | Questions | 问题 |
|---------|------|-----------|------|
| Error messages | 错误信息 | Generic or specific? |
| "Remember me" | "记住我" | Needed? How long? |
| Forgot password | 忘记密码 | Include this flow? |
| Redirect after login | 登录后跳转 | Where? Previous page? |
| Loading states | 加载状态 | Spinners? Disabled buttons? |

#### 6. Data & Storage / 数据与存储
| Missing | 缺失 | Questions | 问题 |
|---------|------|-----------|------|
| User schema | 用户模式 | What fields exist? |
| Password hashing | 密码哈希 | bcrypt? argon2? Cost factor? |
| Existing users | 现有用户 | Migration needed? |

#### 7. Integration / 集成
| Missing | 缺失 | Questions | 问题 |
|---------|------|-----------|------|
| API structure | API 结构 | REST? GraphQL? Existing patterns? |
| State management | 状态管理 | Redux? Context? Zustand? |
| Protected routes | 受保护路由 | Which routes need auth? |

#### 8. Project Context / 项目上下文
| Missing | 缺失 | Questions | 问题 |
|---------|------|-----------|------|
| File structure | 文件结构 | Where to add new files? |
| Coding standards | 编码标准 | Existing patterns to follow? |
| Testing requirements | 测试需求 | Unit tests? E2E tests? |

---

**Improved Prompt / 改进后的提示词:**

```
Add email/password login to my React + Node.js app.
为我的 React + Node.js 应用添加邮箱/密码登录。

## Tech Stack / 技术栈
- Frontend: React 18 + TypeScript (src/client/)
- Backend: Express.js (src/server/)
- Database: PostgreSQL with Prisma ORM
- State: Zustand (src/client/store/)

## Requirements / 需求

### Backend / 后端
- POST /api/auth/login endpoint
- Use JWT tokens (access + refresh)
- Access token: 15min, Refresh token: 7 days
- Store refresh token in httpOnly cookie
- Password: bcrypt with cost 12
- Rate limit: 5 attempts per minute per IP

### Frontend / 前端
- Login form at /login route
- Fields: email, password, "remember me" checkbox
- Use existing Button and Input components from src/client/components/ui/
- Redirect to /dashboard after successful login
- Show inline error messages

### Security / 安全
- CSRF token validation
- Generic error message: "Invalid email or password"
- Sanitize all inputs

### Not Needed Now / 暂不需要
- Social login (Google, etc.)
- 2FA
- Forgot password flow

Please follow the patterns in src/server/controllers/userController.ts
for the backend implementation.
```

---

## Day 1 Key Takeaways / 第一天关键收获

```
┌─────────────────────────────────────────────────────────────┐
│  FROM VAGUE → TO SPECIFIC                                   │
│  从模糊 → 到具体                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ❌ "make it faster"                                        │
│  ✅ Current: 3s → Target: 500ms, file: X, constraints: Y    │
│                                                             │
│  ❌ "add tests"                                             │
│  ✅ Jest, these methods, these scenarios, mock these deps   │
│                                                             │
│  ❌ "clean up code"                                         │
│  ✅ Split into 4 files, add types, fix naming, keep API     │
│                                                             │
│  ❌ "add login"                                             │
│  ✅ JWT + React + specific endpoints + security rules       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### The Formula / 公式

```
Good Prompt = What + Where + How + Constraints + Expected Output
好的提示词 = 什么 + 哪里 + 如何 + 约束 + 预期输出
```

---

## Quick Reference / 快速参考

### Prompt Quality Checklist / 提示词质量检查清单

Before sending any prompt, verify:
发送任何提示词之前，验证：

```
□ WHAT: Is the task clearly defined?
  什么：任务是否明确定义？

□ WHERE: Are file paths/locations specified?
  哪里：是否指定了文件路径/位置？

□ HOW: Are there technical requirements?
  如何：是否有技术要求？

□ CONSTRAINTS: Are limitations stated?
  约束：是否说明了限制？

□ OUTPUT: Is the expected result described?
  输出：是否描述了预期结果？

□ EXAMPLES: Are there examples if needed?
  示例：如果需要是否有示例？
```

---

## Homework / 作业 (Optional)

Practice by writing prompts for your own real tasks today:
通过为今天你自己的真实任务编写提示词来练习：

1. Write your initial prompt / 写出你的初始提示词
2. Review it against the checklist / 对照检查清单审查
3. Improve it before sending / 发送前改进它
4. Note what worked and what didn't / 记录什么有效什么无效

---

**Next: Day 2 - Task Decomposition / 下一课：第二天 - 任务分解**
