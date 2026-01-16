# Day 6: Debugging Prompts & Handling Failures
# 第六天：调试提示词与处理失败

**Duration / 时长**: 1-1.5 hours / 1-1.5小时

---

## Learning Objectives / 学习目标
- Diagnose why prompts don't work as expected / 诊断提示词为什么没有按预期工作
- Refine prompts based on results / 根据结果改进提示词
- Handle common failure modes / 处理常见的失败模式

---

## Core Concepts / 核心概念

### When Things Go Wrong / 当事情出错时

```
┌─────────────────────────────────────────────────────────────┐
│            WHEN THINGS GO WRONG                             │
│              当事情出错时                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🔍 DIAGNOSE    - Why didn't it work?                      │
│     诊断         - 为什么不工作？                            │
│                                                             │
│  📝 FEEDBACK    - Give specific corrections                │
│     反馈         - 给出具体修正                              │
│                                                             │
│  🔄 RECOVER     - Fix without starting over                │
│     恢复         - 不重新开始地修复                          │
│                                                             │
│  🛡️ PREVENT     - Avoid future failures                    │
│     预防         - 避免未来的失败                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Common Prompt Failures / 常见提示词失败

| Problem | Symptom | Cause |
|---------|---------|-------|
| Wrong approach | Works but not what you wanted | Unclear requirements |
| Incomplete | Missing pieces | Scope too large |
| Ignores constraints | Breaks rules you set | Constraints buried/unclear |
| Wrong file | Changed wrong thing | Ambiguous reference |
| Style mismatch | Doesn't fit codebase | No style reference |

---

## Exercises with Solutions / 练习与答案

### Exercise 6.1: Diagnose a Failure / 诊断失败

**Original Prompt / 原始提示词:** "Add caching to the API"

**Result:** In-memory Map cache, no TTL, no invalidation, one endpoint only

---

#### Failure Diagnosis Checklist / 失败诊断清单

```
□ CONTEXT: Was enough background provided?
  ❌ Missing:
  • No mention of Redis being available
  • No mention of existing infrastructure
  • No mention of current performance problems

□ SPECIFICITY: Were requirements detailed enough?
  ❌ Missing:
  • Which caching technology to use (Redis)
  • TTL requirements
  • What data to cache
  • Cache key format

□ CONSTRAINTS: Were limitations stated?
  ❌ Missing:
  • "Use Redis, not in-memory"
  • "Must handle cache invalidation"
  • "Don't break existing async patterns"

□ PATTERNS: Were existing patterns referenced?
  ❌ Missing:
  • No reference to existing code style
  • No mention of async/await usage
  • No example of similar implementation

□ SCOPE: Was scope clearly defined?
  ❌ Missing:
  • Which endpoints to cache
  • Files to modify

□ EXAMPLES: Were examples provided if needed?
  ❌ Missing:
  • Expected cache behavior example
  • Cache key format example
```

---

#### Root Cause Analysis / 根本原因分析

```
PROMPT: "Add caching to the API"

Claude's interpretation:
✓ Add caching ← Did this
✓ To the API ← Did this
? What kind of caching? ← Had to guess (chose Map)
? How long to cache? ← Had to guess (forever)
? Which endpoints? ← Had to guess (just one)
? Invalidation? ← Wasn't asked for

Claude did exactly what was asked - the prompt was
ambiguous, so Claude made reasonable (but wrong) choices.
```

---

#### The Fixed Prompt / 修复后的提示词

```
Add Redis caching to all GET endpoints in the API.

## Context
- Redis is configured at src/lib/redis.ts
- Current endpoints are slow (200-500ms), target is <50ms for cached
- All controller files are in src/controllers/

## Requirements

### Caching Strategy
- Cache all GET endpoints that return lists or single resources
- Cache key format: `api:{resource}:{id}` or `api:{resource}:list:{queryHash}`
- TTL: 5 minutes for lists, 10 minutes for single resources

### Cache Invalidation
- Clear resource cache on POST/PUT/PATCH/DELETE to that resource
- Clear list cache when any item in that resource changes

### Implementation
- Create a caching middleware or utility function
- Follow the async/await pattern used in existing controllers
- Handle Redis connection errors gracefully (fall back to no cache)

## Existing Pattern
Follow the pattern in src/controllers/productController.ts

## Scope
Files to modify:
- src/middleware/cache.ts (create new)
- src/controllers/*.ts (add caching)
- src/lib/redis.ts (add cache helpers if needed)
```

---

### Exercise 6.2: Write Recovery Prompts / 编写恢复提示词

---

#### Scenario A: Inefficient Code / 场景A：低效代码

```
The implementation works correctly, but has performance issues that need fixing.

## What's Working (Keep This)
✅ The logic is correct
✅ The output format is correct
✅ Error handling is good

## Performance Issues to Fix

### Issue 1: O(n²) nested loops
Location: lines 25-40

Current (O(n²)):
for (const user of users) {
  for (const order of orders) {
    if (order.userId === user.id) { ... }
  }
}

Fix (O(n)):
const ordersByUser = new Map(orders.map(o => [o.userId, o]));
for (const user of users) {
  const order = ordersByUser.get(user.id);
}

### Issue 2: N+1 Database Queries
Location: lines 50-60

Current (10 queries):
for (const id of userIds) {
  const user = await db.users.findById(id);
}

Fix (1 query):
const users = await db.users.findByIds(userIds);

### Issue 3: Loading entire file into memory
Location: lines 70-80

Fix: Use streaming for large files

## Constraints
- Keep the same function signature
- Keep the same return format
- Don't change the working logic, only optimize
```

---

#### Scenario B: Security Vulnerability / 场景B：安全漏洞

```
🚨 SECURITY: The implementation has critical vulnerabilities that must be fixed.

## What's Working (Keep This)
✅ The endpoint routing is correct
✅ The business logic is correct
✅ The response format is correct

## Critical Security Fixes Required

### 🔴 CRITICAL: SQL Injection Vulnerability
Location: src/controllers/userController.ts:45

DANGEROUS:
const query = `SELECT * FROM users WHERE id = '${userId}'`;

SAFE:
const result = await db.users.where('id', userId).first();

### 🔴 CRITICAL: Stack Trace Exposure
Location: src/controllers/userController.ts:80

DANGEROUS:
catch (error) {
  res.status(500).json({ error: error.stack });
}

SAFE:
catch (error) {
  logger.error('User fetch failed', { error, userId });
  res.status(500).json({
    error: 'An internal error occurred',
    requestId: req.id
  });
}

### 🟡 HIGH: Missing Input Validation
Location: src/controllers/userController.ts:30

Fix: Add Zod validation before processing

## DO NOT
❌ Do not change the endpoint URLs
❌ Do not change the success response format
❌ Do not remove any existing functionality
```

---

#### Scenario C: Pattern Mismatch / 场景C：模式不匹配

```
The code works but doesn't match our project's patterns and conventions.
Please refactor to align with our codebase style.

## What's Working (Keep This)
✅ The functionality is correct
✅ The logic is correct
✅ The tests pass

## Pattern Violations to Fix

### Issue 1: Callbacks → Async/Await
Current:
function getUser(id, callback) {
  db.query('...', (err, result) => {
    if (err) callback(err);
    else callback(null, result);
  });
}

Our pattern:
async function getUser(id: string): Promise<User> {
  const result = await db.users.findById(id);
  return result;
}

### Issue 2: var → const/let
Convert all var to const (immutable) or let (mutable)

### Issue 3: Business Logic in Controller → Service Layer
Move business logic from controller to service layer.
Reference: src/controllers/productController.ts + src/services/productService.ts

## After Refactoring
□ All callbacks converted to async/await
□ No var keywords remain
□ Controller files are <50 lines each
□ Business logic moved to service layer
□ Existing tests still pass
```

---

#### Recovery Prompt Structure / 恢复提示词结构

```
┌─────────────────────────────────────────────────────────────┐
│              RECOVERY PROMPT STRUCTURE                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. ACKNOWLEDGE GOOD PARTS / 承认好的部分                    │
│     "The logic is correct, keep this..."                   │
│                                                             │
│  2. SPECIFIC ISSUES / 具体问题                              │
│     - Location (file:line)                                 │
│     - Current code (what's wrong)                          │
│     - Target code (what it should be)                      │
│                                                             │
│  3. CONSTRAINTS / 约束                                      │
│     "Keep X, only change Y"                                │
│                                                             │
│  4. VERIFICATION / 验证                                     │
│     "After fixing, verify by..."                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### Exercise 6.3: Incremental Debugging / 增量调试

**Bug:** Order total sometimes differs from cart total

---

#### Incremental Debugging Prompt / 增量调试提示词

```
Debug the order total discrepancy issue step by step.

## Problem Description
Users report: "My cart showed $150, but checkout charged $165"
This happens intermittently, not every time.

## Debug Step by Step

Please investigate each step IN ORDER. After each step, report:
- What you checked
- What you found
- Is this step OK or suspicious?

Wait for my confirmation before moving to the next step.

---

### Step 1: Cart Data Source
Location: src/services/cartService.ts

Check:
□ How is cart total calculated?
□ What data is used?
□ Is there any rounding?

Questions to answer:
- Does getCartTotal() use current prices or stored prices?
- Are prices stored as numbers or strings?

---

### Step 2: Cart to Checkout Transition
Location: src/pages/Checkout.tsx, src/api/checkout.ts

Check:
□ What data is passed from cart page to checkout?
□ Is the total recalculated or passed from cart?
□ Any data transformation happening?

Questions to answer:
- Is there a time gap where prices could change?
- Are we fetching fresh prices at checkout?

---

### Step 3: Checkout Calculation
Location: src/services/checkoutService.ts

Check:
□ How is checkout total calculated?
□ What additional costs are added? (Tax, Shipping, Fees)
□ Is the calculation different from cart?

---

### Step 4: Price Source Consistency
Location: src/services/productService.ts, database

Check:
□ Where do cart items get their prices?
□ Where does checkout get prices?
□ Are they the same source?

---

### Step 5: Race Conditions
Location: src/api/checkout.ts

Check:
□ Multiple async operations that could conflict?
□ Could price be fetched twice with different results?
□ Any caching issues?

---

### Step 6: Rounding & Floating Point
Location: All calculation functions

Check:
□ How is money handled? (cents vs dollars)
□ Any floating point arithmetic issues?
□ When/how is rounding applied?

---

## After Each Step

Report in this format:

### Step X Results
**Checked:** [What you looked at]
**Found:** [What you discovered]
**Status:** ✅ OK / ⚠️ Suspicious / ❌ Bug Found
**Evidence:** [Code snippet or data]
**Recommendation:** [If suspicious: what to investigate or fix]

---

## Start With Step 1
Please begin with Step 1 and report your findings.
```

---

#### Why Incremental Debugging Works / 为什么增量调试有效

```
┌─────────────────────────────────────────────────────────────┐
│              INCREMENTAL DEBUGGING BENEFITS                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🎯 FOCUSED                                                │
│     One thing at a time, not overwhelming                  │
│                                                             │
│  📍 TRACEABLE                                               │
│     Know exactly where the bug is                          │
│                                                             │
│  ✅ VERIFIABLE                                              │
│     Confirm each part works before moving on               │
│                                                             │
│  🧠 EDUCATIONAL                                             │
│     Understand the system, not just fix the bug            │
│                                                             │
│  📝 DOCUMENTED                                              │
│     Creates a record of investigation                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Day 6 Key Takeaways / 第六天关键收获

```
┌─────────────────────────────────────────────────────────────┐
│           DEBUGGING & RECOVERY PRINCIPLES                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🔍 DIAGNOSE SYSTEMATICALLY                                │
│     Use checklist: Context, Specificity, Constraints,      │
│     Patterns, Scope, Examples                              │
│                                                             │
│  📝 GIVE SPECIFIC FEEDBACK                                 │
│     - Acknowledge what's working                           │
│     - Pinpoint exact issues with locations                 │
│     - Show current vs target code                          │
│                                                             │
│  🔄 RECOVER, DON'T RESTART                                 │
│     Keep good parts, fix specific issues                   │
│                                                             │
│  📊 DEBUG INCREMENTALLY                                    │
│     Step by step, verify each checkpoint                   │
│                                                             │
│  🛡️ PREVENT FUTURE FAILURES                                │
│     Learn from failures, improve prompts                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Reference / 快速参考

### Failure Diagnosis Checklist / 失败诊断清单

```
□ Context provided?
□ Specific enough?
□ Constraints clear?
□ Patterns referenced?
□ Scope defined?
□ Examples given?
```

### Recovery Prompt Structure / 恢复提示词结构

```
1. ✅ Acknowledge good parts
2. ❌ List specific issues (location + current + target)
3. 🚫 Constraints (what not to change)
4. ✓ Verification steps
```

### Incremental Debug Flow / 增量调试流程

```
Step 1 → Report → Confirm → Step 2 → Report → Confirm → ...

Each step report:
- What you checked
- What you found
- Status: OK / Suspicious / Bug Found
- Evidence (code/data)
```

---

## Recovery Templates / 恢复模板

```
PERFORMANCE FIX:
"The implementation works but is slow. Keep [good parts].
Fix these performance issues: [list with current → target].
After fixing, should process X in <Y time."

SECURITY FIX:
"🚨 SECURITY: Critical fixes needed. Keep [good parts].
Fix immediately: [prioritized list with severity].
Do not: [things to preserve].
Verify by: [security tests]."

PATTERN FIX:
"Works but doesn't match our patterns. Keep [good parts].
Convert: [old pattern] → [our pattern].
Reference: [example files].
After refactoring: [checklist]."

BUG FIX:
"The code has a bug. Input X produces Y, expected Z.
Keep [working parts]. Fix the issue in [location].
Don't change [other things].
Verify: [test case]."
```

---

## Common Recovery Scenarios / 常见恢复场景

| Scenario | Recovery Approach |
|----------|-------------------|
| Wrong approach | "The approach doesn't fit because [X]. Let's try [Y] instead." |
| Incomplete | "Good start. Now add: [missing parts]" |
| Inefficient | "Works but slow. Optimize [specific parts] while keeping [logic]" |
| Security issue | "🚨 Security fix needed: [prioritized list]" |
| Style mismatch | "Refactor to match [reference file] pattern" |
| Bug introduced | "Bug: input [X] gives [Y], expected [Z]. Fix in [location]" |

---

## Homework / 作业 (Optional)

Next time a prompt doesn't work as expected:

1. Use the Failure Diagnosis Checklist to identify what was missing
2. Write a specific recovery prompt (don't just say "try again")
3. Document what you learned for future prompts

---

**Next: Day 7 - Real Project Practice & Review / 下一课：第七天 - 真实项目实践与回顾**
