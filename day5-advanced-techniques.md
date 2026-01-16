# Day 5: Advanced Prompting Techniques
# 第五天：高级提示词技巧

**Duration / 时长**: 1-1.5 hours / 1-1.5小时

---

## Learning Objectives / 学习目标
- Use meta-prompts and self-correction / 使用元提示词和自我纠正
- Implement iterative refinement / 实现迭代改进
- Handle complex multi-step workflows / 处理复杂的多步骤工作流

---

## Core Concepts / 核心概念

### Advanced Techniques Overview / 高级技巧概览

```
┌─────────────────────────────────────────────────────────────┐
│                 ADVANCED TECHNIQUES                         │
│                    高级技巧                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🧠 Meta-Prompts      - Think before coding                │
│     元提示词           - 编码前思考                          │
│                                                             │
│  🔄 Iterative Refinement - Build in rounds                 │
│     迭代改进            - 分轮构建                          │
│                                                             │
│  ✅ Self-Verification  - Verify own work                   │
│     自我验证            - 验证自己的工作                     │
│                                                             │
│  🎭 Role-Based        - Expert perspectives                │
│     基于角色            - 专家视角                          │
│                                                             │
│  📋 Output Control    - Structured responses               │
│     输出控制            - 结构化响应                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Exercises with Solutions / 练习与答案

### Exercise 5.1: Meta-Prompts / 元提示词

**Task / 任务:** Write a meta-prompt for adding authentication to Express.js API

---

#### Complete Meta-Prompt / 完整元提示词

```
I need to add authentication to our Express.js API. Before implementing,
please analyze our options and recommend an approach.

## Context / 上下文
- Express.js API serving a React SPA frontend
- PostgreSQL database with existing User table
- Currently no authentication (all endpoints public)
- Will need both web and mobile clients in future

## Please Analyze / 请分析

### Step 1: Evaluate These Options / 评估这些选项
For each authentication method, analyze:

| Method | JWT | Sessions | OAuth 2.0 | API Keys |
|--------|-----|----------|-----------|----------|
| How it works | ? | ? | ? | ? |
| Best for | ? | ? | ? | ? |
| Pros | ? | ? | ? | ? |
| Cons | ? | ? | ? | ? |
| Complexity | ? | ? | ? | ? |

### Step 2: Consider These Factors / 考虑这些因素
- Scalability: Will this work with multiple servers?
- Security: Token theft, XSS, CSRF risks?
- Mobile compatibility: Works well with native apps?
- Implementation effort: How complex to implement?
- Maintenance: Session storage, token rotation, etc.?

### Step 3: Recommend / 推荐
Based on our context, recommend:
1. Primary recommendation with reasoning
2. What we'd need (libraries, database changes, etc.)
3. Potential risks and how to mitigate

### Step 4: Wait for Approval / 等待批准
Do NOT write any code yet. Present your analysis and wait for me to:
- Ask clarifying questions
- Choose an approach
- Give approval to proceed

## Output Format / 输出格式
### Analysis Summary
[Comparison table]

### Detailed Evaluation
[Each option with pros/cons]

### Recommendation
[Your suggestion with reasoning]

### Questions for Me
[Anything you need clarified before proceeding]
```

---

#### Meta-Prompt Benefits / 元提示词的好处

```
┌─────────────────────────────────────────────────────────────┐
│              META-PROMPT BENEFITS                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🎯 BETTER DECISIONS / 更好的决策                           │
│     Claude considers multiple approaches                   │
│     You see trade-offs before committing                   │
│                                                             │
│  🛡️ PREVENTS REWORK / 防止返工                             │
│     Catch wrong direction early                            │
│     Easier to change plan than code                        │
│                                                             │
│  📚 KNOWLEDGE TRANSFER / 知识传递                           │
│     Learn options you didn't know about                    │
│     Understand reasoning, not just code                    │
│                                                             │
│  🤝 COLLABORATIVE / 协作性                                  │
│     You stay in control of decisions                       │
│     Claude provides expertise, you provide direction       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

#### Meta-Prompt Patterns / 元提示词模式

```
ANALYSIS PATTERN / 分析模式:
"Before implementing, analyze X approaches and compare..."

DESIGN PATTERN / 设计模式:
"Before coding, design the architecture for..."

RISK PATTERN / 风险模式:
"Before proceeding, identify potential risks and mitigations..."

QUESTION PATTERN / 问题模式:
"Before starting, list any questions you have about..."
```

---

### Exercise 5.2: Iterative Refinement / 迭代改进

**Task / 任务:** Build notification system in 3 iterative rounds

---

#### Round 1: Core Foundation / 核心基础
**"Make it work"**

```
Build the basic notification system with storage and simple retrieval.

## Goal
Users can receive and view notifications. Basic CRUD operations work.

## Includes

### Database Schema
CREATE TABLE notifications (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  type VARCHAR(50) NOT NULL,
  title VARCHAR(255) NOT NULL,
  message TEXT,
  data JSONB,
  is_read BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW()
);

### Backend
- POST /api/notifications - Create notification
- GET /api/notifications - List user's notifications
- PATCH /api/notifications/:id/read - Mark as read
- PATCH /api/notifications/read-all - Mark all as read

### Frontend
- NotificationList component
- NotificationItem component
- Unread count badge in header

## Excludes (Deferred)
❌ Real-time updates
❌ Email notifications
❌ User preferences
❌ Push notifications

## Verify Round 1 Works
1. Create notification via API → appears in database
2. Fetch notifications → returns correct list
3. Click notification → marked as read
```

---

#### Round 2: Real-Time & UX Polish / 实时与用户体验完善
**"Make it good"**

```
Add real-time updates and improve user experience.

## Builds On
Round 1: Basic notification CRUD and display

## Adds

### Real-Time with WebSocket
- WebSocket connection: /ws/notifications
- Server pushes new notifications immediately
- Client updates UI without polling

### Notification Grouping
- Group similar notifications: "John and 5 others liked your post"
- Grouped by: type + target_id + time window (1 hour)

### User Preferences
CREATE TABLE notification_preferences (
  user_id UUID PRIMARY KEY,
  likes_enabled BOOLEAN DEFAULT TRUE,
  comments_enabled BOOLEAN DEFAULT TRUE,
  follows_enabled BOOLEAN DEFAULT TRUE,
  email_digest BOOLEAN DEFAULT FALSE
);

### UI Improvements
- Toast/popup for new notifications
- Slide-in notification panel
- Relative timestamps
- Unread visually distinct

## Excludes (Deferred)
❌ Email digest sending
❌ Push notifications

## Verify Round 2 Works
1. Like in tab 1 → notification in tab 2 instantly
2. 10 likes → shows grouped notification
3. Disable in preferences → no notifications
```

---

#### Round 3: Email, Push & Scale / 邮件、推送与扩展
**"Make it complete"**

```
Add email digests, push notifications, and prepare for scale.

## Builds On
Round 1: Basic CRUD
Round 2: Real-time, preferences, grouping

## Adds

### Email Digests
- Daily/weekly digest of unread notifications
- Scheduled cron job
- Unsubscribe link

### Push Notifications
- Firebase Cloud Messaging integration
- Device token storage
- High-priority notification triggers

### Delivery Queue
- Redis + Bull queue for notification delivery
- Separate queues: in-app, email, push
- Retry with exponential backoff

### Performance & Cleanup
- Index optimization
- Archive old notifications (90 days)
- Rate limiting

## Final Verification
1. Receive notification → in-app, push, email
2. Disable email → no digests
3. 1000 users simultaneously → handles load
```

---

#### Three-Round Progression / 三轮进展

```
┌─────────────────────────────────────────────────────────────┐
│              THREE-ROUND PROGRESSION                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ROUND 1: MAKE IT WORK / 让它工作                           │
│  • Core functionality only                                 │
│  • Simplest possible implementation                        │
│  • ~30% of final features                                  │
│                                                             │
│                    ↓                                        │
│                                                             │
│  ROUND 2: MAKE IT GOOD / 让它好用                           │
│  • Real-time / reactive                                    │
│  • UX polish                                               │
│  • User preferences                                        │
│  • ~70% of final features                                  │
│                                                             │
│                    ↓                                        │
│                                                             │
│  ROUND 3: MAKE IT COMPLETE / 让它完整                       │
│  • All channels (email, push)                              │
│  • Scale & reliability                                     │
│  • Analytics & monitoring                                  │
│  • 100% of final features                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### Exercise 5.3: Self-Verification Prompts / 自我验证提示词

**Task / 任务:** Write self-verification checklist for user registration

---

#### Complete Self-Verification Prompt / 完整自我验证提示词

```
After implementing the user registration feature, please verify your work
by completing this checklist. Report any issues found.

## 1. Functionality Check / 功能检查

### Happy Path
□ Can register with valid email and password
□ User is saved to database with correct fields
□ Password is hashed (not stored in plain text)
□ Success response returned with expected format
□ User can login immediately after registration

## 2. Validation Check / 验证检查

### Input Validation
□ Empty email → returns 400 with clear error
□ Invalid email format → returns 400 with clear error
□ Empty password → returns 400 with clear error
□ Password too short → returns 400 with requirements
□ Duplicate email → returns 409 "Email already registered"

### Edge Cases
□ Email with spaces → trimmed or rejected?
□ Email with uppercase → normalized to lowercase?
□ Unicode in email → handled correctly?
□ Very long email (255+ chars) → rejected?
□ Very long password (1000+ chars) → handled?

## 3. Security Audit / 安全审计

### Password Security
□ Password hashed with bcrypt/argon2 (not MD5/SHA1)
□ Cost factor is appropriate (bcrypt: ≥10)
□ Password not logged anywhere
□ Password not returned in any API response

### Injection Prevention
□ SQL injection: Try email = "'; DROP TABLE users;--"
□ NoSQL injection: Try email = {"$gt": ""}
□ All inputs parameterized/escaped

### Rate Limiting
□ Rate limit exists on registration endpoint
□ Returns 429 after too many attempts
□ Rate limit by IP, not just by email

### Information Disclosure
□ Error for "email exists" doesn't reveal timing info
□ No stack traces in error responses

## 4. Database Check / 数据库检查
□ User record created with all required fields
□ Timestamps populated
□ No sensitive data stored unnecessarily

## 5. Integration Check / 集成检查
□ Works with existing login endpoint
□ Doesn't break existing features
□ Email verification triggered (if required)

## 6. Code Quality Check / 代码质量检查
□ No TypeScript/ESLint errors
□ Follows existing code patterns
□ Error messages are user-friendly
□ Appropriate logging added

## Verification Summary
### ✅ Passed
[List all checks that passed]

### ⚠️ Warnings
[List potential issues]

### ❌ Failed
[List checks that failed - must be fixed]
```

---

#### Self-Verification Categories / 自我验证类别

```
┌─────────────────────────────────────────────────────────────┐
│              SELF-VERIFICATION CATEGORIES                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ✅ FUNCTIONALITY / 功能性                                   │
│     Does it do what was asked?                             │
│                                                             │
│  🔐 SECURITY / 安全性                                       │
│     Is it safe from common attacks?                        │
│                                                             │
│  🧪 EDGE CASES / 边界情况                                   │
│     What happens with weird inputs?                        │
│                                                             │
│  🔗 INTEGRATION / 集成                                      │
│     Does it work with existing code?                       │
│                                                             │
│  📊 QUALITY / 质量                                          │
│     Is the code clean and consistent?                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Additional Techniques / 附加技巧

### Role-Based Prompts / 基于角色的提示词

```
Act as a senior security engineer reviewing this authentication code.
作为一名高级安全工程师审查这段认证代码。

Focus on:
- OWASP Top 10 vulnerabilities
- Token handling best practices
- Session management

Provide findings in order of severity.
```

### Output Format Control / 输出格式控制

```
Please provide your response in this exact format:

### Analysis
[Your analysis here]

### Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| ... | Add/Modify/Delete | ... |

### Implementation
[Code blocks with file paths]

### Testing Instructions
[How to verify the changes]
```

### Conditional Logic in Prompts / 提示词中的条件逻辑

```
Implement user data export with these conditions:

IF the user is admin:
  - Allow export of all user fields
  - Include audit logs

ELSE IF the user is manager:
  - Allow export of their team only
  - Exclude sensitive fields

ELSE:
  - Only allow export of own data
```

---

## Day 5 Key Takeaways / 第五天关键收获

```
┌─────────────────────────────────────────────────────────────┐
│              ADVANCED TECHNIQUES SUMMARY                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🧠 META-PROMPTS / 元提示词                                 │
│     "Analyze options before implementing"                  │
│     → Better decisions, prevent rework                     │
│                                                             │
│  🔄 ITERATIVE REFINEMENT / 迭代改进                         │
│     Round 1: Make it work                                  │
│     Round 2: Make it good                                  │
│     Round 3: Make it complete                              │
│     → Manageable chunks, early validation                  │
│                                                             │
│  ✅ SELF-VERIFICATION / 自我验证                            │
│     "After implementing, verify these items"               │
│     → Catch issues before you do                           │
│                                                             │
│  🎭 ROLE-BASED / 基于角色                                   │
│     "Act as a security engineer reviewing..."              │
│     → Specialized perspectives                             │
│                                                             │
│  📋 OUTPUT CONTROL / 输出控制                               │
│     "Format your response as..."                           │
│     → Consistent, parseable results                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Reference / 快速参考

```
META-PROMPT STARTERS:
• "Before implementing, analyze..."
• "Before coding, design..."
• "Before proceeding, identify risks..."
• "Wait for my approval before writing code"

ITERATIVE ROUNDS:
• Round 1: Core functionality (30%)
• Round 2: Polish & preferences (70%)
• Round 3: Scale & complete (100%)

VERIFICATION CATEGORIES:
• Functionality: Does it work?
• Validation: Are inputs checked?
• Security: Is it safe?
• Edge cases: What could break?
• Integration: Does it fit?
```

---

## The Power Combo / 强力组合

```
MAXIMUM QUALITY WORKFLOW:

1. META-PROMPT: Analyze and plan
        ↓
2. ITERATE: Build in rounds
        ↓
3. VERIFY: Check each round
        ↓
4. REFINE: Based on verification
```

---

## Homework / 作业 (Optional)

For your next complex task:

1. Write a meta-prompt to analyze approaches
2. Plan 2-3 iterative rounds
3. Create a verification checklist
4. Execute and compare results to your usual approach

---

**Next: Day 6 - Debugging Prompts & Handling Failures / 下一课：第六天 - 调试提示词与处理失败**
