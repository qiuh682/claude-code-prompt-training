# Day 3: Context and Constraints
# 第三天：上下文与约束

**Duration / 时长**: 1-1.5 hours / 1-1.5小时

---

## Learning Objectives / 学习目标
- Provide effective context without overwhelming / 提供有效的上下文而不过载
- Set clear constraints and boundaries / 设定清晰的约束和边界
- Reference existing code and patterns / 引用现有代码和模式

---

## Core Concepts / 核心概念

### 1. The Problem / 问题

```
❌ Without Context / 没有上下文:
"Add validation to the form"
→ What form? What framework? What rules? What patterns exist?
→ 什么表单？什么框架？什么规则？存在什么模式？

✅ With Context / 有上下文:
"Add Zod validation to the React registration form in src/components/RegisterForm.tsx,
following the patterns in src/utils/validators.ts"
→ Clear location, framework, patterns to follow
→ 清晰的位置、框架、要遵循的模式
```

### 2. Context Layering / 上下文分层

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

### 3. Types of Constraints / 约束类型

| Type | 类型 | Example | 示例 |
|------|------|---------|------|
| Technical | 技术 | "Must work with Node 18+" | "必须支持 Node 18+" |
| Style | 风格 | "Follow existing naming conventions" | "遵循现有命名规范" |
| Performance | 性能 | "Response time under 100ms" | "响应时间低于100ms" |
| Security | 安全 | "No eval(), sanitize all inputs" | "禁止 eval()，清理所有输入" |
| Scope | 范围 | "Only modify files in src/auth/" | "只修改 src/auth/ 中的文件" |

---

## Exercises with Solutions / 练习与答案

### Exercise 3.1: Context Extraction / 上下文提取

**Task / 任务:** Add caching to an API endpoint that fetches user profiles
为获取用户资料的 API 端点添加缓存

---

#### ESSENTIAL (Must Include) / 必要（必须包含）

| Context | 上下文 | Why Essential | 为什么必要 |
|---------|--------|---------------|------------|
| **File location** | 文件位置 | `src/controllers/userController.ts` - Where to add the code | 在哪里添加代码 |
| **Current caching setup** | 当前缓存设置 | "We use Redis" or "No caching yet" - Determines approach | 决定方法 |
| **Cache invalidation needs** | 缓存失效需求 | When should cache be cleared? User update? Timeout? | 何时清除缓存？ |
| **Performance target** | 性能目标 | "Reduce response time from 500ms to <50ms" - Measurable goal | 可衡量的目标 |

**Example / 示例:**
```
The GET /api/users/:id endpoint in src/controllers/userController.ts
currently takes 400-500ms because it queries the database directly.

We have Redis configured (src/lib/redis.ts) but it's not used for this endpoint.

Cache requirements:
- Cache individual user profiles
- TTL: 5 minutes
- Invalidate when user updates their profile
```

---

#### HELPFUL (Nice to Have) / 有帮助（有则更好）

| Context | 上下文 | Why Helpful | 为什么有帮助 |
|---------|--------|-------------|--------------|
| **Existing caching patterns** | 现有缓存模式 | "See ProductService for caching example" - Ensures consistency | 确保一致性 |
| **Traffic patterns** | 流量模式 | "10K requests/min to this endpoint" - Helps choose strategy | 帮助选择策略 |
| **Error handling conventions** | 错误处理约定 | How to handle Redis connection failures | 如何处理 Redis 连接失败 |
| **Logging requirements** | 日志需求 | "Log cache hits/misses for monitoring" | 记录缓存命中/未命中 |

**Example / 示例:**
```
Reference: See src/services/ProductService.ts lines 45-60 for our
standard caching pattern with error handling.

This endpoint receives ~10K requests/minute during peak hours.

Use the logger from src/utils/logger.ts to log cache hits/misses.
```

---

#### AVOID (Don't Include) / 避免（不要包含）

| Context | 上下文 | Why Avoid | 为什么避免 |
|---------|--------|-----------|------------|
| **Unrelated code history** | 不相关的代码历史 | "We used to use Memcached in 2019..." - Irrelevant | 无关 |
| **Full file contents** | 完整文件内容 | 500 lines of code when only 20 are relevant | 只有20行相关却给500行 |
| **Business justification** | 业务理由 | "The CEO wants this faster" - Not technical | 非技术性的 |
| **Future plans** | 未来计划 | "Later we might add GraphQL" - Not relevant now | 当前不相关 |
| **Obvious information** | 显而易见的信息 | "Redis is a key-value store" - Claude knows this | Claude 知道这个 |

---

#### Complete Prompt Example / 完整提示词示例

```
Add Redis caching to the user profile endpoint.
为用户资料端点添加 Redis 缓存。

## Location / 位置
src/controllers/userController.ts - getUserById function (lines 45-70)

## Current Implementation / 当前实现
async function getUserById(id: string) {
  const user = await db.users.findById(id);  // ~400ms
  return user;
}

## Caching Setup / 缓存设置
- Redis client: src/lib/redis.ts (already configured)
- Pattern to follow: src/services/ProductService.ts lines 45-60

## Requirements / 需求
- Cache key format: `user:profile:{userId}`
- TTL: 5 minutes (300 seconds)
- Return cached data if available, otherwise fetch and cache
- Handle Redis errors gracefully (fall back to DB)

## Cache Invalidation / 缓存失效
Add cache invalidation to the updateUser function in the same file.
Clear cache when user profile is updated.

## Constraints / 约束
- Don't modify the function signature
- Log cache hits/misses using src/utils/logger.ts
- Use existing error handling patterns
```

---

### Exercise 3.2: Write Constraints / 编写约束

---

#### Scenario A: Legacy Codebase / 场景A：遗留代码库

**Context:** 10-year-old PHP codebase, no tests, inconsistent patterns

```
DO / 要做:
─────────────────────────────────────────────────────────────

✅ Match the existing code style in the immediate file
   匹配当前文件中现有的代码风格
   → Even if it's not ideal, consistency matters more

✅ Add defensive null checks and error handling
   添加防御性的空值检查和错误处理
   → Legacy code often has unexpected states

✅ Keep changes minimal and isolated
   保持更改最小化和隔离
   → Reduce risk of breaking unknown dependencies

✅ Add inline comments explaining the new code
   添加内联注释解释新代码
   → Future maintainers need context


DON'T / 不要:
─────────────────────────────────────────────────────────────

❌ Don't refactor surrounding code
   不要重构周围的代码
   → Out of scope, high risk without tests

❌ Don't introduce new dependencies or libraries
   不要引入新的依赖或库
   → May conflict with existing setup

❌ Don't change existing function signatures
   不要更改现有函数签名
   → Unknown callers may break

❌ Don't use modern PHP features (8.x) if codebase uses PHP 7.x
   如果代码库使用 PHP 7.x，不要使用现代 PHP 特性（8.x）
```

---

#### Scenario B: Security-Sensitive Feature / 场景B：安全敏感功能

**Context:** Payment processing integration for e-commerce

```
DO / 要做:
─────────────────────────────────────────────────────────────

✅ Validate ALL inputs at every boundary
   在每个边界验证所有输入

✅ Use parameterized queries / prepared statements
   使用参数化查询/预处理语句

✅ Log all payment attempts (success and failure)
   记录所有支付尝试（成功和失败）

✅ Use environment variables for all credentials
   所有凭证使用环境变量

✅ Implement idempotency for payment operations
   为支付操作实现幂等性

✅ Return generic error messages to users
   向用户返回通用错误信息


DON'T / 不要:
─────────────────────────────────────────────────────────────

❌ Don't log sensitive data (card numbers, CVV, full tokens)
   不要记录敏感数据（卡号、CVV、完整令牌）

❌ Don't store raw credit card data
   不要存储原始信用卡数据

❌ Don't use string concatenation for queries
   不要使用字符串拼接构建查询

❌ Don't expose stack traces or internal errors to users
   不要向用户暴露堆栈跟踪或内部错误

❌ Don't disable HTTPS or certificate validation
   不要禁用 HTTPS 或证书验证

❌ Don't implement custom cryptography
   不要实现自定义加密
```

---

#### Scenario C: Database Query Optimization / 场景C：数据库查询优化

**Context:** Query takes 30 seconds, blocking other operations

```
DO / 要做:
─────────────────────────────────────────────────────────────

✅ First analyze with EXPLAIN/EXPLAIN ANALYZE
   首先使用 EXPLAIN/EXPLAIN ANALYZE 分析

✅ Add indexes for columns in WHERE and JOIN clauses
   为 WHERE 和 JOIN 子句中的列添加索引

✅ Test with production-like data volume
   使用类似生产环境的数据量测试

✅ Measure before and after
   优化前后进行测量

✅ Consider query result caching if data doesn't change often
   如果数据不经常变化，考虑查询结果缓存


DON'T / 不要:
─────────────────────────────────────────────────────────────

❌ Don't add indexes blindly
   不要盲目添加索引

❌ Don't change query results/behavior
   不要改变查询结果/行为

❌ Don't denormalize without measuring first
   不要在没有先测量的情况下反规范化

❌ Don't remove existing indexes without analysis
   不要在没有分析的情况下删除现有索引

❌ Don't optimize prematurely
   不要过早优化

❌ Don't use FORCE INDEX unless absolutely necessary
   除非绝对必要，不要使用 FORCE INDEX
```

---

### Exercise 3.3: Pattern Reference / 模式引用

**Task / 任务:** Create OrderService following UserService patterns
创建 OrderService，遵循 UserService 的模式

---

#### Pattern Reference Prompt / 模式引用提示词

```
Create an OrderService class following the patterns in UserService.
创建一个 OrderService 类，遵循 UserService 中的模式。

## Pattern to Follow / 要遵循的模式
src/services/UserService.ts

## Aspects to Copy from UserService / 从 UserService 复制的方面

### 1. Class Structure / 类结构
- Private constructor with dependency injection
  带依赖注入的私有构造函数
- Static getInstance() for singleton pattern
  用于单例模式的静态 getInstance()
- Separate public methods from private helpers
  分离公共方法和私有辅助函数

### 2. Error Handling Pattern (lines 45-60) / 错误处理模式
- Wrap operations in try-catch
  用 try-catch 包装操作
- Throw custom errors from src/errors/
  抛出 src/errors/ 中的自定义错误
- Log errors with context before rethrowing
  重新抛出前记录带上下文的错误

### 3. Caching Pattern (lines 78-95) / 缓存模式
- Check cache first, return if hit
  先检查缓存，命中则返回
- Fetch from DB if miss
  未命中则从数据库获取
- Cache result before returning
  返回前缓存结果

### 4. Validation Pattern (lines 30-44) / 验证模式
- Validate input at start of each public method
  在每个公共方法开始时验证输入
- Use Zod schemas from src/schemas/
  使用 src/schemas/ 中的 Zod 模式

## New Service Requirements / 新服务需求

### OrderService Location / 位置
src/services/OrderService.ts

### Methods to Implement / 要实现的方法
| Method | Similar to in UserService |
|--------|---------------------------|
| getOrderById(id) | getUserById(id) |
| getOrdersByUserId(userId) | (new - paginated list) |
| createOrder(data) | createUser(data) |
| updateOrderStatus(id, status) | updateUser(id, data) |
| cancelOrder(id) | deleteUser(id) |

### Order-Specific Differences / 订单特有的差异

1. **Status workflow** / 状态工作流
   Orders have status transitions: pending → paid → shipped → delivered
   - Validate status transitions

2. **Related entities** / 关联实体
   - Order has many OrderItems (need to fetch together)
   - Include user info in order response

3. **Cache invalidation** / 缓存失效
   - Invalidate user's order list when any order changes
   - Key pattern: `order:byId:{orderId}`, `orders:byUser:{userId}`

## Verification / 验证
After implementation, these should work:

const orderService = OrderService.getInstance();
const order = await orderService.getOrderById('order-123');
const orders = await orderService.getOrdersByUserId('user-456', { page: 1, limit: 10 });
```

---

## Day 3 Key Takeaways / 第三天关键收获

```
┌─────────────────────────────────────────────────────────────┐
│              CONTEXT & CONSTRAINTS PRINCIPLES               │
│                  上下文与约束原则                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. LAYER YOUR CONTEXT / 分层你的上下文                      │
│     Project → Task → Immediate                             │
│                                                             │
│  2. ESSENTIAL vs NOISE / 必要 vs 噪音                       │
│     Include what Claude NEEDS                              │
│     Exclude what CLUTTERS                                  │
│                                                             │
│  3. DO and DON'T / 要做和不要做                              │
│     Explicit boundaries improve output                     │
│                                                             │
│  4. REFERENCE PATTERNS / 引用模式                           │
│     Point to existing code as examples                     │
│     Specify what to copy and what's different              │
│                                                             │
│  5. CONSTRAINTS BY CATEGORY / 按类别约束                     │
│     Security, Compatibility, Style, Scope, Performance     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Reference / 快速参考

### Context Checklist / 上下文检查清单

```
□ File path and line numbers?
  文件路径和行号？
□ Current state/implementation?
  当前状态/实现？
□ Target state/behavior?
  目标状态/行为？
□ Existing patterns to follow?
  要遵循的现有模式？
□ Removed irrelevant info?
  移除了无关信息？
```

### Constraint Categories / 约束类别

```
COMPATIBILITY / 兼容性
• Language version (ES6+, Python 3.9+, PHP 7.4)
• Browser support (Chrome 90+, no IE11)
• Node version (18+, 20+)

SECURITY / 安全
• Input validation required
• No eval(), no dynamic SQL
• Sanitize outputs

STYLE / 风格
• Follow existing patterns
• Naming conventions
• File organization

SCOPE / 范围
• Only modify specified files
• Don't refactor unrelated code
• Keep changes minimal

PERFORMANCE / 性能
• Response time < X ms
• Memory usage < Y MB
• No blocking operations
```

---

## The Formula / 公式

```
Good Context = Essential Info + Relevant Patterns - Noise
好的上下文 = 必要信息 + 相关模式 - 噪音

Good Constraints = DO (what to follow) + DON'T (what to avoid)
好的约束 = 要做（遵循什么）+ 不要做（避免什么）
```

---

## Homework / 作业 (Optional)

For your next Claude Code task:
对于你的下一个 Claude Code 任务：

1. **Write context in three layers** (project, task, immediate)
   用三层写上下文

2. **List 3 DO and 3 DON'T constraints**
   列出3个要做和3个不要做的约束

3. **Find an existing pattern to reference**
   找一个现有模式来引用

4. **Review: did you include noise? Remove it.**
   审查：你包含了噪音吗？移除它。

---

**Next: Day 4 - Code-Specific Prompt Patterns / 下一课：第四天 - 代码特定的提示词模式**
