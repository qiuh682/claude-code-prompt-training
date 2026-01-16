# Day 4: Code-Specific Prompt Patterns
# 第四天：代码特定的提示词模式

**Duration / 时长**: 1-1.5 hours / 1-1.5小时

---

## Learning Objectives / 学习目标
- Master common code task prompts / 掌握常见代码任务提示词
- Learn debugging prompt techniques / 学习调试提示词技巧
- Write effective refactoring requests / 编写有效的重构请求

---

## Core Concepts / 核心概念

### Code Task Categories / 代码任务类别

```
┌─────────────────────────────────────────────────────────────┐
│                 CODE TASK CATEGORIES                        │
│                    代码任务类别                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🐛 Bug Fixing       - Diagnose and fix issues             │
│     Bug 修复         - 诊断和修复问题                        │
│                                                             │
│  ✨ Feature Building - Implement new functionality          │
│     功能构建         - 实现新功能                            │
│                                                             │
│  🔧 Refactoring     - Improve existing code                │
│     重构             - 改进现有代码                          │
│                                                             │
│  👀 Code Review     - Analyze for issues                   │
│     代码审查         - 分析问题                              │
│                                                             │
│  🧪 Test Writing    - Create test cases                    │
│     测试编写         - 创建测试用例                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Exercises with Solutions / 练习与答案

### Exercise 4.1: Bug Report Prompt / Bug 报告提示词

**Vague Issue / 模糊问题:** "Login doesn't work on mobile"

---

#### Complete Bug-Fixing Prompt / 完整的 Bug 修复提示词

```
Fix the mobile login issue where form submission fails silently on iOS Safari.
修复 iOS Safari 上表单提交静默失败的移动端登录问题。

## Bug Description / Bug 描述
Expected: User submits login form → redirected to dashboard
预期：用户提交登录表单 → 重定向到仪表板

Actual: User taps "Login" button → nothing happens, no error shown
实际：用户点击"登录"按钮 → 什么都没发生，没有显示错误

Works correctly on: Desktop Chrome, Desktop Safari, Android Chrome
正常工作于：桌面 Chrome、桌面 Safari、Android Chrome

Fails on: iOS Safari (iPhone 12, iOS 17.2), iOS Chrome
失败于：iOS Safari（iPhone 12，iOS 17.2）、iOS Chrome

## Steps to Reproduce / 复现步骤
1. Open https://myapp.com/login on iOS Safari
2. Enter valid credentials (test@example.com / password123)
3. Tap "Login" button
4. Observe: Button shows loading state briefly, then returns to normal
5. User remains on login page, not logged in

## Error Information / 错误信息
Console output (Safari Web Inspector):
```
[Error] Failed to fetch
[Error] Unhandled Promise Rejection: TypeError: cancelled
```

Network tab shows:
- POST /api/auth/login request starts
- Request status: "cancelled" after ~100ms
- No response received

## Relevant Files / 相关文件
- src/pages/Login.tsx (lines 45-80) - Form component with onSubmit handler
- src/hooks/useAuth.ts (lines 20-45) - Login mutation using React Query
- src/api/auth.ts - API call function

## Current Implementation / 当前实现
// src/pages/Login.tsx
const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();
  await loginMutation.mutateAsync({ email, password });
  router.push('/dashboard');
};

<form onSubmit={handleSubmit}>
  <button type="submit">Login</button>
</form>

## What I've Tried / 我尝试过的
1. ❌ Added e.stopPropagation() - no change
2. ❌ Wrapped in setTimeout - no change
3. ✅ Changed button to type="button" with onClick - WORKS but not ideal

## Suspected Cause / 疑似原因
iOS Safari may be cancelling the fetch request when the form submits,
possibly due to page navigation conflict or form default behavior.

## Constraints / 约束
- Keep using form element for accessibility (Enter key submit)
- Don't break existing desktop functionality
- Maintain React Query mutation pattern
```

---

#### Bug Report Anatomy / Bug 报告结构

```
┌─────────────────────────────────────────────────────────────┐
│              BUG REPORT PROMPT ANATOMY                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ✅ SPECIFIC ENVIRONMENT                                    │
│     "iOS Safari on iPhone 12, iOS 17.2"                    │
│     Not just "mobile"                                      │
│                                                             │
│  ✅ EXPECTED vs ACTUAL                                      │
│     Clear contrast of what should happen                   │
│                                                             │
│  ✅ REPRODUCIBLE STEPS                                      │
│     Numbered, specific actions                             │
│                                                             │
│  ✅ EXACT ERROR MESSAGES                                    │
│     Console output, network status                         │
│                                                             │
│  ✅ CODE CONTEXT                                            │
│     Current implementation shown                           │
│                                                             │
│  ✅ WHAT YOU'VE TRIED                                       │
│     Prevents duplicate suggestions                         │
│                                                             │
│  ✅ SUSPECTED CAUSE                                         │
│     Shows your analysis, guides solution                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### Exercise 4.2: Feature Implementation Prompt / 功能实现提示词

**Feature / 功能:** Forgot Password / 忘记密码

---

#### Complete Feature Implementation Prompt / 完整功能实现提示词

```
Implement a "Forgot Password" feature for user password recovery.
实现用户密码恢复的"忘记密码"功能。

## Feature Overview / 功能概述
Allow users to reset their password via email verification when they
forget their current password.

## User Story / 用户故事
As a registered user who forgot my password,
I want to reset it via email verification,
so that I can regain access to my account.

## User Flow / 用户流程
1. User clicks "Forgot Password" on login page
           ↓
2. User enters their email address
           ↓
3. System validates email format
           ↓
4. System sends reset email (whether account exists or not - security)
           ↓
5. User sees: "If an account exists, you'll receive an email"
           ↓
6. User clicks link in email → Reset Password page
           ↓
7. User enters new password (with confirmation)
           ↓
8. System validates and updates password
           ↓
9. User redirected to login with success message

## Technical Requirements / 技术要求

### Database / 数据库
CREATE TABLE password_resets (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  token_hash VARCHAR(255) NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  used_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);

### Backend Endpoints / 后端端点

#### POST /api/auth/forgot-password
Request: { "email": "user@example.com" }
Response (always 200): { "message": "If an account exists, a reset email has been sent" }

Logic:
- Generate secure random token (32 bytes)
- Hash token before storing
- Set expiration: 1 hour from now
- Send email with plain token in URL
- Invalidate any existing tokens for this user

#### POST /api/auth/reset-password
Request: { "token": "abc123...", "password": "newPassword123", "passwordConfirm": "newPassword123" }
Response: { "message": "Password reset successful" }

Errors:
- 400: "Passwords do not match"
- 400: "Password does not meet requirements"
- 400: "Invalid or expired reset token"

### Frontend Pages / 前端页面

#### 1. ForgotPassword Page (src/pages/ForgotPassword.tsx)
- Route: /forgot-password
- Form: email input only
- States: idle, submitting, success, error

#### 2. ResetPassword Page (src/pages/ResetPassword.tsx)
- Route: /reset-password?token=xxx
- Form: password, confirmPassword
- Password requirements shown inline

## Security Requirements / 安全要求

DO / 要做:
✅ Hash reset tokens before storing in database
✅ Use same response whether email exists or not (prevents enumeration)
✅ Expire tokens after 1 hour
✅ Single-use tokens (mark as used after reset)
✅ Rate limit: max 3 requests per email per hour
✅ Invalidate all sessions after password reset
✅ Log all password reset attempts

DON'T / 不要:
❌ Don't store plain text tokens
❌ Don't reveal if email exists in error messages
❌ Don't send password in email
❌ Don't use predictable tokens
❌ Don't allow token reuse

## Acceptance Criteria / 验收标准
□ User can request password reset from login page
□ Email is sent within 30 seconds of request
□ Reset link works and loads reset form
□ Expired token (>1 hour) shows appropriate error
□ Used token cannot be reused
□ New password must meet existing password requirements
□ After reset, user can login with new password
□ After reset, old sessions are invalidated
□ Non-existent email shows same success message (security)
□ Mobile responsive design

## Existing Code to Reference / 参考的现有代码
- Email sending: src/lib/email.ts
- Auth patterns: src/controllers/authController.ts
- Password hashing: src/utils/password.ts
- Form components: src/components/ui/Form, Input, Button
```

---

#### Feature Template Checklist / 功能模板检查清单

```
□ User story with role, action, benefit?
□ Complete user flow diagrammed?
□ All API endpoints specified?
□ Request/response formats defined?
□ Database changes documented?
□ Security requirements explicit?
□ Acceptance criteria testable?
□ Existing patterns referenced?
```

---

### Exercise 4.3: Refactoring Prompt / 重构提示词

**Task / 任务:** Refactor 500-line processOrder function

---

#### Complete Refactoring Prompt / 完整重构提示词

```
Refactor the monolithic processOrder function into smaller, testable units.
将单体 processOrder 函数重构为更小的、可测试的单元。

## Current State / 当前状态

Location: src/services/orderProcessor.js - processOrder() (lines 1-500)

### Problems / 问题:
1. 500 lines in single function - impossible to understand/maintain
2. 8 different responsibilities mixed together:
   - Order validation (lines 15-80)
   - Inventory checking (lines 81-150)
   - Price calculation (lines 151-250)
   - Payment processing (lines 251-320)
   - Inventory update (lines 321-370)
   - Email sending (lines 371-420)
   - Shipping label creation (lines 421-470)
   - Analytics logging (lines 471-500)
3. Untestable - can't test price calculation without mocking payment
4. No error recovery - failure at line 400 leaves partial state
5. Hidden dependencies - directly calls external APIs inline

## Desired State / 期望状态

### Architecture / 架构:
┌─────────────────────────────────────────────────────────────┐
│                    OrderProcessor                           │
│                   (Orchestrator only)                       │
│                     ~50 lines                               │
└─────────────────────┬───────────────────────────────────────┘
                      │ coordinates
    ┌─────────────────┼─────────────────┐
    ▼                 ▼                 ▼
┌─────────┐    ┌─────────────┐    ┌─────────────┐
│Validator│    │ PriceCalc   │    │InventoryMgr│
│ ~60 loc │    │  ~80 loc    │    │  ~70 loc    │
└─────────┘    └─────────────┘    └─────────────┘

### Each Module:
- Single responsibility
- Pure functions where possible
- Dependency injection for external services
- Independently testable

## Refactoring Goals / 重构目标
□ No function longer than 80 lines
□ Each module has single responsibility
□ External dependencies injected, not imported directly
□ Each module independently unit-testable
□ Clear error handling with rollback capability
□ Same external behavior (API contract unchanged)

## Proposed Structure / 建议结构

src/services/order/
├── index.ts                    # Re-exports OrderProcessor
├── OrderProcessor.ts           # Orchestrator (~50 lines)
├── validators/
│   └── orderValidator.ts       # Validation logic (~60 lines)
├── calculators/
│   └── priceCalculator.ts      # Price, tax, discount (~80 lines)
├── inventory/
│   └── inventoryManager.ts     # Stock check & update (~70 lines)
├── payment/
│   └── paymentProcessor.ts     # Payment handling (~60 lines)
├── notifications/
│   └── orderNotifier.ts        # Email sending (~50 lines)
├── shipping/
│   └── shippingService.ts      # Label creation (~50 lines)
├── analytics/
│   └── orderAnalytics.ts       # Event logging (~40 lines)
└── types.ts                    # Shared interfaces

## Constraints / 约束

MUST KEEP:
✅ Same function signature for processOrder()
✅ Same return type and error messages
✅ Same transaction semantics (all-or-nothing)
✅ Same logging output format

MUST NOT:
❌ Don't change database schema
❌ Don't change external API calls
❌ Don't add new dependencies
❌ Don't modify other files outside src/services/order/

## Migration Strategy / 迁移策略
Phase 1: Extract types and interfaces
Phase 2: Extract pure calculation functions
Phase 3: Extract validators
Phase 4: Extract services with side effects
Phase 5: Create orchestrator
Phase 6: Update imports
```

---

## Day 4 Key Takeaways / 第四天关键收获

```
┌─────────────────────────────────────────────────────────────┐
│              CODE-SPECIFIC PROMPT PATTERNS                  │
│                  代码特定提示词模式                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🐛 BUG FIXING / Bug 修复                                   │
│     Environment + Steps + Error + Tried + Suspected        │
│     环境 + 步骤 + 错误 + 尝试过的 + 疑似原因                 │
│                                                             │
│  ✨ FEATURE BUILDING / 功能构建                             │
│     User Story + Flow + Endpoints + Security + Criteria    │
│     用户故事 + 流程 + 端点 + 安全 + 标准                     │
│                                                             │
│  🔧 REFACTORING / 重构                                      │
│     Current + Desired + Goals + Structure + Constraints    │
│     当前 + 期望 + 目标 + 结构 + 约束                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Reference Templates / 快速参考模板

```
BUG FIX TEMPLATE / Bug 修复模板:
─────────────────────────────────────
• What: Expected vs Actual
• Where: Environment + file/line
• How: Steps to reproduce
• Error: Exact message/behavior
• Tried: Previous attempts
• Theory: Suspected cause

FEATURE TEMPLATE / 功能模板:
─────────────────────────────────────
• Story: As a X, I want Y, so that Z
• Flow: Step-by-step user journey
• Backend: Endpoints + DB changes
• Frontend: Pages + components
• Security: Requirements + restrictions
• Criteria: Testable acceptance items

REFACTOR TEMPLATE / 重构模板:
─────────────────────────────────────
• Current: Problems + line numbers
• Desired: Target architecture
• Goals: Measurable outcomes
• Structure: New file organization
• Constraints: What must not change
• Migration: Phased approach
```

---

## Additional Templates / 附加模板

### Code Review Prompt / 代码审查提示词

```
Review the following code for:
1. Security vulnerabilities
2. Performance issues
3. Code style consistency
4. Error handling completeness
5. Test coverage gaps

Please provide:
- Severity level for each issue (critical/major/minor)
- Specific line numbers
- Suggested fixes
```

### Test Writing Prompt / 测试编写提示词

```
Write unit tests for [Class/Function] in [file path].

Testing framework: [Jest/Mocha/pytest/etc.]

Please test:
- All public methods
- Edge cases: empty input, null values, invalid data
- Error scenarios
- Mock external dependencies

Follow the AAA pattern (Arrange, Act, Assert).
Target coverage: >80%
```

---

## The Patterns / 模式

```
Each code task type has optimal structure:
每种代码任务类型都有最佳结构：

Bug Fix    = Detective Report (evidence-based)
Feature    = Blueprint (comprehensive plan)
Refactor   = Renovation Plan (before/after)
Code Review = Audit Checklist (systematic)
Test Writing = Scenario Coverage (comprehensive)
```

---

## Homework / 作业 (Optional)

Take a real task from your work and:
拿一个你工作中的真实任务：

1. Identify which category it belongs to
   识别它属于哪个类别

2. Use the appropriate template
   使用合适的模板

3. Fill in all sections
   填写所有部分

4. Review: is anything missing?
   审查：有什么遗漏吗？

---

**Next: Day 5 - Advanced Prompting Techniques / 下一课：第五天 - 高级提示词技巧**
